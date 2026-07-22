import copy
import json
from pathlib import Path

import pyarrow as pa
import pytest

import format_bench.robustness.worker as worker
from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.fair import Operation
from format_bench.formats.base import Artifact, FormatDescription, ParserRejection
from format_bench.model import (
    Comparability,
    Lane,
    ObservedOutcome,
    RobustnessExpectation,
    RobustnessVerdict,
    robustness_verdict,
)
from format_bench.robustness import (
    core_targets,
    encode_malformed,
    encode_valid,
    materialize_case,
    named_cases,
    target_map,
)
from format_bench.robustness.worker import run_request
from format_bench.robustness.targets import (
    RobustnessTarget,
    TargetExecutionError,
    read_robustness,
)


DATASET = Path("datasets/github-stars-2026-07-03")


def _fixture() -> tuple[dict, pa.Table]:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    fixture = copy.deepcopy(manifest)
    fixture["rows"] = table.num_rows
    fixture["canonical_hash"] = ""
    return fixture, table


def test_core_targets_reuse_registered_adapters() -> None:
    assert [target.name for target in core_targets()] == [
        "csv",
        "object_jsonl",
        "parquet_default",
        "parquet_zstd19",
        "lance_base",
        "vortex_default",
        "vortex_compact",
    ]
    assert set(target_map()) == {target.name for target in core_targets()}


@pytest.mark.parametrize("target", core_targets(), ids=lambda item: item.name)
def test_valid_boundary_cases_round_trip_through_each_core_target(tmp_path: Path, target) -> None:
    manifest, base = _fixture()
    cases = {case.case_id: case for case in named_cases()}
    table = materialize_case(base, cases["rows-1024"])
    path = tmp_path / f"valid{target.adapter.describe().extension}"
    encode_valid(target, table, path)
    case_manifest = {
        **manifest,
        "rows": 1024,
        "canonical_hash": canonical_hash(table),
        "expected_counts": query_counts(table),
    }
    assert target.adapter.verify_roundtrip(path, case_manifest)["passed"] is True


@pytest.mark.parametrize("target", core_targets(), ids=lambda item: item.name)
@pytest.mark.parametrize("kind", ["missing_column", "extra_column"])
def test_column_shape_cases_are_constructed_for_each_core_target(tmp_path: Path, target, kind: str) -> None:
    _, base = _fixture()
    path = tmp_path / f"malformed{target.adapter.describe().extension}"
    artifact = encode_malformed(target, base, path, kind)
    assert path.exists()
    if path.is_file():
        assert path.stat().st_size > 0
        assert artifact.native_bytes == path.stat().st_size
    else:
        assert artifact.native_bytes > 0


@pytest.mark.parametrize("target", core_targets(), ids=lambda item: item.name)
def test_malformed_constructor_rejects_unknown_cases(tmp_path: Path, target) -> None:
    _, base = _fixture()
    with pytest.raises(ValueError, match="unsupported"):
        encode_malformed(target, base, tmp_path / f"bad{target.adapter.describe().extension}", "truncated")


@pytest.mark.parametrize("target", core_targets(), ids=lambda item: item.name)
@pytest.mark.parametrize("kind", ["missing_column", "extra_column"])
def test_malformed_column_cases_are_rejected_by_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target, kind: str
) -> None:
    manifest, base = _fixture()
    manifest["canonical_hash"] = canonical_hash(base)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.chdir(tmp_path)
    path = tmp_path / f"malformed{target.adapter.describe().extension}"
    encode_malformed(target, base, path, kind)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({
        "schema_version": "1",
        "case_id": f"{target.name}-{kind}",
        "target": target.name,
        "expectation": "MUST_REJECT",
        "manifest": "manifest.json",
        "artifact": path.name,
    }))
    result = run_request(request)
    assert result["observed"] is ObservedOutcome.REJECTED


def test_read_robustness_attributes_parser_rejection_to_target_boundary(
    tmp_path: Path,
) -> None:
    class RejectingAdapter:
        def describe(self) -> FormatDescription:
            return FormatDescription(
                name="custom",
                lane=Lane.ROBUSTNESS,
                comparability=Comparability.UNAVAILABLE,
                extension=".bin",
                settings={},
            )

        def encode(self, table: pa.Table, path: Path) -> Artifact:
            raise NotImplementedError

        def read(self, path: Path, manifest: dict) -> pa.Table:
            raise ParserRejection(ValueError("malformed artifact"))

        def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
            raise NotImplementedError

        def scan(self, path: Path, manifest: dict, operation: Operation) -> pa.Table:
            raise NotImplementedError

    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"broken")
    target = RobustnessTarget("custom", RejectingAdapter())

    with pytest.raises(TargetExecutionError, match="malformed artifact"):
        read_robustness(target, artifact, _fixture()[0])


