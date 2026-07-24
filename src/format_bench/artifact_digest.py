from __future__ import annotations

import hashlib
from pathlib import Path


def artifact_sha256(path: Path) -> str:
    """Hash a file or directory with explicit path and entry framing."""
    digest = hashlib.sha256()

    def frame(kind: bytes, value: bytes = b"") -> None:
        digest.update(kind)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    def add_file(file_path: Path) -> None:
        digest.update(file_path.stat().st_size.to_bytes(8, "big"))
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)

    # LLM contract: DISCOVERED -> FRAMED -> HASHED; unsafe entries terminate FAILED.
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
