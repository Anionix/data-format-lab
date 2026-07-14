from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


class ArtifactBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactRecord:
    relative_path: str
    size_bytes: int
    sha256: str


class EvidenceStore:
    def __init__(self, root: Path, budget_bytes: int) -> None:
        if budget_bytes < 0:
            raise ValueError("artifact budget must be non-negative")
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            raise ValueError("evidence root must not be a symlink")
        self.root = root.resolve()
        self.budget_bytes = budget_bytes
        existing = list(self.root.rglob("*"))
        if any(item.is_symlink() for item in existing):
            raise ValueError("evidence root must not contain symlinks")
        self.used_bytes = sum(item.stat().st_size for item in existing if item.is_file())
        if self.used_bytes > self.budget_bytes:
            raise ArtifactBudgetExceeded(
                f"existing artifacts exceed budget: used {self.used_bytes}, budget {self.budget_bytes}"
            )

    def _target(self, relative: str | Path) -> Path:
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("artifact path must be a safe relative path")
        target = self.root / relative
        if any(parent.is_symlink() for parent in (target, *target.parents) if parent != self.root.parent):
            raise ValueError("artifact path must not contain symlinks")
        if not target.resolve(strict=False).is_relative_to(self.root):
            raise ValueError("artifact path escapes the evidence root")
        return target

    def _reserve(self, size: int) -> None:
        if self.used_bytes + size > self.budget_bytes:
            raise ArtifactBudgetExceeded(
                f"artifact budget exhausted: required {size}, remaining {self.budget_bytes - self.used_bytes}"
            )

    def store_bytes(self, relative: str | Path, data: bytes) -> ArtifactRecord:
        target = self._target(relative)
        if target.exists():
            raise FileExistsError(target)
        self._reserve(len(data))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.used_bytes += len(data)
        return self._record(target)

    def import_path(self, source: Path, relative: str | Path) -> tuple[ArtifactRecord, ...]:
        if source.is_symlink():
            raise ValueError("artifact source must exist and must not be a symlink")
        source = source.resolve()
        if not source.exists():
            raise ValueError("artifact source must exist and must not be a symlink")
        files = [source] if source.is_file() else sorted(item for item in source.rglob("*") if item.is_file())
        if any(item.is_symlink() for item in source.rglob("*")):
            raise ValueError("artifact source must not contain symlinks")
        size = sum(item.stat().st_size for item in files)
        target = self._target(relative)
        if target.exists():
            raise FileExistsError(target)
        self._reserve(size)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target) if source.is_file() else shutil.copytree(source, target)
        self.used_bytes += size
        copied = [target] if target.is_file() else sorted(item for item in target.rglob("*") if item.is_file())
        return tuple(self._record(item) for item in copied)

    def _record(self, path: Path) -> ArtifactRecord:
        data = path.read_bytes()
        return ArtifactRecord(path.relative_to(self.root).as_posix(), len(data), hashlib.sha256(data).hexdigest())
