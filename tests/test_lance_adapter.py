import json
from pathlib import Path

from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.formats import LanceAdapter, build_fts, lance_components, query_fts


DATASET = Path("datasets/github-stars-2026-07-03")


def fixture_contract():
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    manifest["rows"] = table.num_rows
    manifest["canonical_hash"] = canonical_hash(table)
    manifest["expected_counts"] = query_counts(table)
    return manifest, table


def test_lance_base_roundtrip_and_size_components(tmp_path: Path) -> None:
    manifest, table = fixture_contract()
    adapter = LanceAdapter()
    path = tmp_path / "base.lance"
    artifact = adapter.encode(table, path)
    components = lance_components(path)

    assert adapter.describe().settings["data_storage_version"] == "stable"
    assert artifact.native_bytes == components["logical_directory_bytes"]
    assert components["index_bytes"] == 0
    assert adapter.verify_roundtrip(path, manifest)["passed"] is True


def test_lance_fts_reports_index_and_substring_quality(tmp_path: Path) -> None:
    _, table = fixture_contract()
    path = tmp_path / "fts.lance"
    built = build_fts(table, path)
    measured = query_fts(path, table, "coding agent", warmups=1, iterations=2)

    assert built["index_bytes"] > 0
    assert built["artifact"].native_bytes == built["logical_directory_bytes"]
    assert measured["ground_truth_substring_rows"] == 3
    assert measured["timing"]["samples"] == 2
