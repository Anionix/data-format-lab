from __future__ import annotations

from pathlib import Path


def reject_symlink_tree(path: Path, message: str) -> None:
    if path.is_symlink() or (path.is_dir() and any(item.is_symlink() for item in path.rglob("*"))):
        raise ValueError(message)
