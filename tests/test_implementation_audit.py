from pathlib import Path
from typing import cast

from format_bench.formats.text import CsvAdapter, TsvAdapter
from format_bench.implementation_audit import (
    AuditEvidence,
    AuditStatus,
    audit_adapters,
    audit_implementation,
    audit_lifecycle,
    audit_safe_relative_paths,
    audit_workload_coverage,
)
from format_bench.model import ExecutionState, Lane, WorkloadKind, WorkloadSpec


def _workloads() -> dict[str, WorkloadSpec]:
    return {
        "read_all": WorkloadSpec("read_all", WorkloadKind.READ_ALL),
        "head_10": WorkloadSpec("head_10", WorkloadKind.HEAD, limit=10),
    }


def _observed(evidence: AuditEvidence) -> dict[str, object]:
    assert isinstance(evidence.observed, dict)
    return cast(dict[str, object], evidence.observed)


def test_adapter_audit_reports_count_and_lane_failures() -> None:
    result = audit_adapters(
        (CsvAdapter(), TsvAdapter()),
        expected_count=3,
        expected_lanes={"csv": Lane.FAIR, "tsv": Lane.FAIR, "missing": Lane.FAIR},
    )
    assert result.status is AuditStatus.FAIL
    lane_mismatches = _observed(result)["lane_mismatches"]
    assert isinstance(lane_mismatches, tuple)
    assert "missing adapter: missing" in lane_mismatches


def test_adapter_audit_reports_unexpected_adapter_without_crashing() -> None:
    result = audit_adapters(
        (CsvAdapter(), TsvAdapter()),
        expected_lanes={"csv": Lane.FAIR},
    )
    assert result.status is AuditStatus.FAIL
    assert _observed(result)["lane_mismatches"] == ("unexpected adapter: tsv",)


def test_lifecycle_audit_accepts_public_contract_and_rejects_skips() -> None:
    assert audit_lifecycle(
        [
            ExecutionState.DISCOVERED,
            ExecutionState.ENCODED,
            ExecutionState.ROUNDTRIP_VERIFIED,
            ExecutionState.BENCHMARKED,
            ExecutionState.REPORTED,
        ]
    ).status is AuditStatus.PASS
    result = audit_lifecycle(["DISCOVERED", "BENCHMARKED"])
    assert result.status is AuditStatus.FAIL
    assert _observed(result)["illegal"] == ("DISCOVERED -> BENCHMARKED",)


def test_safe_paths_are_deterministic_and_root_aware(tmp_path: Path) -> None:
    assert audit_safe_relative_paths(["artifacts/result.json"], root=tmp_path).passed
    result = audit_safe_relative_paths(["../result.json", "/tmp/result.json"], root=tmp_path)
    assert result.status is AuditStatus.FAIL
    assert _observed(result)["unsafe"] == ("../result.json", "/tmp/result.json")


def test_workload_audit_requires_declared_coverage() -> None:
    result = audit_workload_coverage(_workloads(), ["read_all", "filter"])
    assert result.status is AuditStatus.FAIL
    assert _observed(result)["missing"] == ("filter",)
    assert audit_workload_coverage(_workloads(), ["head_10"]).passed


def test_aggregate_returns_pass_fail_evidence_without_score() -> None:
    result = audit_implementation(
        (CsvAdapter(), TsvAdapter()),
        lifecycle=["DISCOVERED", "ENCODED", "ROUNDTRIP_VERIFIED", "BENCHMARKED"],
        artifact_paths=["run/result.csv"],
        workloads=_workloads(),
        required_operations=["read_all", "head_10"],
        expected_adapter_count=2,
        expected_lanes={"csv": Lane.FAIR, "tsv": Lane.EQUIVALENCE},
    )
    assert result.status is AuditStatus.PASS
    assert "score" not in result.as_dict()
    assert {check.status for check in result.checks} == {AuditStatus.PASS}
