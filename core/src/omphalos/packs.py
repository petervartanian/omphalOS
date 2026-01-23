import os
import shutil
import tarfile
from pathlib import Path

from .util import read_json, sha256_file


def pack_verify(index_path):
    idx = read_json(index_path)
    base = Path(index_path).parent
    ok = True
    for pk in idx.get("packs", []):
        p = base / pk["file"]
        ok = ok and p.exists() and sha256_file(p) == pk["sha256"]
    return ok


def _is_within_directory(base: Path, target: Path) -> bool:
    base_r = base.resolve()
    try:
        target.resolve().relative_to(base_r)
        return True
    except Exception:
        return False


def _safe_extract(tf: tarfile.TarFile, dest: Path) -> None:
    """Extract a tarball defensively.

    Refuses:
      - absolute paths and traversal
      - symlinks, hardlinks
      - device nodes and other special files
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    safe_members = []
    for m in tf.getmembers():
        name = m.name

        # Absolute paths, Windows drive prefixes, or tilde expansion are disallowed.
        if os.path.isabs(name) or name.startswith("~"):
            raise ValueError(f"unsafe tar member path: {name}")

        p = Path(name)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError(f"unsafe tar traversal: {name}")

        # Symlinks/hardlinks and special files are disallowed.
        if m.issym() or m.islnk():
            raise ValueError(f"unsafe tar link entry: {name}")
        if m.isdev():
            raise ValueError(f"unsafe tar device entry: {name}")

        out_path = dest / p
        if not _is_within_directory(dest, out_path):
            raise ValueError(f"unsafe tar escape: {name}")

        safe_members.append(m)

    for m in safe_members:
        tf.extract(m, path=dest)


def pack_install(index_path, dest_dir):
    idx = read_json(index_path)
    base = Path(index_path).parent
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    for pk in idx.get("packs", []):
        src = base / pk["file"]
        out = dest / pk["name"]
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True, exist_ok=True)
        with tarfile.open(src, "r:gz") as tf:
            _safe_extract(tf, out)