def test_parquet_data_page_rejection_crosses_parser_boundary(tmp_path: Path) -> None:
    manifest, table = _fixture()
    path = tmp_path / "artifact.parquet"
    encode_valid(target_map()["parquet_zstd19"], table, path)
    mutated = bytearray(path.read_bytes())
    mutated[4] ^= 0xFF
    path.write_bytes(mutated)
    with pytest.raises(TargetExecutionError) as caught:
        read_robustness(target_map()["parquet_zstd19"], path, manifest)
    assert isinstance(caught.value.cause, OSError)


def test_lance_wrong_type_rejection_crosses_parser_boundary(tmp_path: Path) -> None:
    manifest, table = _fixture()
    index = table.schema.get_field_index("description")
    malformed = table.set_column(index, "description", pa.array([[1]] * table.num_rows))
    path = tmp_path / "artifact.lance"
    encode_valid(target_map()["lance_base"], malformed, path)
    with pytest.raises(TargetExecutionError) as caught:
        read_robustness(target_map()["lance_base"], path, manifest)
    assert isinstance(caught.value.cause, pa.ArrowException)


def test_worker_reports_value_mismatch_when_verification_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MismatchingAdapter:
        def read(self, path, manifest):
            return None

        def verify_roundtrip(self, path, manifest):
            return {"passed": False}

    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "artifact.bin").write_bytes(b"data")
    (tmp_path / "request.json").write_text(json.dumps({
        "case_id": "mismatch",
        "target": "mismatch",
        "expectation": "MUST_ROUNDTRIP",
        "manifest": "manifest.json",
        "artifact": "artifact.bin",
    }))
    monkeypatch.setattr(worker, "adapter_map", lambda: {"mismatch": MismatchingAdapter()})
    monkeypatch.chdir(tmp_path)

    assert run_request(Path("request.json"))["observed"] is ObservedOutcome.VALUE_MISMATCH


@pytest.mark.parametrize(
    ("error", "observed", "error_type"),
    [
        (
            ParserRejection(ValueError("malformed round-trip artifact")),
            ObservedOutcome.REJECTED,
            "ValueError",
        ),
        (TypeError("adapter defect"), ObservedOutcome.HARNESS_FAILED, "TypeError"),
    ],
)
def test_worker_classifies_roundtrip_read_parser_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    observed: ObservedOutcome,
    error_type: str,
) -> None:
    class FailingReader:
        def read(self, path, manifest):
            raise error

    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "artifact.bin").write_bytes(b"data")
    (tmp_path / "request.json").write_text(json.dumps({
        "case_id": "roundtrip-read-error",
        "target": "broken",
        "expectation": "MUST_ROUNDTRIP",
        "manifest": "manifest.json",
        "artifact": "artifact.bin",
    }))
    monkeypatch.setattr(worker, "adapter_map", lambda: {"broken": FailingReader()})
    monkeypatch.chdir(tmp_path)

    result = run_request(Path("request.json"))

    assert result["observed"] is observed
    assert result["details"]["error_type"] == error_type
    assert result["details"]["message"] == str(error)


def test_worker_reports_raised_builtin_verification_as_value_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, table = _fixture()
    manifest["canonical_hash"] = "not-the-table-hash"
    manifest["expected_counts"] = query_counts(table)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    encode_valid(target_map()["csv"], table, tmp_path / "artifact.csv")
    (tmp_path / "request.json").write_text(json.dumps({
        "case_id": "raised-mismatch",
        "target": "csv",
        "expectation": "MUST_ROUNDTRIP",
        "manifest": "manifest.json",
        "artifact": "artifact.csv",
    }))
    monkeypatch.chdir(tmp_path)

    result = run_request(Path("request.json"))
    assert result["observed"] is ObservedOutcome.VALUE_MISMATCH
    assert result["details"]["error_type"] == "ValueError"


