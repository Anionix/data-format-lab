import json
from pathlib import Path

from format_bench.formats.text import CsvAdapter
from format_bench.profile_run import run_claims, run_prompt
from format_bench.workflow import prepare_run, verify_run


def _fixture_run(root: Path, destination: Path) -> Path:
    adapter = CsvAdapter()
    prepare_run(
        root,
        "github-stars-2026-07-03",
        destination,
        fixture=True,
        selected=[adapter],
    )
    verify_run(destination, {"csv": adapter})
    return destination


def test_prompt_run_records_exact_metrics_and_relative_artifacts(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    path = run_prompt(root, _fixture_run(root, tmp_path / "prompt-run"))
    result = json.loads(path.read_text())["results"]["prompt_v1"]
    assert result["state"] == "BENCHMARKED"
    assert set(result["metrics"]["corpus"]) == {
        "compact_tsv",
        "object_jsonl",
        "array_jsonl",
    }
    assert all(not Path(value).is_absolute() for value in result["artifacts"].values())


def test_claim_run_isolates_each_claim_and_negative_record(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = _fixture_run(root, tmp_path / "claims-run")
    path = run_claims(
        root,
        run_dir,
        stress_rows=8,
        ts_devices=2,
        ts_points=10,
        warmups=0,
        iterations=1,
    )
    results = json.loads(path.read_text())["results"]
    assert results["lance_fts"]["state"] == "BENCHMARKED"
    assert results["vortex_stress"]["state"] == "BENCHMARKED"
    assert results["tsfile_time_series"]["state"] in {"BENCHMARKED", "UNSUPPORTED"}
    assert set(results["negative_research"]) == {"anyblox", "fastlanes", "nimble"}
