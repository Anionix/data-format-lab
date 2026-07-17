import json
from pathlib import Path

import pyarrow as pa
import pytest

from format_bench.canonical import canonical_hash, load_dataset, query_counts, read_csv
from format_bench.datasets import sha256_bytes
from format_bench.interop import run_arrow_ipc_interoperability
from format_bench.workflow import _fixture_manifest


DATASET = Path("datasets/github-stars-2026-07-03")


def test_arrow_ipc_independent_consumer_records_contract_and_controls(tmp_path: Path) -> None:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    manifest.update(
        rows=table.num_rows,
        canonical_hash=canonical_hash(table),
        expected_counts=query_counts(table),
    )

    evidence_path = run_arrow_ipc_interoperability(table, manifest, tmp_path / "evidence")
    evidence = json.loads(evidence_path.read_text())

    assert evidence["contract_version"] == "1"
    assert evidence["environment"]["hardware_model"]
    assert [item["status"] for item in evidence["variants"]] == ["PASS"] * 3
    assert all(item["artifact_sha256"] for item in evidence["variants"])
    assert all(item["canonical_hash"] == manifest["canonical_hash"] for item in evidence["variants"])
    assert all(item["expected_counts"] == manifest["expected_counts"] for item in evidence["variants"])
    assert [item["status"] for item in evidence["negative_cases"]] == ["FAILED", "FAILED"]
    report = (tmp_path / "evidence" / "arrow-ipc-interoperability.md").read_text()
    assert "independent-consumer" in report
    assert "cross-language matrix" in report


def test_interoperability_evidence_has_exact_null_positions(tmp_path: Path) -> None:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    base = read_csv(DATASET / "fixture.csv", manifest)
    table = base.set_column(
        0,
        "group",
        pa.array([None, *base["group"].to_pylist()[1:]], type=pa.string()),
    )
    manifest.update(
        rows=table.num_rows,
        canonical_hash=canonical_hash(table),
        expected_counts=query_counts(table),
    )

    evidence = json.loads(
        run_arrow_ipc_interoperability(table, manifest, tmp_path / "evidence").read_text()
    )

    assert evidence["variants"][0]["null_positions"]["group"] == [0]


def test_interoperability_output_cannot_be_reused(tmp_path: Path) -> None:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    manifest.update(
        rows=table.num_rows,
        canonical_hash=canonical_hash(table),
        expected_counts=query_counts(table),
    )
    output = tmp_path / "evidence"

    run_arrow_ipc_interoperability(table, manifest, output)

    with pytest.raises(FileExistsError, match="already exists"):
        run_arrow_ipc_interoperability(table, manifest, output)


def test_load_dataset_rejects_modified_production_source(tmp_path: Path) -> None:
    root = tmp_path / "root"
    dataset = root / "datasets" / "fixture"
    source_dir = root / ".data" / "fixture"
    dataset.mkdir(parents=True)
    source_dir.mkdir(parents=True)
    manifest = json.loads((DATASET / "manifest.json").read_text())
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    source = source_dir / "source.csv"
    source.write_text("changed\n")

    with pytest.raises(ValueError, match="source SHA-256 mismatch"):
        load_dataset(root, "fixture")


def test_fixture_manifest_records_effective_source_provenance() -> None:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    source = DATASET / "fixture.csv"
    table = read_csv(source, manifest)

    effective = _fixture_manifest(manifest, table, source)

    assert effective["fixture"] is True
    assert effective["source_sha256"] == sha256_bytes(source.read_bytes())