def test_worker_reports_non_value_verification_errors_as_harness_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenVerifier:
        def read(self, path, manifest):
            return None

        def verify_roundtrip(self, path, manifest):
            raise TypeError("comparison unavailable")

    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "artifact.bin").write_bytes(b"data")
    (tmp_path / "request.json").write_text(json.dumps({
        "case_id": "type-mismatch",
        "target": "broken",
        "manifest": "manifest.json",
        "artifact": "artifact.bin",
        "expectation": "MUST_ROUNDTRIP",
    }))
    monkeypatch.setattr(worker, "adapter_map", lambda: {"broken": BrokenVerifier()})
    monkeypatch.chdir(tmp_path)

    result = run_request(Path("request.json"))

    assert result["observed"] is ObservedOutcome.HARNESS_FAILED
    assert result["details"]["error_type"] == "TypeError"


@pytest.mark.parametrize("error_type", [NameError, TypeError])
@pytest.mark.parametrize("expectation", ["MUST_REJECT", "MUST_NOT_CRASH"])
def test_worker_does_not_attribute_lab_setup_errors_to_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
    expectation: str,
) -> None:
    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "artifact.bin").write_bytes(b"data")
    (tmp_path / "request.json").write_text(json.dumps({
        "case_id": "lab-setup-error",
        "target": "broken",
        "manifest": "manifest.json",
        "artifact": "artifact.bin",
        "expectation": expectation,
    }))

    def broken_target_map() -> dict:
        raise error_type("lab setup failure")

    monkeypatch.setattr(worker, "adapter_map", lambda: {"broken": object()})
    monkeypatch.setattr(worker, "target_map", broken_target_map)
    monkeypatch.chdir(tmp_path)

    result = run_request(Path("request.json"))

    assert result["observed"] is ObservedOutcome.HARNESS_FAILED
    assert result["details"]["error_type"] == error_type.__name__
    assert robustness_verdict(
        RobustnessExpectation(expectation), result["observed"]
    ) is RobustnessVerdict.INCOMPLETE


@pytest.mark.parametrize(
    "error_type",
    [pa.ArrowInvalid, OSError, RuntimeError, ValueError, NameError, TypeError],
)
@pytest.mark.parametrize("expectation", ["MUST_REJECT", "MUST_NOT_CRASH"])
def test_worker_does_not_attribute_core_adapter_defects_to_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
    expectation: str,
) -> None:
    manifest, table = _fixture()
    target = worker.target_map()["parquet_default"]
    encode_valid(target, table, tmp_path / "artifact.parquet")

    def fail_adapter(_path: Path, _manifest: dict) -> pa.Table:
        raise error_type("adapter defect")

    monkeypatch.setattr(target.adapter, "read", fail_adapter)
    monkeypatch.setattr(worker, "target_map", lambda: {target.name: target})
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "request.json").write_text(json.dumps({
        "case_id": "adapter-defect",
        "target": target.name,
        "manifest": "manifest.json",
        "artifact": "artifact.parquet",
        "expectation": expectation,
    }))
    monkeypatch.chdir(tmp_path)

    result = run_request(Path("request.json"))

    assert result["observed"] is ObservedOutcome.HARNESS_FAILED
    assert result["details"]["error_type"] == error_type.__name__
    assert robustness_verdict(
        RobustnessExpectation(expectation), result["observed"]
    ) is RobustnessVerdict.INCOMPLETE


def test_worker_accepts_explicit_target_boundary_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class RejectingAdapter:
        def read(self, path, manifest):
            raise TargetExecutionError(TypeError("target rejected artifact"))

    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "artifact.bin").write_bytes(b"data")
    (tmp_path / "request.json").write_text(json.dumps({
        "case_id": "target-boundary-error",
        "target": "broken",
        "manifest": "manifest.json",
        "artifact": "artifact.bin",
        "expectation": "MUST_REJECT",
    }))
    monkeypatch.setattr(worker, "adapter_map", lambda: {"broken": RejectingAdapter()})
    monkeypatch.setattr(worker, "target_map", lambda: {})
    monkeypatch.chdir(tmp_path)

    result = run_request(Path("request.json"))

    assert result["observed"] is ObservedOutcome.REJECTED
    assert result["details"]["error_type"] == "TypeError"
    assert robustness_verdict(
        RobustnessExpectation.MUST_REJECT, result["observed"]
    ) is RobustnessVerdict.PASS
