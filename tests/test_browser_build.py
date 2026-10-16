"""Static deployment contains only checked application and runtime artifacts."""

import importlib.util
import json
import re
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def builder():
    source = Path(__file__).parents[1] / "tools" / "build_browser.py"
    spec = importlib.util.spec_from_file_location("omphalos_browser_build", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_engine_archive_is_deterministic_and_excludes_user_data_and_hosted_backend(
    builder, tmp_path
):
    package = tmp_path / "package"
    package.mkdir()
    (package / "__init__.py").write_text('__version__ = "2.0.0"\n')
    (package / "models.py").write_text('value = "retained engine"\n')
    (package / "hosted.py").write_text('raise Exception("not a browser transport")\n')
    (package / "private.json").write_text("secret")
    (package / "workspace").mkdir()
    (package / "workspace" / "private.py").write_text("secret")
    one, two = tmp_path / "one.zip", tmp_path / "two.zip"
    inventory = builder.package_engine(package, one)
    builder.package_engine(package, two)
    assert one.read_bytes() == two.read_bytes()
    with zipfile.ZipFile(one) as archive:
        assert archive.namelist() == ["omphalos/__init__.py", "omphalos/models.py"]
        assert set(inventory) == set(archive.namelist())


def test_engine_build_rejects_link_to_external_source(builder, tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    outside = tmp_path / "private.py"
    outside.write_text("secret")
    (package / "__init__.py").symlink_to(outside)
    with pytest.raises(ValueError, match="regular files"):
        builder.package_engine(package, tmp_path / "engine.zip")


def test_cached_runtime_is_rechecked_before_use(builder, tmp_path):
    good = b"official artifact"
    record = {
        "filename": "asset.whl",
        "bytes": len(good),
        "sha256": builder.digest(good),
    }
    cached = tmp_path / (record["sha256"] + "-" + record["filename"])
    cached.write_bytes(b"altered artifact!")
    with pytest.raises(ValueError, match="integrity check failed"):
        builder.verified_download(record, tmp_path)
    cached.write_bytes(good)
    assert builder.verified_download(record, tmp_path) == good


def test_browser_assets_are_relative_and_bridge_precedes_app(builder):
    source = (builder.ROOT / "src" / "omphalos" / "ui" / "index.html").read_bytes()
    result = builder.browser_asset("index.html", source).decode()
    assert result.index('src="./browser.js"') < result.index('src="./app.js"')
    assert 'src="/app.js"' not in result and 'href="/styles.css"' not in result
    assert 'rel="canonical" href="https://petervartanian.xyz/omphalos/"' in result
    css = builder.browser_asset(
        "styles.css", b"src:url('/geist.woff2'); background:url(/image.png)"
    )
    assert css == b"src:url('./geist.woff2'); background:url(./image.png)"


def test_browser_entry_urls_hash_transformed_assets_without_changing_native_index(
    builder,
):
    directory = builder.ROOT / "src" / "omphalos" / "ui"
    original_index = (directory / "index.html").read_bytes()
    assets = builder.browser_interface(directory)
    html = assets["index.html"].decode()
    versions = dict(re.findall(r'(?:src|href)="\./([^"?]+)\?v=([0-9a-f]{16})"', html))
    assert set(versions) == {"styles.css", "box.js", "browser.js", "app.js"}
    for name, version in versions.items():
        assert version == builder.digest(assets[name])[:16]
    assert html.index('src="./browser.js?v=') < html.index('src="./app.js?v=')
    assert assets["styles.css"] != (directory / "styles.css").read_bytes()
    assert (directory / "index.html").read_bytes() == original_index
    assert b'src="/app.js"' in original_index and b"?v=" not in original_index


def test_changed_renderer_gets_new_url_while_unchanged_assets_keep_their_urls(
    builder, tmp_path
):
    directory = builder.ROOT / "src" / "omphalos" / "ui"
    for name in builder.UI_FILES:
        (tmp_path / name).write_bytes((directory / name).read_bytes())
    first = builder.browser_interface(tmp_path)
    (tmp_path / "box.js").write_bytes(
        first["box.js"] + b"\n// Updated renderer fixture\n"
    )
    second = builder.browser_interface(tmp_path)
    for name in ("styles.css", "box.js", "browser.js", "app.js"):
        first_url = f"./{name}?v={builder.digest(first[name])[:16]}".encode()
        second_url = f"./{name}?v={builder.digest(second[name])[:16]}".encode()
        assert first_url in first["index.html"]
        assert second_url in second["index.html"]
        assert (first_url != second_url) is (name == "box.js")
    assert builder.browser_interface(tmp_path) == second


def test_build_will_not_replace_unrecognized_output(builder, tmp_path):
    retained = tmp_path / "private.json"
    retained.write_text("keep")
    with pytest.raises(ValueError, match="without an omphalOS build manifest"):
        builder.validate_output(tmp_path)
    (tmp_path / "build-manifest.json").write_text(
        json.dumps({"kind": "omphalos-browser-build", "files": []})
    )
    with pytest.raises(ValueError, match="unrecognized files"):
        builder.validate_output(tmp_path)
    assert retained.read_text() == "keep"


def test_runtime_package_lock_has_only_the_exact_local_hashed_wheels(builder):
    pinned = json.loads(builder.LOCK.read_text())
    info = {"python": "3.14.2", "abi_version": "2026_0", "arch": "wasm32"}
    configured = builder.pinned_package_lock(
        {"info": info, "packages": {"cryptography": {"version": "old"}}},
        pinned["wheels"],
    )
    assert configured["info"] == info
    assert set(configured["packages"]) == {
        record["name"] for record in pinned["wheels"]
    }
    for record in pinned["wheels"]:
        runtime = configured["packages"][record["name"]]
        assert runtime["sha256"] == record["sha256"]
        assert runtime["version"] == record["version"]
        assert runtime["file_name"] == "../wheels/" + record["filename"]
        assert set(runtime["depends"]) <= set(configured["packages"])
