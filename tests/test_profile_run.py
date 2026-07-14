import json
from pathlib import Path

import format_bench.profile_run as profile_run
from format_bench.formats.text import CsvAdapter
from format_bench.model import Comparability, TargetTier
from format_bench.profile_run import _attempt, run_claims, run_prompt
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


def test_claim_run_isolates_each_claim_and_negative_record(
    tmp_path: Path, monkeypatch
) -> None:
    root = Path(__file__).parents[1]
    run_dir = _fixture_run(root, tmp_path / "claims-run")
    monkeypatch.setattr(
        profile_run,
        "run_fastlanes_claim",
        lambda *args, **kwargs: {
            "status": "MEASURED",
            "numeric": {"rows": 1024},
            "summary": "numeric=ROUNDTRIP_EQUAL",
        },
    )
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
    assert results["tsfile_time_series"]["comparability"] == Comparability.ADAPTED
    assert results["tsfile_time_series"]["target_tier"] == TargetTier.EXPERIMENTAL
    assert results["fastlanes_official"]["state"] == "BENCHMARKED"
    assert results["fastlanes_official"]["comparability"] == Comparability.PARTIAL
    assert results["fastlanes_official"]["target_tier"] == TargetTier.EXPERIMENTAL
    assert results["fastlanes_official"]["evidence"]["summary"] == "numeric=ROUNDTRIP_EQUAL"
    assert set(results["negative_research"]) == {"anyblox", "fastlanes", "nimble"}


def test_claim_returned_failure_stays_terminal() -> None:
    result = _attempt(
        Comparability.FULL_COMPARABLE,
        lambda: {"status": "FAILED", "reason": "result mismatch"},
    )
    assert result["state"] == "FAILED"
    assert result["failure_reason"] == "result mismatch"
