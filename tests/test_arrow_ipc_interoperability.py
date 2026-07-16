import json
from pathlib import Path

import pyarrow as pa

from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.interop import run_arrow_ipc_interoperability


DATASET = Path("datasets/github-stars-2026-07-03")


def test_arrow_ipc_independent_consumer_records_contract_and_controls(tmp_path: Path) -> None:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    manifest.update(
        rows=table.num_rows,
        canonical_hash=canonical_hash(table),
        expected_counts=query_counts(table),
    )

    evidence_path = run_arrow_ipc_interoperability(table, manifest, tmp_path)
    evidence = json.loads(evidence_path.read_text())

    assert evidence["contract_version"] == "1"
    assert [item["status"] for item in evidence["variants"]] == ["PASS"] * 3
    assert all(item["artifact_sha256"] for item in evidence["variants"])
    assert all(item["canonical_hash"] == manifest["canonical_hash"] for item in evidence["variants"])
    assert all(item["expected_counts"] == manifest["expected_counts"] for item in evidence["variants"])
    assert [item["status"] for item in evidence["negative_cases"]] == ["FAILED", "FAILED"]
    report = (tmp_path / "arrow-ipc-interoperability.md").read_text()
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

    evidence = json.loads(run_arrow_ipc_interoperability(table, manifest, tmp_path).read_text())

    assert evidence["variants"][0]["null_positions"]["group"] == [0]
