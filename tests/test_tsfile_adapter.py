import json
from pathlib import Path

import pytest

from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.formats import TsFileAdapter
from format_bench.model import Comparability


DATASET = Path("datasets/github-stars-2026-07-03")


def test_tsfile_adapted_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("tsfile", reason="install the pinned wheel with --no-deps")
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    manifest["rows"] = table.num_rows
    manifest["canonical_hash"] = canonical_hash(table)
    manifest["expected_counts"] = query_counts(table)
    adapter = TsFileAdapter()
    path = tmp_path / "fixture.tsfile"

    artifact = adapter.encode(table, path)
    assert adapter.describe().comparability is Comparability.ADAPTED
    assert artifact.native_bytes == path.stat().st_size
    assert adapter.verify_roundtrip(path, manifest)["passed"] is True
