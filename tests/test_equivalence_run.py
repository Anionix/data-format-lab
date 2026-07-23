from __future__ import annotations

import json
from pathlib import Path

import format_bench.equivalence_run as equivalence_run
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
    original_run_jobs = equivalence_run.run_jobs

    def assert_preregistered(*args, **kwargs):
        manifest = json.loads((run_dir / "manifest.json").read_text())
        assert manifest["equivalence"]["contract_version"] == "2"
        assert manifest["equivalence"]["primary_endpoints"] == {
            "csv-tsv": {"scope": "storage", "metric": "native_bytes"}
        }
        control = manifest["equivalence"]["multiplicity_control"]
        assert control["method"] == "bonferroni_simultaneous_intervals"
        assert control["planned_comparisons"] == 7
        assert manifest["measurement"]["estimand"]["targets"]["warm_p50_ms"] == {
            "variable": "per_process_median_post_warmup_elapsed_excluding_validation",
            "unit": "milliseconds",
            "population_summary": "median_across_fresh_processes",
            "estimator": "median_of_per_process_medians",
            "rounding": "3_decimal_places",
            "evidence_field": "warm_process_p50_ms",
            "estimate_field": "warm_process_estimates.median_p50_ms",
        }
        return original_run_jobs(*args, **kwargs)

    monkeypatch.setattr(equivalence_run, "run_jobs", assert_preregistered)

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
    assert manifest["equivalence"]["contract_version"] == "2"
    assert {key: manifest["equivalence"][key] for key in expected} == expected
    assert {key: results["equivalence"][key] for key in expected} == expected
    assert manifest["measurement"]["worker_timeout_seconds"] == 7.5
    assert results["measurement"]["worker_timeout_seconds"] == 7.5
    assert manifest["measurement"]["estimand"] == results["measurement"]["estimand"]


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
