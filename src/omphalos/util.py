"""Shared, deterministic serialization and constrained filesystem operations."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any

ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")


class OmphalOSError(ValueError):
    """An actionable invalid-input or incomplete-evidence error."""


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise OmphalOSError("Non-finite numbers are not permitted.")
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """Versioned application encoding; not a claim of RFC 8785 conformance."""
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
            default=_json_default,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OmphalOSError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path | str) -> Any:
    def reject_constant(value: str) -> Any:
        raise OmphalOSError(f"Invalid JSON number: {value}")

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise OmphalOSError("JSON number exceeds finite floating-point range.")
        return parsed

    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(
            handle,
            object_pairs_hook=_unique_object,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )


def atomic_write(path: Path | str, content: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise OmphalOSError("Refusing to replace a symbolic link.")
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=".write-", delete=False
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def write_json(path: Path | str, value: Any) -> None:
    atomic_write(path, canonical_json(value))


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def safe_id(value: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise OmphalOSError(
            "IDs must use 1–80 letters, digits, underscores or hyphens, "
            "and start with a letter or digit."
        )
    return value


def safe_child(root: Path | str, relative: str | Path) -> Path:
    """Resolve a relative POSIX artifact path without crossing a symlink/root."""
    root = Path(root)
    if root.is_symlink():
        raise OmphalOSError("Symbolic links are not evidence directories.")
    root = root.resolve()
    value = str(relative)
    rel = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 for character in value)
        or rel.is_absolute()
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise OmphalOSError("Artifact paths must remain within their directory.")
    target = root
    for part in rel.parts:
        target = target / part
        if target.is_symlink():
            raise OmphalOSError("Symbolic links are not evidence artifacts.")
    if not target.resolve().is_relative_to(root):
        raise OmphalOSError("Artifact path escapes its directory.")
    return target
