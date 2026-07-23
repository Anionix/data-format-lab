import json
from pathlib import Path

from format_bench.formats.text import CsvAdapter, TsvAdapter
from format_bench.fair_run import run_fair
from format_bench.runner import MeasurementConfig
import format_bench.fair_run as fair_run_module
from format_bench.workflow import prepare_run, verify_run


def test_fair_run_uses_fresh_workers_and_advances_state(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "fixture-run"
    adapter = CsvAdapter()
    prepare_run(
        root,
        "github-stars-2026-07-03",
        run_dir,
        fixture=True,
        selected=[adapter],
    )
    verify_run(run_dir, {"csv": adapter})
    original_run_jobs = fair_run_module.run_jobs

    def assert_preregistered(*args, **kwargs):
        manifest = json.loads((run_dir / "manifest.json").read_text())
        assert (
            manifest["measurement"]["estimand"]["targets"]["fresh_p50_ms"]["variable"]
            == "first_invocation_elapsed_excluding_validation"
        )
        return original_run_jobs(*args, **kwargs)

    monkeypatch.setattr(fair_run_module, "run_jobs", assert_preregistered)

    result_path = run_fair(
        root,
        run_dir,
        MeasurementConfig(fresh_processes=2, warmups=1, iterations=2),
    )
    results = json.loads(result_path.read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert results["state"] == "BENCHMARKED"
    assert len(results["results"]) == 6
    assert all(item["status"] == "MEASURED" for item in results["results"].values())
    assert all(item["fresh_process"]["samples"] == 2 for item in results["results"].values())
    assert all(item["warm"]["samples"] == 4 for item in results["results"].values())
    assert all(item["evidence"]["normalized_hash"] for item in results["results"].values())
    assert results["measurement"]["timeout_seconds"] == 120
    assert results["measurement"]["worker_timeout_seconds"] == 120
    assert manifest["measurement"]["worker_timeout_seconds"] == 120
    assert manifest["measurement"]["estimand"] == results["measurement"]["estimand"]
    assert manifest["formats"][0]["state"] == "BENCHMARKED"


def test_fair_run_records_explicit_worker_timeout(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "fixture-run"
    adapter = CsvAdapter()
    prepare_run(root, "github-stars-2026-07-03", run_dir, fixture=True, selected=[adapter])
    verify_run(run_dir, {"csv": adapter})

    result_path = run_fair(
        root,
        run_dir,
        MeasurementConfig(fresh_processes=1, warmups=0, iterations=1, timeout_seconds=7.5),
    )
    results = json.loads(result_path.read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert results["measurement"]["worker_timeout_seconds"] == 7.5
    assert results["measurement"]["timeout_seconds"] == 7.5
    assert manifest["measurement"]["worker_timeout_seconds"] == 7.5


def test_fair_run_does_not_report_failed_worker_as_benchmarked(
    tmp_path: Path, monkeypatch
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "fixture-run"
    adapter = CsvAdapter()
    prepare_run(root, "github-stars-2026-07-03", run_dir, fixture=True, selected=[adapter])
    verify_run(run_dir, {"csv": adapter})
    monkeypatch.setattr(
        fair_run_module,
        "run_jobs",
        lambda jobs, config, cwd: {job.job_id: {"status": "FAILED", "reason": "boom"} for job in jobs},
    )

    result_path = fair_run_module.run_fair(root, run_dir)
    results = json.loads(result_path.read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert results["state"] == "FAILED"
    assert manifest["state"] == "FAILED"


def test_fair_run_excludes_equivalence_lane_adapters(tmp_path: Path) -> None:
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

    result_path = run_fair(
        root,
        run_dir,
        MeasurementConfig(fresh_processes=1, warmups=0, iterations=1),
    )
    results = json.loads(result_path.read_text())
    assert all(job_id.startswith("csv/") for job_id in results["results"])
