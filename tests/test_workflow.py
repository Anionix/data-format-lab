import json
import os
import shutil
import stat
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pytest

from format_bench import cli, workflow
from format_bench.artifact_digest import artifact_sha256
from format_bench.fair import Operation
from format_bench.formats.base import Artifact, FormatDescription
from format_bench.formats.lance import LanceAdapter
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


class RecordingVerificationAdapter(CsvAdapter):
    def __init__(self) -> None:
        self.verification_calls = 0

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        self.verification_calls += 1
        return {"passed": True}


class UnsafeFormatAdapter(CsvAdapter):
    def __init__(self, name: str, extension: str = ".unsafe") -> None:
        self.unsafe_name = name
        self.unsafe_extension = extension

    def describe(self) -> FormatDescription:
        description = super().describe()
        return FormatDescription(
            name=self.unsafe_name,
            lane=description.lane,
            comparability=description.comparability,
            extension=self.unsafe_extension,
            settings=description.settings,
        )


class WrongPathAdapter(CsvAdapter):
    def __init__(self, returned_path: Path) -> None:
        self.returned_path = returned_path

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        artifact = super().encode(table, path)
        return replace(artifact, path=self.returned_path)


class SymlinkArtifactAdapter(CsvAdapter):
    def __init__(self, target: Path) -> None:
        self.target = target

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(self.target, target_is_directory=True)
        return Artifact(path, 1, 1, 0.0)


def _minimal_verification_manifest(
    input_manifest: str, artifact: str = "artifacts/csv.csv"
) -> dict[str, object]:
    return {
        "input": {"manifest": input_manifest},
        "formats": [
            {
                "format": "csv",
                "artifact": artifact,
                "state": "ENCODED",
            }
        ],
        "state": "ENCODED",
    }


def _assert_verification_rejected(
    run_dir: Path,
    raw: str,
    message: str,
    error_type: type[Exception] = ValueError,
) -> None:
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(raw, encoding="utf-8")
    adapter = RecordingVerificationAdapter()

    with pytest.raises(error_type, match=message):
        verify_run(run_dir, {"csv": adapter})

    assert adapter.verification_calls == 0
    assert manifest_path.read_text(encoding="utf-8") == raw


