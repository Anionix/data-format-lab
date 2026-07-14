import json
from pathlib import Path

import pytest

from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.formats import ParquetAdapter
from format_bench.model import Comparability, Lane


DATASET = Path("datasets/github-stars-2026-07-03")


@pytest.mark.parametrize("level", [None, 19])
def test_parquet_variants_roundtrip_the_same_table(tmp_path: Path, level: int | None) -> None:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    manifest["rows"] = table.num_rows
    manifest["canonical_hash"] = canonical_hash(table)
    manifest["expected_counts"] = query_counts(table)
    adapter = ParquetAdapter(level)
    path = tmp_path / f"{adapter.describe().name}.parquet"

    artifact = adapter.encode(table, path)
    description = adapter.describe()
    assert description.lane is Lane.FAIR
    assert description.comparability is Comparability.FULL_COMPARABLE
    assert description.settings["level"] == (level or "library-default")
    assert artifact.native_bytes == path.stat().st_size
    assert adapter.verify_roundtrip(path, manifest)["passed"] is True
