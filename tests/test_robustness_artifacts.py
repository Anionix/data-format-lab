from pathlib import Path

import pytest

from format_bench.robustness import (
    ArtifactBudgetExceeded,
    EvidenceStore,
    apply_mutation,
    mutation_recipes,
)


def test_mutation_recipes_are_deterministic_and_cover_operations() -> None:
    first = mutation_recipes(256, 20260703, 14)
    assert first == mutation_recipes(256, 20260703, 14)
    assert first != mutation_recipes(256, 20260704, 14)
    assert {recipe.operation for recipe in first} == {
        "empty",
        "truncate",
        "flip_header",
        "flip_middle",
        "flip_footer",
        "zero_range",
        "append",
    }
    assert all(isinstance(apply_mutation(bytes(range(256)), recipe), bytes) for recipe in first)


def test_evidence_store_records_relative_paths_digests_and_budget(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "evidence", budget_bytes=4)
    record = store.store_bytes("cases/one/input.bin", b"abc")
    assert record.relative_path == "cases/one/input.bin"
    assert record.size_bytes == 3
    assert len(record.sha256) == 64
    with pytest.raises(ArtifactBudgetExceeded, match="remaining 1"):
        store.store_bytes("cases/two/input.bin", b"de")
    assert store.used_bytes == 3
    assert (store.root / record.relative_path).read_bytes() == b"abc"
    reopened = EvidenceStore(store.root, budget_bytes=4)
    assert reopened.used_bytes == 3
    with pytest.raises(ArtifactBudgetExceeded, match="remaining 1"):
        reopened.store_bytes("cases/three/input.bin", b"de")


def test_evidence_store_imports_file_and_directory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "data.bin").write_bytes(b"data")
    (source / "meta.json").write_bytes(b"{}")
    store = EvidenceStore(tmp_path / "evidence", budget_bytes=10)
    records = store.import_path(source, "cases/lance/artifact")
    assert [record.relative_path for record in records] == [
        "cases/lance/artifact/data.bin",
        "cases/lance/artifact/meta.json",
    ]
    assert store.used_bytes == 6


def test_evidence_store_rejects_unsafe_paths_and_symlinks(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "evidence", budget_bytes=100)
    with pytest.raises(ValueError, match="safe relative"):
        store.store_bytes("../outside", b"x")
    source = tmp_path / "source"
    source.mkdir()
    (source / "link").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="symlinks"):
        store.import_path(source, "case/artifact")


def test_invalid_mutation_arguments_and_operations_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        mutation_recipes(-1, 1, 1)
    recipe = mutation_recipes(1, 1, 1)[0]
    unknown = type(recipe)("bad", "unknown")
    with pytest.raises(ValueError, match="unknown mutation"):
        apply_mutation(b"x", unknown)
