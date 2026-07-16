import json
import os
from dataclasses import replace
from pathlib import Path

import format_bench.robustness.native as native
from format_bench.formats.text import CsvAdapter
from format_bench.model import ObservedOutcome, RobustnessVerdict
from format_bench.robustness.native import (
    ARROW_NATIVE_TARGETS,
    FASTLANES_NATIVE_TARGETS,
    NativeTarget,
    NATIVE_TARGETS,
    UNAVAILABLE_NATIVE_TARGETS,
    VORTEX_NATIVE_TARGETS,
    run_native,
)
from format_bench.workflow import prepare_run, verify_run


DATASET = "github-stars-2026-07-03"


def test_native_target_catalog_preserves_official_engine_types() -> None:
    assert [target.official_target for target in VORTEX_NATIVE_TARGETS] == [
        "file_io", "compress_roundtrip"
    ]
    assert all(target.engine == "coverage-guided" for target in VORTEX_NATIVE_TARGETS)
    assert all(target.tier.value == "CORE" for target in ARROW_NATIVE_TARGETS)
    assert all(target.tier.value == "CORE" for target in VORTEX_NATIVE_TARGETS)
    assert all(target.source_commit == "7932e197eaa00577ff3e83ddf956022df3ef174c" for target in ARROW_NATIVE_TARGETS)
    assert all(target.source_commit == "5abaf9823dee973dde7295a6a36234935f08d060" for target in VORTEX_NATIVE_TARGETS)
    assert FASTLANES_NATIVE_TARGETS[0].official_target == "quick_fuzz_test"
    assert FASTLANES_NATIVE_TARGETS[0].engine == "project-seeded"
    assert FASTLANES_NATIVE_TARGETS[0].tier.value == "EXPERIMENTAL"
    assert [target.name for target in UNAVAILABLE_NATIVE_TARGETS] == [
        "lance", "object-jsonl", "tsfile"
    ]
    assert NATIVE_TARGETS[-3:] == UNAVAILABLE_NATIVE_TARGETS


def _verified_fixture(root: Path, run_dir: Path) -> None:
    adapter = CsvAdapter()
    prepare_run(root, DATASET, run_dir, fixture=True, selected=(adapter,))
    verify_run(run_dir, {"csv": adapter})


def _fake_target(build_dir: Path, name: str, body: str) -> None:
    build_dir.mkdir(parents=True)
    path = build_dir / name
    path.write_text(f"#!/usr/bin/env python3\n{body}\n")
    path.chmod(0o755)


def test_native_suite_records_arrow_target_and_process_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    root = Path(__file__).parents[1]
    monkeypatch.chdir(root)
    run_dir = Path(os.path.relpath(tmp_path / "run", root))
    build_dir = tmp_path / "build"
    _verified_fixture(root, run_dir)
    _fake_target(build_dir, "arrow-csv-fuzz", "print('native smoke')")

    result_path = run_native(
        root,
        run_dir,
        duration_seconds=1,
        artifact_budget_mib=4,
        targets=(replace(ARROW_NATIVE_TARGETS[0], source_commit=None),),
        build_dir=build_dir,
    )
    payload = json.loads(result_path.read_text())
    evidence = payload["results"]["robustness_v1"]
    case = evidence["cases"][0]
    assert evidence["suite"] == "native"
    assert evidence["target_summary"]["arrow-csv-fuzz"]["pass"] == 1
    assert evidence["config"]["source_commits"] == {
        "arrow": "7932e197eaa00577ff3e83ddf956022df3ef174c",
        "vortex": "5abaf9823dee973dde7295a6a36234935f08d060",
        "fastlanes": "f0edc1020a538f1f8098640fce8347c9ac247a0d",
    }
    assert case["details"]["official_target"] == "arrow-csv-fuzz"
    assert case["observed"] == ObservedOutcome.ACCEPTED.value
    assert case["verdict"] == RobustnessVerdict.PASS.value
    assert case["process"]["exit_code"] == 0
    assert len(case["details"]["binary_sha256"]) == 64
    assert not Path(case["stdout"]).is_absolute()


