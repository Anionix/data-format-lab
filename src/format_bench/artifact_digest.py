from __future__ import annotations

import errno
import hashlib
import os
import stat
from pathlib import Path
from typing import Protocol


_CHUNK_SIZE = 1024 * 1024
_DESCRIPTOR_HASHING = os.name == "posix" and hasattr(os, "O_NOFOLLOW")


class _Digest(Protocol):
    def update(self, data: bytes, /) -> None: ...


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _read_file_descriptor(digest: _Digest, file_descriptor: int) -> None:
    before = os.fstat(file_descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("artifact entry is not a regular file")
    digest.update(before.st_size.to_bytes(8, "big"))
    while chunk := os.read(file_descriptor, _CHUNK_SIZE):
        digest.update(chunk)
    after = os.fstat(file_descriptor)
    if not _same_identity(before, after):
        raise ValueError("artifact changed while hashing")


def _open_no_follow(
    path: str | bytes | Path,
    *,
    directory_fd: int | None = None,
    root: bool = False,
) -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        if directory_fd is None:
            return os.open(path, flags)
        return os.open(path, flags, dir_fd=directory_fd)
    except OSError as error:
        if error.errno == errno.ELOOP:
            message = (
                "artifact path must not be a symlink"
                if root
                else "artifact path must not contain a symlink"
            )
            raise ValueError(message) from error
        raise


def _open_path_no_follow(path: Path) -> int:
    if path.is_absolute():
        current_fd = os.open(os.sep, os.O_RDONLY)
        components = path.parts[1:]
    else:
        current_fd = os.open(".", os.O_RDONLY)
        components = path.parts
    try:
        for index, component in enumerate(components):
            if component == ".":
                continue
            next_fd = _open_no_follow(
                component,
                directory_fd=current_fd,
                root=index == len(components) - 1,
            )
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _collect_directory_entries(
    directory_fd: int,
    prefix: tuple[str, ...],
    entries: list[tuple[tuple[str, ...], str, os.stat_result]],
) -> None:
    names = sorted(os.fsdecode(name) for name in os.listdir(directory_fd))
    for name in names:
        entry_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        relative = prefix + (name,)
        if stat.S_ISLNK(entry_stat.st_mode):
            raise ValueError(f"artifact directory contains a symlink: {name}")
        if stat.S_ISDIR(entry_stat.st_mode):
            entries.append((relative, "directory", entry_stat))
            child_fd = _open_no_follow(name, directory_fd=directory_fd)
            try:
                child_stat = os.fstat(child_fd)
                if not stat.S_ISDIR(child_stat.st_mode) or not _same_identity(
                    entry_stat, child_stat
                ):
                    raise ValueError("artifact directory changed while hashing")
                _collect_directory_entries(child_fd, relative, entries)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(entry_stat.st_mode):
            entries.append((relative, "file", entry_stat))
        else:
            raise ValueError(f"unsupported artifact entry: {name}")


def _open_relative_file(root_fd: int, relative: tuple[str, ...]) -> int:
    if not relative:
        raise ValueError("artifact file path is empty")
    current_fd = os.dup(root_fd)
    try:
        for component in relative[:-1]:
            next_fd = _open_no_follow(component, directory_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
            if not stat.S_ISDIR(os.fstat(current_fd).st_mode):
                raise ValueError("artifact path component is not a directory")
        return _open_no_follow(relative[-1], directory_fd=current_fd)
    finally:
        os.close(current_fd)


def _artifact_sha256_descriptor(path: Path) -> str:
    digest = hashlib.sha256()

    def frame(kind: bytes, value: bytes = b"") -> None:
        digest.update(kind)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    root_fd = _open_path_no_follow(path)
    try:
        root_stat = os.fstat(root_fd)
        if stat.S_ISREG(root_stat.st_mode):
            frame(b"root-file")
            _read_file_descriptor(digest, root_fd)
            return digest.hexdigest()
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError(f"artifact path is neither a file nor directory: {path}")

        frame(b"root-directory")
        entries: list[tuple[tuple[str, ...], str, os.stat_result]] = []
        _collect_directory_entries(root_fd, (), entries)
        entries.sort(key=lambda item: Path(*item[0]).as_posix())
        for relative, kind, expected_stat in entries:
            encoded_relative = Path(*relative).as_posix().encode("utf-8")
            if kind == "directory":
                frame(b"directory-entry", encoded_relative)
                continue
            frame(b"file-entry", encoded_relative)
            file_fd = _open_relative_file(root_fd, relative)
            try:
                actual_stat = os.fstat(file_fd)
                if not _same_identity(expected_stat, actual_stat):
                    raise ValueError("artifact changed while hashing")
                _read_file_descriptor(digest, file_fd)
            finally:
                os.close(file_fd)
        return digest.hexdigest()
    finally:
        os.close(root_fd)


def _artifact_sha256_path(path: Path) -> str:
    digest = hashlib.sha256()

    def frame(kind: bytes, value: bytes = b"") -> None:
        digest.update(kind)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    def add_file(file_path: Path) -> None:
        digest.update(file_path.stat().st_size.to_bytes(8, "big"))
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
                digest.update(chunk)

    if path.is_symlink():
        raise ValueError(f"artifact path must not be a symlink: {path}")
    if path.is_file():
        frame(b"root-file")
        add_file(path)
    elif path.is_dir():
        frame(b"root-directory")
        for child in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
            relative = child.relative_to(path).as_posix().encode("utf-8")
            if child.is_symlink():
                raise ValueError(f"artifact directory contains a symlink: {child}")
            if child.is_dir():
                frame(b"directory-entry", relative)
            elif child.is_file():
                frame(b"file-entry", relative)
                add_file(child)
            else:
                raise ValueError(f"unsupported artifact entry: {child}")
    else:
        raise ValueError(f"artifact path is neither a file nor directory: {path}")
    return digest.hexdigest()


def artifact_sha256(path: Path) -> str:
    """Hash a file or directory with deterministic framing and safe reads."""
    # LLM contract: DISCOVERED -> FRAMED -> HASHED; unsafe entries terminate FAILED.
    if _DESCRIPTOR_HASHING:
        return _artifact_sha256_descriptor(path)
    return _artifact_sha256_path(path)
