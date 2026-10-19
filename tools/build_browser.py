#!/usr/bin/env python3
"""Build the self-hosted, browser-local edition without copying user workspaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "deploy" / "browser-runtime.lock.json"
RUNTIME_FILES = {
    "pyodide.js",
    "pyodide.mjs",
    "pyodide.asm.mjs",
    "pyodide.asm.wasm",
    "pyodide-lock.json",
    "python_stdlib.zip",
    "package.json",
}
UI_FILES = {
    "index.html",
    "app.js",
    "box.js",
    "styles.css",
    "browser.js",
    "browser-worker.js",
    "geist.woff2",
    "geist-mono.woff2",
    "font-license.txt",
    "logo.svg",
    "logo-512.png",
    "apple-touch-icon.png",
    "favicon.ico",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_download(record: dict, cache: Path) -> bytes:
    """A cached or freshly downloaded artifact must match the checked-in lock."""
    filename = record["filename"]
    if PurePosixPath(filename).name != filename:
        raise ValueError("Runtime lock filenames must be basenames.")
    target = cache / (record["sha256"] + "-" + filename)
    if target.exists():
        data = target.read_bytes()
    else:
        request = urllib.request.Request(
            record["url"], headers={"User-Agent": "omphalOS-browser-build/2.0"}
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read(record["bytes"] + 1)
    if len(data) != record["bytes"] or digest(data) != record["sha256"]:
        raise ValueError(f"Runtime integrity check failed: {filename}")
    if not target.exists():
        target.write_bytes(data)
    return data


def write_file(root: Path, relative: str, data: bytes) -> dict:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": relative, "sha256": digest(data), "bytes": len(data)}


def extract_runtime(archive_path: Path, destination: Path) -> list[dict]:
    files = []
    with tarfile.open(archive_path) as archive:
        for name in sorted(RUNTIME_FILES):
            member = archive.getmember("pyodide/" + name)
            if not member.isfile() or member.size > 32 * 1024 * 1024:
                raise ValueError(f"Unexpected runtime member: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Missing runtime member: {name}")
            files.append(
                write_file(destination, "runtime/pyodide/" + name, stream.read())
            )
    return files


def package_engine(package: Path, destination: Path) -> dict:
    inventory = {}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for source in sorted(package.glob("*.py")):
            if source.name == "hosted.py":
                continue
            if source.is_symlink() or not source.is_file():
                raise ValueError("Application modules must be regular files.")
            name = "omphalos/" + source.name
            raw = source.read_bytes()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
            inventory[name] = digest(raw)
    if not inventory or "omphalos/__init__.py" not in inventory:
        raise ValueError("The application package is missing.")
    return inventory


def pinned_package_lock(upstream: dict, wheels: list[dict]) -> dict:
    """Make Pyodide verify the wheel bytes it installs, with no CDN fallback."""
    dependencies = {
        "typing-extensions": [],
        "annotated-types": [],
        "typing-inspection": ["typing-extensions"],
        "pydantic-core": ["typing-extensions"],
        "pydantic": [
            "typing-extensions",
            "annotated-types",
            "typing-inspection",
            "pydantic-core",
        ],
    }
    return {
        "info": upstream["info"],
        "packages": {
            wheel["name"]: {
                "name": wheel["name"],
                "version": wheel["version"],
                "file_name": "../wheels/" + wheel["filename"],
                "sha256": wheel["sha256"],
                "install_dir": "site",
                "package_type": "package",
                "imports": [wheel["name"].replace("-", "_")],
                "depends": dependencies[wheel["name"]],
            }
            for wheel in wheels
        },
    }


def browser_asset(name: str, raw: bytes) -> bytes:
    if name == "index.html":
        text = raw.decode("utf-8")
        text = re.sub(
            r'(\b(?:src|href)=")/([^"/]+\.(?:js|css|svg|png|ico))"',
            r'\1./\2"',
            text,
        )
        needle = '<script src="./app.js" defer></script>'
        if text.count(needle) != 1:
            raise ValueError("Expected one application script in the interface.")
        text = text.replace(
            needle, '<script src="./browser.js" defer></script>\n    ' + needle
        )
        metadata = """    <meta name="description" content="Investigate records, review sources, and retain evidence. omphalOS runs in your browser." />
    <link rel="canonical" href="https://petervartanian.xyz/omphalos/" />
    <meta property="og:type" content="website" />
    <meta property="og:title" content="omphalOS: the center of the investigation" />
    <meta property="og:description" content="Investigate records, review sources, and retain evidence. Runs in your browser." />
    <meta property="og:url" content="https://petervartanian.xyz/omphalos/" />
    <meta property="og:image" content="https://petervartanian.xyz/omphalos/logo-512.png" />
    <meta property="og:image:width" content="512" />
    <meta property="og:image:height" content="512" />
    <meta property="og:image:alt" content="omphalOS ribbon logo" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:image" content="https://petervartanian.xyz/omphalos/logo-512.png" />
    <meta name="twitter:image:alt" content="omphalOS ribbon logo" />
