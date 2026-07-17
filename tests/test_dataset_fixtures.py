from __future__ import annotations

import json
from pathlib import Path

import pytest

from format_bench.formats.text import CsvAdapter
from format_bench.workflow import prepare_run, verify_run


DATASETS = (
    "uci-online-retail-ii",
    "uci-bank-marketing",
    "nyc-311-2010-2019",
    "owid-energy",
    "geonames-cities500",
)


@pytest.mark.parametrize("dataset_id", DATASETS)
def test_dataset_fixture_roundtrip_uses_declared_workloads(
    tmp_path: Path, dataset_id: str
) -> None:
    root = Path(__file__).parents[1]
    run_dir = prepare_run(
        root,
        dataset_id,
        tmp_path / dataset_id,
        fixture=True,
        selected=(CsvAdapter(),),
    )
    verify_run(run_dir, {"csv": CsvAdapter()})

    manifest = json.loads((run_dir / "input" / "manifest.json").read_text())
    result = json.loads((run_dir / "manifest.json").read_text())
    assert set(manifest["expected_counts"]) == set(manifest["workloads"])
    assert result["state"] == "ROUNDTRIP_VERIFIED"
    assert result["formats"][0]["verification"]["counts"] == manifest["expected_counts"]