def test_native_suite_passes_a_corpus_directory_to_arrow_fuzzer(
    tmp_path: Path, monkeypatch
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "non-fixture-run"
    build_dir = tmp_path / "build"
    _verified_fixture(root, run_dir)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update(fixture=False, rankable=True)
    manifest_path.write_text(json.dumps(manifest))
    _fake_target(build_dir, "parquet-arrow-fuzz", "print('native smoke')")
    commands: list[list[str]] = []

    def fake_process(command, cwd, timeout, output_budget_bytes):
        commands.append(list(command))
        corpus = Path(command[-1])
        assert corpus.is_dir()
        assert [item.name for item in corpus.iterdir()] == ["source.csv"]
        return {"timed_out": False, "signal": None, "exit_code": 0}, "", ""

    monkeypatch.setattr(native, "_process", fake_process)
    target = replace(ARROW_NATIVE_TARGETS[1], source_commit=None)
    result_path = run_native(
        root,
        run_dir,
        duration_seconds=1,
        artifact_budget_mib=4,
        targets=(target,),
        build_dir=build_dir,
    )

    case = json.loads(result_path.read_text())["results"]["robustness_v1"]["cases"][0]
    assert case["details"]["corpus_seed"].endswith("source.csv")
    assert case["details"]["corpus"] == "robustness/native/parquet-arrow-fuzz/corpus"
    assert case["corpus_records"][0]["path"].endswith("/source.csv")


def test_native_suite_keeps_missing_target_as_unsupported(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    _verified_fixture(root, run_dir)
    target = NativeTarget(
        "missing-fuzz", "missing-fuzz", "project-seeded", Path("native/missing"), "missing-fuzz"
    )

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
    assert "unavailable" in case["details"]["reason"]


def test_native_suite_requires_pinned_source_checkout(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    work_dir = tmp_path / "vortex"
    work_dir.mkdir()
    _verified_fixture(root, run_dir)
    target = replace(VORTEX_NATIVE_TARGETS[0], work_dir=work_dir)

    result_path = run_native(
        root,
        run_dir,
        duration_seconds=1,
        artifact_budget_mib=4,
        targets=(target,),
    )
    case = json.loads(result_path.read_text())["results"]["robustness_v1"]["cases"][0]
    assert case["observed"] == ObservedOutcome.UNSUPPORTED.value
    assert "no .git metadata" in case["details"]["reason"]


def test_native_suite_reports_unavailable_formats_without_running_them(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    _verified_fixture(root, run_dir)

    result_path = run_native(
        root,
        run_dir,
        duration_seconds=1,
        artifact_budget_mib=4,
        targets=UNAVAILABLE_NATIVE_TARGETS,
    )
    cases = json.loads(result_path.read_text())["results"]["robustness_v1"]["cases"]
    assert [case["target"] for case in cases] == ["lance", "object-jsonl", "tsfile"]
    assert all(case["observed"] == ObservedOutcome.UNSUPPORTED.value for case in cases)
    assert all(case["verdict"] == RobustnessVerdict.INCOMPLETE.value for case in cases)
    assert all("no confirmed official native fuzz target" in case["details"]["reason"] for case in cases)


def test_native_suite_uses_cargo_fuzz_for_vortex(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "vortex-run"
    work_dir = tmp_path / "vortex"
    work_dir.mkdir()
    _verified_fixture(root, run_dir)
    targets = tuple(
        replace(target, work_dir=work_dir, source_commit=None)
        for target in VORTEX_NATIVE_TARGETS
    )
    commands: list[list[str]] = []

    def fake_process(command, cwd, timeout, output_budget_bytes):
        commands.append(list(command))
        return {"timed_out": False, "signal": None, "exit_code": 0}, "", ""

    monkeypatch.setattr(native, "_process", fake_process)
    result_path = run_native(
        root,
        run_dir,
        duration_seconds=1.1,
        artifact_budget_mib=4,
        targets=targets,
    )

    payload = json.loads(result_path.read_text())
    cases = payload["results"]["robustness_v1"]["cases"]
    assert [case["target"] for case in cases] == [
        "vortex-file-io", "vortex-compress-roundtrip"
    ]
    assert all(case["details"]["engine"] == "coverage-guided" for case in cases)
    command = commands[0]
    assert command[:4] == ["cargo", "fuzz", "run", "file_io"]
    assert command[4] == "--"
    assert "-max_total_time=2" in command
    assert all(not item.startswith("-timeout=") for item in command)
    assert commands[1][:4] == ["cargo", "fuzz", "run", "compress_roundtrip"]


def test_native_suite_uses_gtest_for_fastlanes(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "fastlanes-run"
    work_dir = tmp_path / "fastlanes"
    _verified_fixture(root, run_dir)
    _fake_target(work_dir / "build", "quick_fuzz_test", "print('fastlanes smoke')")
    target = replace(FASTLANES_NATIVE_TARGETS[0], work_dir=work_dir, source_commit=None)
    commands: list[list[str]] = []

    def fake_process(command, cwd, timeout, output_budget_bytes):
        commands.append(list(command))
        return {"timed_out": False, "signal": None, "exit_code": 0}, "", ""

    monkeypatch.setattr(native, "_process", fake_process)
    run_native(root, run_dir, duration_seconds=1, artifact_budget_mib=4, targets=(target,))

    command = commands[0]
    assert command[:3] == [
        str(work_dir / "build/quick_fuzz_test"),
        "--gtest_filter=QuickFuzz_*",
        "--gtest_color=no",
    ]
    assert command[3].startswith("--gtest_output=xml:")
    assert all(not item.startswith("-max_total_time=") for item in command)


def test_native_suite_classifies_project_seeded_target_failure(
    tmp_path: Path, monkeypatch
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "fastlanes-failed-run"
    work_dir = tmp_path / "fastlanes"
    _verified_fixture(root, run_dir)
    _fake_target(work_dir / "build", "quick_fuzz_test", "print('target failed')")
    target = replace(FASTLANES_NATIVE_TARGETS[0], work_dir=work_dir, source_commit=None)

    def fake_process(command, cwd, timeout, output_budget_bytes):
        return {"timed_out": False, "signal": None, "exit_code": 1}, "", "failed"

    monkeypatch.setattr(native, "_process", fake_process)
    result_path = run_native(
        root, run_dir, duration_seconds=1, artifact_budget_mib=4, targets=(target,)
    )

    case = json.loads(result_path.read_text())["results"]["robustness_v1"]["cases"][0]
    assert case["observed"] == ObservedOutcome.TARGET_FAILED.value
    assert case["verdict"] == RobustnessVerdict.FAIL.value
    assert case["process"]["exit_code"] == 1


def test_native_suite_rejects_manifest_corpus_traversal(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    build_dir = tmp_path / "build"
    _verified_fixture(root, run_dir)
    _fake_target(build_dir, "arrow-csv-fuzz", "print('should not run')")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["input"]["source"] = "../outside.csv"
    manifest_path.write_text(json.dumps(manifest))

    result_path = run_native(
        root,
        run_dir,
        duration_seconds=1,
        artifact_budget_mib=4,
        targets=(replace(ARROW_NATIVE_TARGETS[0], source_commit=None),),
        build_dir=build_dir,
    )
    case = json.loads(result_path.read_text())["results"]["robustness_v1"]["cases"][0]
    assert case["observed"] == "HARNESS_FAILED"
    assert "safe and relative" in case["details"]["reason"]


def test_native_suite_rejects_symlinked_binary(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    build_dir = tmp_path / "build"
    outside = tmp_path / "outside" / "fuzz"
    _verified_fixture(root, run_dir)
    _fake_target(outside.parent, outside.name, "print('must not run')")
    build_dir.mkdir()
    (build_dir / "arrow-csv-fuzz").symlink_to(outside)

    result_path = run_native(
        root,
        run_dir,
        duration_seconds=1,
        artifact_budget_mib=4,
        targets=(replace(ARROW_NATIVE_TARGETS[0], source_commit=None),),
        build_dir=build_dir,
    )
    case = json.loads(result_path.read_text())["results"]["robustness_v1"]["cases"][0]
    assert case["observed"] == ObservedOutcome.UNSUPPORTED.value
    assert "unavailable" in case["details"]["reason"]
