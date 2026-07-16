import json
from pathlib import Path

import pytest

import format_bench.robustness.profile as robustness_profile
from format_bench import cli
from format_bench.formats.text import CsvAdapter
from format_bench.robustness.profile import _mutate, run_bounded
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
        "PASS": 4,
    }
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
