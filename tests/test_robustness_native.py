import json
from pathlib import Path

from format_bench.formats.text import CsvAdapter
from format_bench.model import ObservedOutcome, RobustnessVerdict
from format_bench.robustness.native import (
    ARROW_NATIVE_TARGETS,
    NativeTarget,
    run_native,
)
from format_bench.workflow import prepare_run, verify_run


DATASET = "github-stars-2026-07-03"


def _verified_fixture(root: Path, run_dir: Path) -> None:
    adapter = CsvAdapter()
    prepare_run(root, DATASET, run_dir, fixture=True, selected=(adapter,))
    verify_run(run_dir, {"csv": adapter})


def _fake_target(build_dir: Path, name: str, body: str) -> None:
    build_dir.mkdir(parents=True)
    path = build_dir / name
    path.write_text(f"#!/usr/bin/env python3\n{body}\n")
    path.chmod(0o755)


def test_native_suite_records_arrow_target_and_process_evidence(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    build_dir = tmp_path / "build"
    _verified_fixture(root, run_dir)
    _fake_target(build_dir, "arrow-csv-fuzz", "print('native smoke')")

    result_path = run_native(
        root,
        run_dir,
        duration_seconds=1,
        artifact_budget_mib=4,
        targets=(ARROW_NATIVE_TARGETS[0],),
        build_dir=build_dir,
    )
    payload = json.loads(result_path.read_text())
    evidence = payload["results"]["robustness_v1"]
    case = evidence["cases"][0]
    assert evidence["suite"] == "native"
    assert evidence["config"]["source_commit"] == (
        "7932e197eaa00577ff3e83ddf956022df3ef174c"
    )
    assert case["details"]["official_target"] == "arrow-csv-fuzz"
    assert case["observed"] == ObservedOutcome.ACCEPTED.value
    assert case["verdict"] == RobustnessVerdict.PASS.value
    assert case["process"]["exit_code"] == 0
    assert not Path(case["stdout"]).is_absolute()


def test_native_suite_keeps_missing_target_as_unsupported(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    _verified_fixture(root, run_dir)
    target = NativeTarget("missing-fuzz", "missing-fuzz")

    result_path = run_native(
        root,
        run_dir,
        duration_seconds=1,
        artifact_budget_mib=4,
        targets=(target,),
        build_dir=tmp_path / "empty-build",
    )
    case = json.loads(result_path.read_text())["results"]["robustness_v1"]["cases"][0]
    assert case["observed"] == ObservedOutcome.UNSUPPORTED.value
    assert case["verdict"] == RobustnessVerdict.INCOMPLETE.value
    assert "not found" in case["details"]["reason"]