"""
        text = text.replace("  </head>", metadata + "  </head>")
        return text.encode("utf-8")
    if name == "styles.css":
        return re.sub(rb"url\((['\"]?)/([^)'\"]+)\1\)", rb"url(\1./\2\1)", raw)
    return raw


def browser_interface(directory: Path) -> dict[str, bytes]:
    """Bind browser entry-point URLs to the exact assets in this build."""
    assets = {}
    for name in sorted(UI_FILES):
        source = directory / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Required browser interface asset is missing: {name}")
        assets[name] = browser_asset(name, source.read_bytes())
    index = assets["index.html"].decode("utf-8")
    for name in ("styles.css", "box.js", "browser.js", "app.js"):
        reference = f'="./{name}"'
        if index.count(reference) != 1:
            raise ValueError(f"Expected one browser entry-point reference: {name}")
        version = digest(assets[name])[:16]
        index = index.replace(reference, f'="./{name}?v={version}"')
    assets["index.html"] = index.encode("utf-8")
    return assets


def validate_output(output: Path) -> None:
    if not output.exists():
        return
    if output.is_symlink() or not output.is_dir():
        raise ValueError("Build output must be a regular directory.")
    marker = output / "build-manifest.json"
    if not marker.is_file():
        raise ValueError(
            "Refusing to replace a directory without an omphalOS build manifest."
        )
    manifest = json.loads(marker.read_text())
    if manifest.get("kind") != "omphalos-browser-build":
        raise ValueError("Unrecognized build directory.")
    allowed = {item["path"] for item in manifest["files"]} | {"build-manifest.json"}
    for path in output.rglob("*"):
        if path.is_symlink() or (
            path.is_file() and path.relative_to(output).as_posix() not in allowed
        ):
            raise ValueError(
                "Build output contains unrecognized files; use a new output directory."
            )


def build(output: Path, cache: Path, *, runtime_only: bool = False) -> dict:
    lock = json.loads(LOCK.read_text())
    validate_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".omphalos-browser-", dir=output.parent
    ) as temporary:
        stage = Path(temporary) / "site"
        stage.mkdir()
        archive_data = verified_download(lock["pyodide"], cache)
        archive_path = Path(temporary) / "runtime.tar.bz2"
        archive_path.write_bytes(archive_data)
        files = extract_runtime(archive_path, stage)
        package_lock_path = "runtime/pyodide/pyodide-lock.json"
        upstream = json.loads((stage / package_lock_path).read_text())
        package_lock = pinned_package_lock(upstream, lock["wheels"])
        files = [entry for entry in files if entry["path"] != package_lock_path]
        files.append(
            write_file(
                stage,
                package_lock_path,
                (json.dumps(package_lock, indent=2, sort_keys=True) + "\n").encode(),
            )
        )
        wheels = []
        for wheel in lock["wheels"]:
            entry = write_file(
                stage,
                "runtime/wheels/" + wheel["filename"],
                verified_download(wheel, cache),
            )
            wheels.append({**entry, "name": wheel["name"], "version": wheel["version"]})
            files.append(entry)
        for license_record in lock["licenses"]:
            files.append(
                write_file(
                    stage,
                    "runtime/licenses/" + license_record["filename"],
                    verified_download(license_record, cache),
                )
            )
        engine_path = stage / "runtime" / "omphalos.zip"
        inventory = package_engine(ROOT / "src" / "omphalos", engine_path)
        engine_data = engine_path.read_bytes()
        engine = {
            "path": "runtime/omphalos.zip",
            "sha256": digest(engine_data),
            "bytes": len(engine_data),
        }
        files.append(engine)
        runtime_manifest = {
            "schema_version": 1,
            "mode": "browser_local",
            "pyodide": {
                "version": lock["pyodide"]["version"],
                "python_version": lock["pyodide"]["python_version"],
                "abi": lock["pyodide"]["abi"],
                "index_url": "runtime/pyodide/",
            },
            "wheels": wheels,
            "engine": {**engine, "modules": inventory},
            "capabilities": {
                "native_ed25519_signing": False,
                "server_transport": False,
            },
        }
        files.append(
            write_file(
                stage,
                "runtime/manifest.json",
                (
                    json.dumps(runtime_manifest, indent=2, sort_keys=True) + "\n"
                ).encode(),
            )
        )
        if not runtime_only:
            for name, data in browser_interface(
                ROOT / "src" / "omphalos" / "ui"
            ).items():
                files.append(write_file(stage, name, data))
        files.append(write_file(stage, "LICENSE", (ROOT / "LICENSE").read_bytes()))
        manifest = {
            "kind": "omphalos-browser-build",
            "schema_version": 1,
            "runtime_only": runtime_only,
            "files": sorted(files, key=lambda item: item["path"]),
        }
        (stage / "build-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        if output.exists():
            shutil.rmtree(output)
        os.replace(stage, output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "browser")
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(tempfile.gettempdir()) / "omphalos-browser-runtime",
    )
    parser.add_argument(
        "--runtime-only",
        action="store_true",
        help="Build Python assets before the browser bridge is ready.",
    )
    args = parser.parse_args()
    try:
        import truststore
    except ImportError:
        pass
    else:
        truststore.inject_into_ssl()
    manifest = build(
        args.output.absolute(), args.cache.absolute(), runtime_only=args.runtime_only
    )
    total = sum(item["bytes"] for item in manifest["files"])
    print(
        f"Built {len(manifest['files'])} verified files ({total:,} bytes) in {args.output}"
    )


if __name__ == "__main__":
    main()
