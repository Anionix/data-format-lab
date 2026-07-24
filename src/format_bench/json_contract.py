"""Strict JSON serialization shared by public and persistent writers."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import BinaryIO, Never, TypedDict, Unpack, cast


class JsonDumpOptions(TypedDict, total=False):
    ensure_ascii: bool
    indent: int | str | None
    separators: tuple[str, str] | None
    sort_keys: bool


def _write_atomic_file(destination: BinaryIO, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = destination.write(payload[offset:])
        if written <= 0:
            raise OSError("temporary JSON file write made no progress")
        offset += written


def _flush_atomic_file(destination: BinaryIO) -> None:
    destination.flush()
    os.fsync(destination.fileno())


def _replace_same_directory(temporary: Path, destination: Path) -> None:
    if temporary.parent != destination.parent:
        raise ValueError(
            "temporary JSON file must use the destination's same directory"
        )
    if destination.is_symlink():
        raise ValueError("JSON destination must not be a symbolic link")
    os.replace(temporary, destination)


def _reject_nonfinite(token: str) -> Never:
    raise json.JSONDecodeError(
        f"non-finite JSON number is not permitted: {token}",
        token,
        0,
    )


def _parse_finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        _reject_nonfinite(token)
    return value


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise json.JSONDecodeError(
                f"duplicate JSON object key: {key}",
                key,
                0,
            )
        result[key] = value
    return result


def strict_json_loads(value: str) -> object:
    """Parse RFC 8259 JSON without Python's NaN and Infinity extensions."""
    return cast(
        object,
        json.loads(
            value,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
            object_pairs_hook=_reject_duplicate_keys,
        ),
    )


def strict_json_dumps(value: object, **kwargs: Unpack[JsonDumpOptions]) -> str:
    """Serialize JSON while rejecting values outside the RFC 8259 number grammar."""
    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    # RFC 8259 Section 6 excludes NaN and Infinity; reject each value before emission.
    if "allow_nan" in kwargs:
        raise TypeError("allow_nan is fixed to False")
    return json.dumps(value, allow_nan=False, **kwargs)


def atomic_write_json(path: Path, value: object) -> None:
    """Write one deterministic JSON document through a same-directory replace."""
    payload = (strict_json_dumps(value, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    destination = path.absolute()
    if destination.is_symlink():
        raise ValueError("JSON destination must not be a symbolic link")
    if destination.exists() and not destination.is_file():
        raise ValueError("JSON destination must be a regular file")

    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            _write_atomic_file(stream, payload)
            _flush_atomic_file(stream)
        # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED ->
        # BENCHMARKED -> REPORTED becomes persistent only at this replace boundary.
        # os.replace is atomic on success; file fsync does not claim directory or
        # power-loss durability. See https://docs.python.org/3/library/os.html#os.replace
        _replace_same_directory(temporary, destination)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
