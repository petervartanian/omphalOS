from __future__ import annotations

import json
from pathlib import Path

import typer

from omphalos.core import determinism, publishability, release, sbom
from omphalos.core.contracts import load_json_schema, validate_json_against_schema
from omphalos.core.exceptions import WorkbenchError
from omphalos.core.pipeline import run_workbench
from omphalos.core.settings import load_run_config

app = typer.Typer(add_completion=False, help="omphalOS CLI (import package: omphalos).")


@app.command()
def run(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False, help="Run config YAML."),
) -> None:
    """Execute a deterministic run and write artifacts."""
    cfg = load_run_config(config)
    run_dir = run_workbench(cfg, config_path=str(config))
    typer.echo(str(run_dir))


@app.command()
def verify(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False),
) -> None:
    """Verify a run directory's internal contracts and hashes."""
    report = determinism.verify_run_dir(run_dir)
    typer.echo(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PASS":
        raise typer.Exit(code=2)


@app.command()
def certify(
    run_a: Path = typer.Option(..., "--run-a", exists=True, file_okay=False),
    run_b: Path = typer.Option(..., "--run-b", exists=True, file_okay=False),
) -> None:
    """Compare two runs and certify determinism equivalence."""
    rep = determinism.certify_equivalence(run_a, run_b)
    typer.echo(json.dumps(rep, indent=2, sort_keys=True))
    if rep["status"] != "PASS":
        raise typer.Exit(code=2)


release_app = typer.Typer(add_completion=False, help="Release bundle operations.")
app.add_typer(release_app, name="release")


@release_app.command("build")
def release_build(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False),
    out: Path = typer.Option(..., "--out", dir_okay=False),
) -> None:
    """Build a release tarball and emit a release manifest."""
    manifest_path = release.build_release_bundle(run_dir, out)
    typer.echo(str(manifest_path))


@release_app.command("verify")
def release_verify(
    bundle: Path = typer.Option(..., "--bundle", exists=True, dir_okay=False),
) -> None:
    """Verify a release tarball against its embedded release manifest."""
    rep = release.verify_release_bundle(bundle)
    typer.echo(json.dumps(rep, indent=2, sort_keys=True))
    if rep["status"] != "PASS":
        raise typer.Exit(code=2)


pub_app = typer.Typer(add_completion=False, help="Publishability scanning.")
app.add_typer(pub_app, name="publishability")


@pub_app.command("scan")
def publishability_scan(
    path: Path = typer.Option(..., "--path", exists=True),
    out: Path = typer.Option(..., "--out", dir_okay=False),
) -> None:
    """Scan a path for high-risk patterns and emit a publishability report."""
    rep = publishability.scan_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(str(out))
    if rep["status"] != "PASS":
        raise typer.Exit(code=2)


@app.command("sbom")
def sbom_manifest(
    out: Path = typer.Option(..., "--out", dir_okay=False),
) -> None:
    """Emit an SBOM manifest as JSON."""
    rep = sbom.generate_sbom_manifest()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(str(out))


contracts_app = typer.Typer(add_completion=False, help="Contract validation utilities.")
app.add_typer(contracts_app, name="contracts")


@contracts_app.command("validate")
def contracts_validate(
    schema: str = typer.Option(..., "--schema", help="Schema filename under contracts/schemas."),
    json_path: Path = typer.Option(..., "--json", exists=True, dir_okay=False),
) -> None:
    """Validate a JSON file against a named schema."""
    sch = load_json_schema(schema)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    validate_json_against_schema(data, sch)
    typer.echo("PASS")


@app.callback()
def main() -> None:
    """Entry point."""
    return


def _die(msg: str) -> None:
    typer.echo(msg, err=True)
    raise typer.Exit(code=2)


def app_entry() -> None:
    """Console script entrypoint."""
    try:
        app()
    except WorkbenchError as e:
        _die(str(e))
