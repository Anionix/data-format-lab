import sys
from pathlib import Path
from types import ModuleType

import pyarrow as pa
import pytest

import format_bench.claims.tsfile as tsfile_claim
from format_bench.claims import run_tsfile_claim
from format_bench.fair import FairOperation, result_evidence


def test_tsfile_claim_matches_parquet_results(tmp_path: Path) -> None:
    pytest.importorskip("tsfile", reason="install the pinned wheel with --no-deps")
    result = run_tsfile_claim(
        tmp_path, devices=2, points_per_device=10, warmups=0, iterations=1
    )

    assert result["status"] == "MEASURED"
    assert result["rows"] == 20
    assert result["timing"]["tsfile"]["result"] == 1
    assert result["timing"]["parquet"]["result"] == 1
    assert result["evidence"]["tsfile"] == result["evidence"]["parquet"]
    assert result["evidence"]["tsfile"]["rows"] == 1
    assert result["evidence"]["tsfile"]["normalized_hash"]
    assert result["bytes"]["tsfile"] > 0
    assert result["writer_settings"]["tsfile"]["default_compression_type_"] == "LZ4"
    assert result["writer_settings"]["tsfile"]["time_encoding_type_"] == "TS_2DIFF"
    assert result["writer_settings"]["parquet"] == {
        "compression": "zstd",
        "row_group_size": 10,
    }


def test_tsfile_claim_rejects_equal_counts_with_different_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_tsfile = ModuleType("tsfile")
    fake_tsfile.TsFileReader = object
    fake_tsfile.tag_eq = lambda *_: None
    monkeypatch.setitem(sys.modules, "tsfile", fake_tsfile)

    def fake_write(tsfile_path: Path, parquet_path: Path, *_: int):
        tsfile_path.write_bytes(b"tsfile")
        parquet_path.write_bytes(b"parquet")
        return {"tsfile": 0.0, "parquet": 0.0}, {}

    original = result_evidence(pa.table({"value": [1]}), FairOperation.READ_ALL)
    changed = result_evidence(pa.table({"value": [2]}), FairOperation.READ_ALL)
    measurements = iter(
        [
            {"timing": {}, "result": 1, "evidence": original},
            {"timing": {}, "result": 1, "evidence": changed},
        ]
    )
    monkeypatch.setattr(tsfile_claim, "_write_datasets", fake_write)
    monkeypatch.setattr(tsfile_claim, "_measure", lambda *_: next(measurements))

    result = tsfile_claim.run_tsfile_claim(
        tmp_path, devices=1, points_per_device=1, warmups=0, iterations=1
    )

    assert result["status"] == "FAILED"
