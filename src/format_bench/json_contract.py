"""Strict JSON serialization shared by public and persistent writers."""

from __future__ import annotations

import json
import math
import os
import stat
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


def _destination_mode(directory_fd: int, name: str) -> int:
    try:
        destination = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return 0o644
    if stat.S_ISLNK(destination.st_mode):
        raise ValueError("JSON destination must not be a symbolic link")
    if not stat.S_ISREG(destination.st_mode):
        raise ValueError("JSON destination must be a regular file")
    return stat.S_IMODE(destination.st_mode)


def _temporary_name(directory_fd: int, descriptor: int, temporary: Path) -> str:
    try:
        entry = os.stat(temporary.name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError as error:
        raise ValueError(
            "temporary JSON file must use the destination's same directory"
        ) from error
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISREG(entry.st_mode)
        or entry.st_dev != opened.st_dev
        or entry.st_ino != opened.st_ino
    ):
        raise ValueError(
            "temporary JSON file must be a regular same-directory entry"
        )
    return temporary.name


def _replace_same_directory(
    directory_fd: int,
    temporary_name: str,
    destination_name: str,
) -> None:
    _destination_mode(directory_fd, destination_name)
    os.replace(
        temporary_name,
        destination_name,
        src_dir_fd=directory_fd,
        dst_dir_fd=directory_fd,
    )


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
    destination_parent = destination.parent.resolve(strict=True)
    destination_name = destination.name
    if not destination_name or destination_name in {".", ".."}:
        raise ValueError("JSON destination must name a regular file")

    directory_fd = -1
    descriptor = -1
    temporary: Path | None = None
    temporary_name: str | None = None
    try:
        directory_fd = os.open(
            destination_parent,
            os.O_RDONLY | os.O_DIRECTORY,
        )
        mode = _destination_mode(directory_fd, destination_name)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination_parent,
        )
        temporary = Path(temporary_name)
        temporary_name = _temporary_name(directory_fd, descriptor, temporary)
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            _write_atomic_file(stream, payload)
            _flush_atomic_file(stream)
        # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED ->
        # BENCHMARKED -> REPORTED becomes persistent only at this replace boundary.
        # os.replace is atomic on success; file fsync does not claim directory or
        # power-loss durability. See https://docs.python.org/3/library/os.html#os.replace
        _replace_same_directory(directory_fd, temporary_name, destination_name)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None and directory_fd >= 0:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        elif temporary is not None:
            temporary.unlink(missing_ok=True)
        if directory_fd >= 0:
            os.close(directory_fd)
