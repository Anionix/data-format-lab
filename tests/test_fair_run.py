import json
from pathlib import Path

from format_bench.formats.text import CsvAdapter
from format_bench.fair_run import run_fair
from format_bench.runner import MeasurementConfig
from format_bench.workflow import prepare_run, verify_run


def test_fair_run_uses_fresh_workers_and_advances_state(tmp_path: Path) -> None:
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
    assert manifest["formats"][0]["state"] == "BENCHMARKED"
