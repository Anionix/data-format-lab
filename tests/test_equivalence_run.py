from __future__ import annotations

import json
from pathlib import Path

from format_bench.equivalence_run import run_equivalence
from format_bench.formats.text import CsvAdapter, TsvAdapter
from format_bench.runner import MeasurementConfig
from format_bench.workflow import prepare_run, verify_run


def test_equivalence_records_parallel_worker_counts_in_manifest_and_results(
    tmp_path: Path, monkeypatch
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "fixture-run"
    adapters = [CsvAdapter(), TsvAdapter()]
    prepare_run(
        root,
        "github-stars-2026-07-03",
        run_dir,
        fixture=True,
        selected=adapters,
    )
    verify_run(run_dir, {adapter.describe().name: adapter for adapter in adapters})
    monkeypatch.setenv("FORMAT_BENCH_MAX_WORKERS", "2")

    result_path = run_equivalence(
        root,
        run_dir,
        pairs=("csv-tsv",),
        config=MeasurementConfig(
            fresh_processes=1, warmups=0, iterations=1, timeout_seconds=7.5
        ),
        parallel=True,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text())
    results = json.loads(result_path.read_text())
    expected = {"requested_workers": 2, "effective_workers": 2}
    assert {key: manifest["equivalence"][key] for key in expected} == expected
    assert {key: results["equivalence"][key] for key in expected} == expected
    assert manifest["measurement"]["worker_timeout_seconds"] == 7.5
    assert results["measurement"]["worker_timeout_seconds"] == 7.5


def test_unavailable_parquet_orc_still_reports_accepted_risk(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "fixture-run"
    adapters = [CsvAdapter(), TsvAdapter()]
    prepare_run(
        root,
        "github-stars-2026-07-03",
        run_dir,
        fixture=True,
        selected=adapters,
    )
    verify_run(run_dir, {adapter.describe().name: adapter for adapter in adapters})

    result_path = run_equivalence(root, run_dir, pairs=("parquet-orc",))

    pair = json.loads(result_path.read_text())["equivalence"]["pairs"]["parquet-orc"]
    assert pair["comparison_scope"] == "configured_system"
    assert pair["execution_plan"]["orc_zlib"]["predicate_pushdown"] is False
    assert pair["writer_plan"]["parquet_default"]["compression"] == "zstd"
    assert pair["writer_plan"]["orc_zlib"]["compression"] == "zlib"
    assert "predicate" in pair["accepted_risk"]
