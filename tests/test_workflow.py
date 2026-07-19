import json
import shutil
from pathlib import Path

import pyarrow as pa
import pytest

from format_bench import cli
from format_bench.fair import Operation
from format_bench.formats.base import Artifact, FormatDescription
from format_bench.formats.text import CsvAdapter, ObjectJsonlAdapter
from format_bench.model import Comparability, Lane
from format_bench.runner import MeasurementConfig
from format_bench.workflow import prepare_run, verify_run


DATASET = "github-stars-2026-07-03"


class FailingAdapter:
    def __init__(self, name: str, error: Exception) -> None:
        self.name = name
        self.error = error

    def describe(self) -> FormatDescription:
        return FormatDescription(
            name=self.name,
            lane=Lane.FAIR,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".failure",
            settings={},
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        raise self.error

    def read(self, path: Path, manifest: dict) -> pa.Table:
        raise NotImplementedError

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        raise NotImplementedError

    def scan(self, path: Path, manifest: dict, operation: Operation) -> pa.Table:
        raise NotImplementedError


class FalseVerificationAdapter(CsvAdapter):
    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return {"passed": False}


def test_prepare_and_verify_fixture_record_relative_evidence(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    chosen = (CsvAdapter(), ObjectJsonlAdapter())
    prepared = prepare_run(root, DATASET, run_dir, fixture=True, selected=chosen)

    manifest = json.loads((prepared / "manifest.json").read_text())
    assert manifest["state"] == "ENCODED"
    assert manifest["fixture"] is True
    assert manifest["rankable"] is False
    assert all(not Path(entry["artifact"]).is_absolute() for entry in manifest["formats"])
    assert {entry["state"] for entry in manifest["formats"]} == {"ENCODED"}

    verify_run(prepared, {adapter.describe().name: adapter for adapter in chosen})
    verified = json.loads((prepared / "manifest.json").read_text())
    assert verified["state"] == "ROUNDTRIP_VERIFIED"
    assert {entry["state"] for entry in verified["formats"]} == {
        "ROUNDTRIP_VERIFIED"
    }
    assert all(entry["verification"]["passed"] for entry in verified["formats"])


@pytest.mark.parametrize(
    ("errors", "expected_state"),
    [
        ((ImportError("missing dependency"),), "UNSUPPORTED"),
        ((RuntimeError("adapter failed"),), "FAILED"),
        (
            (RuntimeError("adapter failed"), ImportError("missing dependency")),
            "FAILED",
        ),
    ],
)
def test_verify_run_does_not_pass_without_a_verified_adapter(
    tmp_path: Path, errors: tuple[Exception, ...], expected_state: str
) -> None:
    root = Path(__file__).parents[1]
    adapters = tuple(
        FailingAdapter(f"failure_{index}", error)
        for index, error in enumerate(errors)
    )
    run_dir = tmp_path / "run"
    prepare_run(root, DATASET, run_dir, fixture=True, selected=adapters)

    verify_run(run_dir, {adapter.name: adapter for adapter in adapters})
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert manifest["state"] == expected_state
    assert {entry["state"] for entry in manifest["formats"]} <= {
        "FAILED",
        "UNSUPPORTED",
    }


def test_verify_run_allows_partial_adapter_failure_with_verified_evidence(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    working = CsvAdapter()
    failed = FailingAdapter("failure", RuntimeError("adapter failed"))
    run_dir = tmp_path / "run"
    prepare_run(root, DATASET, run_dir, fixture=True, selected=(working, failed))

    verify_run(run_dir, {"csv": working, failed.name: failed})
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert manifest["state"] == "ROUNDTRIP_VERIFIED"
    assert {entry["state"] for entry in manifest["formats"]} == {
        "ROUNDTRIP_VERIFIED",
        "FAILED",
    }


def test_verify_run_rejects_empty_adapter_selection(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    prepare_run(root, DATASET, run_dir, fixture=True, selected=())

    verify_run(run_dir, {})
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert manifest["state"] == "FAILED"
    assert manifest["failure_reason"] == "no adapters selected for verification"


def test_verify_run_rejects_false_verification_result(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    adapter = FalseVerificationAdapter()
    run_dir = tmp_path / "run"
    prepare_run(root, DATASET, run_dir, fixture=True, selected=(adapter,))

    verify_run(run_dir, {"csv": adapter})
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert manifest["state"] == "FAILED"
    assert manifest["formats"][0]["state"] == "FAILED"
    assert "did not pass" in manifest["formats"][0]["failure_reason"]


def test_prepare_validates_dataset_before_creating_destination(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"

    with pytest.raises(ValueError, match="one path segment"):
        prepare_run(tmp_path, "../outside", run_dir, fixture=True)

    assert not run_dir.exists()


def test_prepare_rejects_source_hash_mismatch_before_encoding(tmp_path: Path) -> None:
    root = tmp_path / "root"
    dataset = root / "datasets" / DATASET
    dataset.mkdir(parents=True)
    source_dir = root / ".data" / DATASET
    source_dir.mkdir(parents=True)
    repository_root = Path(__file__).parents[1]
    shutil.copy2(
        repository_root / "datasets" / DATASET / "manifest.json",
        dataset / "manifest.json",
    )
    source = source_dir / "source.csv"
    source.write_text("not the dataset\n")
    run_dir = tmp_path / "run"

    with pytest.raises(ValueError, match="source SHA-256 mismatch"):
        prepare_run(root, DATASET, run_dir, selected=(CsvAdapter(),))

    assert not run_dir.exists()


def test_cli_run_prepares_and_verifies_new_explicit_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    calls: list[tuple[str, Path]] = []

    def prepare(
        root: Path, dataset: str, destination: Path, *, fixture: bool
    ) -> Path:
        assert dataset == DATASET
        assert fixture is True
        destination.mkdir()
        calls.append(("prepare", destination))
        return destination

    monkeypatch.setattr(cli, "prepare_run", prepare)
    monkeypatch.setattr(cli, "verify_run", lambda path: calls.append(("verify", path)))
    monkeypatch.setattr(
        cli, "run_prompt", lambda root, path: calls.append(("run", path)) or path
    )
    monkeypatch.chdir(root)

    cli.main(
        [
            "run",
            "--profile",
            "prompt",
            "--dataset",
            DATASET,
            "--run-dir",
            str(run_dir),
            "--fixture",
        ]
    )

    assert calls == [("prepare", run_dir), ("verify", run_dir), ("run", run_dir)]


@pytest.mark.parametrize(
    ("profile", "runner_name"),
    [("fair", "run_fair"), ("claims", "run_claims"), ("prompt", "run_prompt")],
)
def test_cli_profile_dispatch_matches_runner_signatures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    runner_name: str,
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    captured: list[object] = []

    def prepare(
        root: Path, dataset: str, destination: Path, *, fixture: bool
    ) -> Path:
        del root
        destination.mkdir()
        (destination / "manifest.json").write_text(
            json.dumps({"dataset_id": dataset, "fixture": fixture})
        )
        return destination

    monkeypatch.setattr(cli, "prepare_run", prepare)
    monkeypatch.setattr(cli, "verify_run", lambda path: None)
    if profile == "fair":
        def run_fair(root: Path, path: Path, *, config: object) -> Path:
            del root
            captured.append(config)
            return path

        monkeypatch.setattr(cli, runner_name, run_fair)
    else:
        def run_profile(root: Path, path: Path) -> Path:
            del root
            captured.append(profile)
            return path

        monkeypatch.setattr(cli, runner_name, run_profile)
    monkeypatch.chdir(root)

    cli.main(
        [
            "run",
            "--profile",
            profile,
            "--dataset",
            DATASET,
            "--run-dir",
            str(run_dir),
            "--fixture",
        ]
    )

    assert captured == [None if profile == "fair" else profile]


@pytest.mark.parametrize(
    ("profile", "expected_sampling"),
    [
        ("fair", (1, 1, 0, 1)),
        ("equivalence", (2, 1, 1, 2)),
    ],
)
def test_cli_timeout_preserves_fixture_sampling_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    expected_sampling: tuple[int, int, int, int],
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    captured: list[MeasurementConfig] = []

    def prepare(
        root: Path, dataset: str, destination: Path, *, fixture: bool, **kwargs
    ) -> Path:
        del root, kwargs
        destination.mkdir()
        (destination / "manifest.json").write_text(
            json.dumps({"dataset_id": dataset, "fixture": fixture})
        )
        return destination

    def run(*args, **kwargs):
        captured.append(kwargs["config"])
        return run_dir

    monkeypatch.setattr(cli, "prepare_run", prepare)
    monkeypatch.setattr(cli, "verify_run", lambda path: None)
    if profile == "fair":
        monkeypatch.setattr(cli, "run_fair", run)
    else:
        monkeypatch.setattr(cli, "run_equivalence", run)
    monkeypatch.chdir(root)

    arguments = [
        "run",
        "--profile",
        profile,
        "--dataset",
        DATASET,
        "--run-dir",
        str(run_dir),
        "--fixture",
        "--worker-timeout-seconds",
        "7.5",
    ]
    if profile == "equivalence":
        arguments.extend(["--pair", "csv-tsv"])
    cli.main(arguments)

    config = captured[0]
    assert (config.fresh_processes, config.fresh_workers, config.warmups, config.iterations) == expected_sampling
    assert config.timeout_seconds == 7.5


@pytest.mark.parametrize("profile", ["fair", "equivalence"])
def test_cli_explicit_fixture_sampling_flags_override_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    captured: list[MeasurementConfig] = []

    def prepare(
        root: Path, dataset: str, destination: Path, *, fixture: bool, **kwargs
    ) -> Path:
        del root, kwargs
        destination.mkdir()
        (destination / "manifest.json").write_text(
            json.dumps({"dataset_id": dataset, "fixture": fixture})
        )
        return destination

    monkeypatch.setattr(cli, "prepare_run", prepare)
    monkeypatch.setattr(cli, "verify_run", lambda path: None)
    def run(*args, **kwargs):
        captured.append(kwargs["config"])
        return run_dir

    monkeypatch.setattr(cli, "run_fair" if profile == "fair" else "run_equivalence", run)
    monkeypatch.chdir(root)

    arguments = [
        "run",
        "--profile",
        profile,
        "--dataset",
        DATASET,
        "--run-dir",
        str(run_dir),
        "--fixture",
        "--fresh-processes",
        "3",
        "--fresh-workers",
        "2",
        "--warmups",
        "4",
        "--iterations",
        "6",
        "--worker-timeout-seconds",
        "7.5",
    ]
    if profile == "equivalence":
        arguments.extend(["--pair", "csv-tsv"])
    cli.main(arguments)

    config = captured[0]
    assert (config.fresh_processes, config.fresh_workers, config.warmups, config.iterations) == (3, 2, 4, 6)
    assert config.timeout_seconds == 7.5


def test_cli_validates_robustness_profile_options() -> None:
    invalid_profiles = (
        (["--profile", "robustness"], "--suite bounded"),
        (["--profile", "prompt", "--suite", "bounded"], "only apply"),
    )
    for arguments, message in invalid_profiles:
        with pytest.raises(ValueError, match=message):
            cli.main(["run", *arguments, "--dataset", DATASET])
    for option, value in (
        ("--generated-cases", "-1"),
        ("--mutations-per-target", "-1"),
        ("--case-timeout-seconds", "0"),
        ("--case-timeout-seconds", "nan"),
        ("--artifact-budget-mib", "0"),
    ):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(
                [
                    "run", "--profile", "robustness", "--suite", "bounded",
                    "--dataset", DATASET, option, value,
                ]
            )


def test_cli_accepts_equivalence_pairs_and_rejects_robustness_options() -> None:
    args = cli.build_parser().parse_args(
        [
            "run",
            "--profile",
            "equivalence",
            "--dataset",
            DATASET,
            "--pair",
            "csv-tsv",
            "--pair",
            "arrow-feather",
        ]
    )
    assert args.pair == ["csv-tsv", "arrow-feather"]
    cli._validate_run_options(args)

    parallel = cli.build_parser().parse_args(
        [
            "run",
            "--profile",
            "equivalence",
            "--dataset",
            DATASET,
            "--parallel-jobs",
        ]
    )
    cli._validate_run_options(parallel)
    assert parallel.parallel_jobs is True

    timeout = cli.build_parser().parse_args(
        [
            "run",
            "--profile",
            "fair",
            "--dataset",
            DATASET,
            "--worker-timeout-seconds",
            "37.5",
        ]
    )
    cli._validate_run_options(timeout)
    assert timeout.worker_timeout_seconds == 37.5

    fair_parallel = cli.build_parser().parse_args(
        [
            "run",
            "--profile",
            "fair",
            "--dataset",
            DATASET,
            "--parallel-jobs",
        ]
    )
    with pytest.raises(ValueError, match="requires --profile equivalence"):
        cli._validate_run_options(fair_parallel)

    invalid = cli.build_parser().parse_args(
        [
            "run",
            "--profile",
            "equivalence",
            "--dataset",
            DATASET,
            "--suite",
            "bounded",
        ]
    )
    with pytest.raises(ValueError, match="robustness options"):
        cli._validate_run_options(invalid)


@pytest.mark.parametrize("value", ["0", "nan", "inf", "-1"])
def test_cli_rejects_invalid_worker_timeout(value: str) -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            [
                "run",
                "--profile",
                "equivalence",
                "--dataset",
                DATASET,
                "--worker-timeout-seconds",
                value,
            ]
        )