def test_prepare_and_verify_fixture_record_relative_evidence(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    chosen = (CsvAdapter(), ObjectJsonlAdapter())
    prepared = prepare_run(
        root,
        DATASET,
        run_dir,
        fixture=True,
        selected=chosen,
        size_observations=2,
    )

    manifest = json.loads((prepared / "manifest.json").read_text())
    assert manifest["state"] == "ENCODED"
    assert manifest["fixture"] is True
    assert manifest["rankable"] is False
    assert all(
        not Path(entry["artifact"]).is_absolute() for entry in manifest["formats"]
    )
    assert {entry["state"] for entry in manifest["formats"]} == {"ENCODED"}
    assert all(
        entry["size_observations"]["completed"] == 2 for entry in manifest["formats"]
    )
    assert not (prepared / ".size-observations").exists()

    verify_run(prepared, {adapter.describe().name: adapter for adapter in chosen})
    verified = json.loads((prepared / "manifest.json").read_text())
    assert verified["state"] == "ROUNDTRIP_VERIFIED"
    assert {entry["state"] for entry in verified["formats"]} == {"ROUNDTRIP_VERIFIED"}
    assert all(entry["verification"]["passed"] for entry in verified["formats"])
    assert all(
        all(
            attempt["roundtrip_verified"]
            for attempt in entry["size_observations"]["attempts"]
        )
        for entry in verified["formats"]
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory-mode contract")
@pytest.mark.parametrize("mask", (0o002, 0o000))
def test_prepare_run_creates_private_lifecycle_directories_under_open_umask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mask: int,
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    requested_modes: dict[str, int] = {}
    real_mkdir = Path.mkdir

    def record_mode(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if path == run_dir or run_dir in path.parents:
            requested_modes.setdefault(str(path.relative_to(run_dir.parent)), mode)
        real_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", record_mode)
    previous_mask = os.umask(mask)
    try:
        prepare_run(
            root,
            DATASET,
            run_dir,
            fixture=True,
            selected=(CsvAdapter(),),
            size_observations=2,
        )
    finally:
        os.umask(previous_mask)

    for directory in (run_dir, run_dir / "input", run_dir / "artifacts"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert requested_modes["run/.size-observations"] == 0o700
    assert requested_modes["run/.size-observations/csv"] == 0o700
    assert (run_dir / "input" / "manifest.json").is_file()
    assert (run_dir / "manifest.json").is_file()


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory-mode contract")
@pytest.mark.parametrize("mask", (0o002, 0o000))
def test_prepare_run_creates_each_missing_custom_ancestor_privately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mask: int,
) -> None:
    root = Path(__file__).parents[1]
    existing_parent = tmp_path / "existing"
    existing_parent.mkdir(mode=0o700)
    first_ancestor = existing_parent / "first"
    second_ancestor = first_ancestor / "second"
    run_dir = second_ancestor / "run"
    created_levels = (first_ancestor, second_ancestor, run_dir)
    requested_modes: dict[Path, int] = {}
    real_mkdir = Path.mkdir

    def record_mode(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if path in created_levels:
            requested_modes[path] = mode
            assert parents is False
        real_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", record_mode)

    previous_mask = os.umask(mask)
    try:
        prepared = prepare_run(root, DATASET, run_dir, fixture=True, selected=())
    finally:
        os.umask(previous_mask)

    assert prepared == run_dir
    assert requested_modes == {directory: 0o700 for directory in created_levels}
    for directory in created_levels:
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert (run_dir / "input" / "manifest.json").is_file()
    assert (run_dir / "manifest.json").is_file()


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory-mode contract")
@pytest.mark.parametrize(
    ("raced_mode", "expected_error"),
    ((0o700, None), (0o755, PermissionError)),
)
def test_missing_private_parent_validates_concurrent_creator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raced_mode: int,
    expected_error: type[Exception] | None,
) -> None:
    existing_parent = tmp_path / "existing"
    existing_parent.mkdir(mode=0o700)
    raced_parent = existing_parent / "runs"
    destination = raced_parent / "run"
    real_mkdir = Path.mkdir
    raced = False

    def race_mkdir(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        nonlocal raced
        if path == raced_parent and not raced:
            real_mkdir(path, mode=raced_mode)
            path.chmod(raced_mode)
            raced = True
        real_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", race_mkdir)

    if expected_error is None:
        workflow._create_missing_private_parents(destination)
    else:
        with pytest.raises(expected_error, match="not private"):
            workflow._create_missing_private_parents(destination)

    assert raced is True
    assert stat.S_IMODE(raced_parent.stat().st_mode) == raced_mode


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory-mode contract")
@pytest.mark.parametrize("mask", (0o002, 0o000))
def test_prepare_run_creates_missing_default_parent_privately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mask: int,
) -> None:
    root = Path(__file__).parents[1]
    destination_root = tmp_path / "root"
    destination_root.mkdir(mode=0o700)
    destination = destination_root / "runs" / "run"
    monkeypatch.setattr(
        workflow,
        "_default_run_dir",
        lambda _root, _dataset_id: destination,
    )

    previous_mask = os.umask(mask)
    try:
        prepared = prepare_run(root, DATASET, fixture=True, selected=())
    finally:
        os.umask(previous_mask)

    assert prepared == destination
    for directory in (destination.parent, destination):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_artifact_digest_rejects_root_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "data.bin").write_bytes(b"data")
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="must not be a symlink"):
        artifact_sha256(link)


@pytest.mark.parametrize(
    ("name", "extension", "message"),
    [
        ("../escape", ".bin", "format name"),
        ("safe", "../escape", "format extension"),
        ("/absolute", ".bin", "format name"),
    ],
)
def test_prepare_rejects_unsafe_format_path_components(
    tmp_path: Path, name: str, extension: str, message: str
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"

    with pytest.raises(ValueError, match=message):
        prepare_run(
            root,
            DATASET,
            run_dir,
            fixture=True,
            selected=(UnsafeFormatAdapter(name, extension),),
            size_observations=2,
        )

    assert not (tmp_path / "escape").exists()


def test_prepare_rejects_adapter_returning_different_artifact_path(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    returned_path = tmp_path / "outside.bin"
    returned_path.write_bytes(b"must remain unchanged")
    run_dir = tmp_path / "run"

    prepare_run(
        root,
        DATASET,
        run_dir,
        fixture=True,
        selected=(WrongPathAdapter(returned_path),),
    )

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["formats"][0]["state"] == "FAILED"
    assert (
        "different from the requested path" in manifest["formats"][0]["failure_reason"]
    )
    assert returned_path.read_bytes() == b"must remain unchanged"


def test_prepare_unlinks_symlink_artifacts_without_touching_target(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    run_dir = tmp_path / "run"

    prepare_run(
        root,
        DATASET,
        run_dir,
        fixture=True,
        selected=(SymlinkArtifactAdapter(outside),),
    )

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["formats"][0]["state"] == "FAILED"
    assert not (run_dir / "artifacts" / "csv.csv").exists()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_prepare_hashes_lance_directory_size_observations(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    adapter = LanceAdapter()
    run_dir = tmp_path / "run"

    prepare_run(
        root,
        DATASET,
        run_dir,
        fixture=True,
        selected=(adapter,),
        size_observations=2,
    )
    verify_run(run_dir, {adapter.describe().name: adapter})

    entry = json.loads((run_dir / "manifest.json").read_text())["formats"][0]
    attempts = entry["size_observations"]["attempts"]
    assert entry["state"] == "ROUNDTRIP_VERIFIED"
    assert (run_dir / entry["artifact"]).is_dir()
    assert not (run_dir / ".size-observations").exists()
    assert [attempt["status"] for attempt in attempts] == ["MEASURED", "MEASURED"]
    assert all(len(attempt["artifact_sha256"]) == 64 for attempt in attempts)


@pytest.mark.parametrize(("fixture", "expected"), [(True, 2), (False, 10)])
def test_equivalence_size_observation_count_is_bounded(
    fixture: bool, expected: int
) -> None:
    assert cli._equivalence_size_observations(fixture) == expected
    args = cli.build_parser().parse_args(
        ["prepare", "--dataset", DATASET, "--size-observations", str(expected)]
    )
    assert args.size_observations == expected


@pytest.mark.parametrize(
    ("fixture", "observations", "required", "malformed"),
    [
        (True, 1, 2, None),
        (False, 2, 10, None),
        (True, 2, 2, "digest"),
        (False, 10, 10, "contract"),
    ],
)
def test_existing_equivalence_run_rejects_invalid_size_evidence(
    tmp_path: Path,
    fixture: bool,
    observations: int,
    required: int,
    malformed: str | None,
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    attempts = [
        {
            "index": index,
            "status": "MEASURED",
            "native_bytes": 10,
            "transport_zstd_bytes": 8,
            "artifact_sha256": f"{index:064x}",
            "roundtrip_verified": True,
        }
        for index in range(observations)
    ]
    if malformed == "digest":
        attempts[-1]["artifact_sha256"] = "not-a-sha256"
    evidence = {
        "contract_version": "1",
        "resampling_unit": "same_process_encode_invocation",
        "attempted": observations,
        "completed": observations,
        "attempts": attempts,
    }
    if malformed == "contract":
        evidence["contract_version"] = "0"
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_id": DATASET,
                "fixture": fixture,
                "formats": [
                    {
                        "format": name,
                        "state": "ROUNDTRIP_VERIFIED",
                        "size_observations": evidence,
                    }
                    for name in ("csv", "tsv")
                ],
            }
        )
    )
    args = cli.build_parser().parse_args(
        [
            "run",
            "--profile",
            "equivalence",
            "--dataset",
            DATASET,
            "--run-dir",
            str(run_dir),
            "--pair",
            "csv-tsv",
        ]
    )

    with pytest.raises(ValueError, match=f"--size-observations {required}"):
        cli._run_directory(root, args)


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
        FailingAdapter(f"failure_{index}", error) for index, error in enumerate(errors)
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


def test_verify_run_rejects_duplicate_input_manifest_keys_before_adapter(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    raw = (
        '{"input":{"manifest":"input/manifest.json","manifest":'
        f"{json.dumps(str(outside))}"
        '},"formats":[{"format":"csv","artifact":"artifacts/csv.csv",'
        '"state":"ENCODED"}],"state":"ENCODED"}'
    )
    _assert_verification_rejected(
        run_dir,
        raw,
        "duplicate JSON object key",
        json.JSONDecodeError,
    )


@pytest.mark.parametrize("path_kind", ["absolute", "parent", "symlink"])
def test_verify_run_rejects_escaped_input_manifest_before_adapter(
    tmp_path: Path, path_kind: str
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    if path_kind == "absolute":
        input_manifest = str(outside)
    elif path_kind == "parent":
        input_manifest = "../outside.json"
    else:
        input_dir = run_dir / "input"
        input_dir.mkdir()
        (input_dir / "manifest.json").symlink_to(outside)
        input_manifest = "input/manifest.json"
    manifest = _minimal_verification_manifest(input_manifest)
    raw = json.dumps(manifest)
    _assert_verification_rejected(run_dir, raw, "input manifest must be run-relative")


@pytest.mark.parametrize("path_kind", ["absolute", "parent", "symlink"])
def test_verify_run_rejects_escaped_artifact_before_adapter(
    tmp_path: Path, path_kind: str
) -> None:
    run_dir = tmp_path / "run"
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "manifest.json").write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside.csv"
    outside.write_text("outside", encoding="utf-8")
    if path_kind == "absolute":
        artifact = str(outside)
    elif path_kind == "parent":
        artifact = "../outside.csv"
    else:
        artifact_dir = run_dir / "artifacts"
        artifact_dir.mkdir()
        (artifact_dir / "csv.csv").symlink_to(outside)
        artifact = "artifacts/csv.csv"
    raw = json.dumps(_minimal_verification_manifest("input/manifest.json", artifact))
    _assert_verification_rejected(run_dir, raw, "artifact path must be run-relative")


@pytest.mark.parametrize(
    "artifact",
    ["input/source.csv", "artifacts/../input/source.csv", "artifacts"],
)
def test_verify_run_rejects_artifact_outside_artifact_namespace(
    tmp_path: Path, artifact: str
) -> None:
    run_dir = tmp_path / "run"
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (input_dir / "source.csv").write_text("not encoded output", encoding="utf-8")
    raw = json.dumps(_minimal_verification_manifest("input/manifest.json", artifact))
    _assert_verification_rejected(run_dir, raw, "artifact path must be below artifacts")


def test_verify_run_rejects_non_object_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _assert_verification_rejected(run_dir, "[]", "run manifest must be an object")


def test_verify_run_rejects_malformed_size_observations_before_adapter(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    adapter = RecordingVerificationAdapter()
    prepare_run(root, DATASET, run_dir, fixture=True, selected=(adapter,))
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["formats"][0]["size_observations"] = []
    raw = json.dumps(manifest)
    _assert_verification_rejected(run_dir, raw, "size_observations must be an object")


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

    def prepare(root: Path, dataset: str, destination: Path, *, fixture: bool) -> Path:
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

    def prepare(root: Path, dataset: str, destination: Path, *, fixture: bool) -> Path:
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
    assert (
        config.fresh_processes,
        config.fresh_workers,
        config.warmups,
        config.iterations,
    ) == expected_sampling
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

    monkeypatch.setattr(
        cli, "run_fair" if profile == "fair" else "run_equivalence", run
    )
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
    assert (
        config.fresh_processes,
        config.fresh_workers,
        config.warmups,
        config.iterations,
    ) == (3, 2, 4, 6)
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
                    "run",
                    "--profile",
                    "robustness",
                    "--suite",
                    "bounded",
                    "--dataset",
                    DATASET,
                    option,
                    value,
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
