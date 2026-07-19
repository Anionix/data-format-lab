import json
from pathlib import Path

import pytest

import format_bench.robustness.profile as robustness_profile
from format_bench import cli
from format_bench.formats.text import CsvAdapter
from format_bench.robustness.profile import (
    _execute,
    _mutate,
    run_bounded,
)
from format_bench.robustness.evidence import EvidenceStore
from format_bench.model import (
    ObservedOutcome,
    RobustnessExpectation,
    RobustnessVerdict,
)
from format_bench.canonical import read_csv
from format_bench.robustness.targets import core_targets
from format_bench.workflow import prepare_run, verify_run


DATASET = "github-stars-2026-07-03"


def test_bounded_fixture_writes_versioned_evidence(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    adapter = CsvAdapter()
    prepare_run(root, DATASET, run_dir, fixture=True, selected=(adapter,))
    verify_run(run_dir, {"csv": adapter})

    result_path = run_bounded(
        root,
        run_dir,
        generated_count=0,
        mutations_per_target=1,
        targets=(core_targets()[0],),
    )
    results = json.loads(result_path.read_text())
    evidence = results["results"]["robustness_v1"]
    assert results["schema_version"] == evidence["contract_version"] == "1"
    assert evidence["state"] == "BENCHMARKED"
    assert evidence["summary"] == {
        "FAIL": 0,
        "INCOMPLETE": 0,
        "NOT_APPLICABLE": 0,
        "PASS": 11,
    }
    assert evidence["target_summary"]["csv"]["cases"] == 11
    assert evidence["target_summary"]["csv"]["applicable"] == 11
    assert evidence["target_summary"]["csv"]["pass"] == 11
    assert evidence["target_summary"]["csv"]["artifact_sha256"]
    assert all(
        {
            "schema_version",
            "contract_version",
            "expectation",
            "observed",
            "verdict",
        }
        <= item.keys()
        for item in evidence["cases"]
    )
    valid = next(item for item in evidence["cases"] if item["case_id"] == "rows-1")
    assert len(valid["input_canonical_hash"]) == 64
    assert len(valid["input_arrow"]["sha256"]) == 64
    assert all(len(record["sha256"]) == 64 for record in valid["artifact_records"])
    mutated = next(
        item for item in evidence["cases"] if item["case_id"].startswith("mutation-")
    )
    assert mutated["case_id"] == "mutation-000-empty"
    assert mutated["mutation"]["member_size_bytes"] > 1


def test_bounded_fixture_includes_each_named_boundary_family(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    adapter = CsvAdapter()
    prepare_run(root, DATASET, run_dir, fixture=True, selected=(adapter,))
    verify_run(run_dir, {"csv": adapter})

    result_path = run_bounded(
        root,
        run_dir,
        generated_count=0,
        mutations_per_target=0,
        targets=(core_targets()[0],),
    )
    case_ids = {
        item["case_id"]
        for item in json.loads(result_path.read_text())["results"]["robustness_v1"]["cases"]
    }

    assert {
        "rows-0",
        "rows-2049",
        "dictionary-256",
        "null-all",
        "string-utf8",
        "numeric-int64",
        "malformed-missing-column",
        "malformed-truncated",
    } <= case_ids


def test_public_cli_runs_and_reports_bounded_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    csv_target = core_targets()[0]
    monkeypatch.setattr(robustness_profile, "core_targets", lambda: (csv_target,))
    monkeypatch.chdir(root)
    cli.main(
        [
            "run", "--profile", "robustness", "--suite", "bounded",
            "--dataset", DATASET, "--run-dir", str(run_dir), "--fixture",
            "--seed", "7", "--generated-cases", "0", "--mutations-per-target", "1",
            "--case-timeout-seconds", "5", "--artifact-budget-mib", "64",
        ]
    )
    results = json.loads((run_dir / "results.json").read_text())
    evidence = results["results"]["robustness_v1"]
    assert results["profile"] == "robustness"
    assert evidence["contract_version"] == "1"
    assert evidence["config"]["seed"] == 7
    assert evidence["config"]["generated_cases"] == 0
    assert evidence["config"]["mutations_per_target"] == 1
    assert evidence["config"]["case_timeout_seconds"] == 5
    assert evidence["config"]["artifact_budget_mib"] == 64
    valid = next(item for item in evidence["cases"] if "input_arrow" in item)
    assert not Path(valid["input_arrow"]["path"]).is_absolute()
    cli.main(["report", "--run-dir", str(run_dir)])
    first = (run_dir / "report.md").read_text()
    cli.main(["report", "--run-dir", str(run_dir)])
    assert (run_dir / "report.md").read_text() == first


def test_bounded_resolves_relative_run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).parents[1]
    absolute_run = tmp_path / "relative-run"
    adapter = CsvAdapter()
    prepare_run(root, DATASET, absolute_run, fixture=True, selected=(adapter,))
    verify_run(absolute_run, {"csv": adapter})
    monkeypatch.chdir(tmp_path)

    result_path = run_bounded(
        root,
        Path("relative-run"),
        generated_count=0,
        mutations_per_target=0,
        targets=(core_targets()[0],),
    )

    assert result_path == absolute_run / "results.json"
    assert result_path.is_file()


def test_mutation_uses_actual_member_size_and_rejects_links(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(bytes(range(256)))
    recipe, member, digests = _mutate(artifact, 20260703, 7, 3)
    assert recipe.operation == "flip_middle"
    assert 96 <= recipe.options["offset"] < 160
    assert member == "artifact.bin"
    assert digests["before_sha256"] != digests["after_sha256"]

    directory = tmp_path / "directory"
    directory.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"unchanged")
    (directory / "linked.bin").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        _mutate(directory, 1, 1, 0)
    assert outside.read_bytes() == b"unchanged"
    with pytest.raises(ValueError, match="non-negative"):
        run_bounded(tmp_path, tmp_path, mutations_per_target=-1)


def test_worker_output_budget_leaves_room_for_case_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    target = core_targets()[0]
    prepare_run(root, DATASET, run_dir, fixture=True, selected=(target.adapter,))
    dataset = json.loads((run_dir / "input/manifest.json").read_text())
    table = read_csv(run_dir / "input/source.csv", dataset)
    store = EvidenceStore(run_dir / "robustness", 64 * 1024)

    def noisy_case(
        case_root: Path,
        request: str,
        output_dir: str,
        timeout: float,
        command=None,
        output_budget_bytes: int | None = None,
    ) -> dict:
        assert output_budget_bytes is not None
        assert output_budget_bytes < store.budget_bytes - store.used_bytes
        output = case_root / output_dir
        output.mkdir(parents=True, exist_ok=True)
        (output / "stdout.txt").write_bytes(b"x" * output_budget_bytes)
        (output / "stderr.txt").write_bytes(b"")
        return {
            "case_id": "budget-boundary",
            "target": target.name,
            "expectation": RobustnessExpectation.MUST_ROUNDTRIP,
            "observed": ObservedOutcome.BUDGET_EXHAUSTED,
            "verdict": RobustnessVerdict.INCOMPLETE,
            "details": {},
            "process": {
                "exit_code": 0,
                "signal": None,
                "timed_out": False,
                "duration_ms": 0.0,
                "stdout_bytes": output_budget_bytes,
                "stderr_bytes": 0,
                "stdout_truncated": True,
                "stderr_truncated": False,
                "output_budget_bytes": output_budget_bytes,
                "output_exhausted": True,
            },
            "stdout": (output / "stdout.txt").relative_to(case_root).as_posix(),
            "stderr": (output / "stderr.txt").relative_to(case_root).as_posix(),
        }

    monkeypatch.setattr("format_bench.robustness.profile.run_case", noisy_case)
    result = _execute(
        run_dir,
        store,
        target,
        "budget-boundary",
        RobustnessExpectation.MUST_ROUNDTRIP,
        table,
        dataset,
        1.0,
    )

    result_path = store.root / "cases" / target.name / "budget-boundary" / "result.json"
    assert result["observed"] is ObservedOutcome.BUDGET_EXHAUSTED
    assert result_path.is_file()
    assert store.used_bytes <= store.budget_bytes


def test_budget_exhaustion_keeps_later_cases_runnable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    target = core_targets()[0]
    prepare_run(root, DATASET, run_dir, fixture=True, selected=(target.adapter,))
    verify_run(run_dir, {target.name: target.adapter})
    first = robustness_profile.CaseSpec(
        "rows-1", "rows", robustness_profile.RobustnessExpectation.MUST_ROUNDTRIP,
        (("rows", 1),),
    )
    later = robustness_profile.CaseSpec(
        "generated-000-later", "rows", robustness_profile.RobustnessExpectation.MUST_ROUNDTRIP,
        (("rows", 1),),
    )
    monkeypatch.setattr(robustness_profile, "named_cases", lambda: (first,))
    monkeypatch.setattr(robustness_profile, "generated_cases", lambda seed, count: (later,))
    output_bytes = 128
    calls: list[str] = []
    monkeypatch.setattr(
        robustness_profile, "_PER_CASE_OUTPUT_BUDGET_BYTES", output_bytes
    )

    def noisy_case(
        case_root: Path,
        request: str,
        output_dir: str,
        timeout: float,
        command=None,
        output_budget_bytes: int | None = None,
    ) -> dict:
        del timeout, command
        assert output_budget_bytes == output_bytes
        request_payload = json.loads((case_root / request).read_text())
        calls.append(request_payload["case_id"])
        output = case_root / output_dir
        output.mkdir(parents=True, exist_ok=True)
        (output / "stdout.txt").write_bytes(b"x" * output_budget_bytes)
        (output / "stderr.txt").write_bytes(b"")
        return {
            "case_id": request_payload["case_id"],
            "target": target.name,
            "expectation": "MUST_ROUNDTRIP",
            "observed": ObservedOutcome.BUDGET_EXHAUSTED,
            "verdict": RobustnessVerdict.INCOMPLETE,
            "details": {},
            "process": {},
            "stdout": (Path(output_dir) / "stdout.txt").as_posix(),
            "stderr": (Path(output_dir) / "stderr.txt").as_posix(),
        }

    monkeypatch.setattr(robustness_profile, "run_case", noisy_case)
    result_path = run_bounded(
        root,
        run_dir,
        generated_count=0,
        mutations_per_target=0,
        targets=(target,),
        artifact_budget_mib=4,
    )
    cases = json.loads(result_path.read_text())["results"]["robustness_v1"]["cases"]

    assert calls == ["rows-1", "generated-000-later"]
    assert [case["observed"] for case in cases] == ["BUDGET_EXHAUSTED"] * 2
    assert all(
        (run_dir / "robustness" / "cases" / target.name / case / "result.json").is_file()
        for case in calls
    )
