from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

import format_bench.artifact_digest as artifact_digest
from format_bench.artifact_digest import artifact_sha256


def _legacy_digest(path: Path) -> str:
    digest = hashlib.sha256()

    def frame(kind: bytes, value: bytes = b"") -> None:
        digest.update(kind)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    def add_file(file_path: Path) -> None:
        digest.update(file_path.stat().st_size.to_bytes(8, "big"))
        digest.update(file_path.read_bytes())

    if path.is_file():
        frame(b"root-file")
        add_file(path)
    else:
        frame(b"root-directory")
        for child in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
            relative = child.relative_to(path).as_posix().encode("utf-8")
            if child.is_dir():
                frame(b"directory-entry", relative)
            else:
                frame(b"file-entry", relative)
                add_file(child)
    return digest.hexdigest()


def test_descriptor_hash_preserves_deterministic_directory_framing(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact"
    (artifact / "a").mkdir(parents=True)
    (artifact / "a" / "nested.bin").write_bytes(b"nested")
    (artifact / "a.txt").write_bytes(b"sibling")

    assert artifact_sha256(artifact) == _legacy_digest(artifact)


def test_descriptor_hash_rejects_nested_symlink_without_reading_target(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("must remain unread", encoding="utf-8")
    (artifact / "linked.txt").symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        artifact_sha256(artifact)

    assert outside.read_text(encoding="utf-8") == "must remain unread"


def test_descriptor_hash_rejects_symlinked_parent_component(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "data.bin").write_bytes(b"outside")
    link = tmp_path / "linked-parent"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        artifact_sha256(link / "data.bin")


@pytest.mark.skipif(
    not artifact_digest._DESCRIPTOR_HASHING,
    reason="descriptor no-follow hashing is Unix-specific",
)
def test_descriptor_hash_rejects_link_replacement_during_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"original")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"must remain unread")
    real_open = artifact_digest._open_no_follow
    replaced = False

    def replace_before_open(
        path: str | bytes | Path,
        *,
        directory_fd: int | None = None,
        root: bool = False,
    ) -> int:
        nonlocal replaced
        if not replaced and os.fspath(path) == artifact.name:
            artifact.unlink()
            artifact.symlink_to(outside)
            replaced = True
        return real_open(path, directory_fd=directory_fd, root=root)

    monkeypatch.setattr(artifact_digest, "_open_no_follow", replace_before_open)

    with pytest.raises(ValueError, match="symlink"):
        artifact_sha256(artifact)

    assert outside.read_bytes() == b"must remain unread"
