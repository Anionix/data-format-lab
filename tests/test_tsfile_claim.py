from pathlib import Path

import pytest

from format_bench.claims import run_tsfile_claim


def test_tsfile_claim_matches_parquet_results(tmp_path: Path) -> None:
    pytest.importorskip("tsfile", reason="install the pinned wheel with --no-deps")
    result = run_tsfile_claim(
        tmp_path, devices=2, points_per_device=10, warmups=0, iterations=1
    )

    assert result["status"] == "MEASURED"
    assert result["rows"] == 20
    assert result["timing"]["tsfile"]["result"] == 1
    assert result["timing"]["parquet"]["result"] == 1
    assert result["bytes"]["tsfile"] > 0
