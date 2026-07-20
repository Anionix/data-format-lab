import json
from pathlib import Path
from typing import Literal

import pytest
import pyarrow as pa

from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.fair import FairOperation
from format_bench.formats import ArrowIpcAdapter
from format_bench.model import Comparability, Lane


DATASET = Path("datasets/github-stars-2026-07-03")


@pytest.fixture
def fixture_contract() -> tuple[dict, pa.Table]:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    manifest["rows"] = table.num_rows
    manifest["canonical_hash"] = canonical_hash(table)
    manifest["expected_counts"] = query_counts(table)
    return manifest, table


def test_arrow_ipc_roundtrip_and_scan(fixture_contract, tmp_path: Path) -> None:
    manifest, table = fixture_contract
    adapter = ArrowIpcAdapter()
    path = tmp_path / "stars.arrow"

    artifact = adapter.encode(table, path)

    assert adapter.describe().lane is Lane.FAIR
    assert adapter.describe().comparability is Comparability.FULL_COMPARABLE
    assert artifact.native_bytes == path.stat().st_size
    assert adapter.verify_roundtrip(path, manifest)["passed"] is True
    assert (
        adapter.scan(path, manifest, FairOperation.FILTER_AI_LLM).num_rows
        == manifest["expected_counts"]["group_ai_llm"]
    )


@pytest.mark.parametrize("compression", ["none", "lz4", "zstd"])
def test_arrow_ipc_compression_variants_preserve_contract(
    fixture_contract,
    tmp_path: Path,
    compression: Literal["none", "lz4", "zstd"],
) -> None:
    manifest, table = fixture_contract
    adapter = ArrowIpcAdapter(compression)
    path = tmp_path / f"{adapter.describe().name}.arrow"

    artifact = adapter.encode(table, path)

    assert adapter.describe().settings["compression"] == compression
    assert artifact.native_bytes == path.stat().st_size
    assert adapter.verify_roundtrip(path, manifest)["passed"] is True
    for operation in FairOperation:
        assert adapter.scan(path, manifest, operation).num_rows >= 0
