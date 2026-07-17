"""Deterministic implementation-contract checks.

This module audits declarations and evidence metadata only.  It does not run
adapters, benchmark workloads, or assign a maturity score.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .formats.base import FormatAdapter
from .model import ExecutionState, Lane, WorkloadSpec, transition


class AuditStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class AuditEvidence:
    """One deterministic check result, suitable for JSON serialization."""

    check: str
    status: AuditStatus
    details: str
    observed: object
    expected: object

    @property
    def passed(self) -> bool:
        return self.status is AuditStatus.PASS

    def as_dict(self) -> dict[str, object]:
        return {
            "check": self.check,
            "status": self.status.value,
            "details": self.details,
            "observed": self.observed,
            "expected": self.expected,
        }


@dataclass(frozen=True)
class ImplementationAudit:
    checks: tuple[AuditEvidence, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def status(self) -> AuditStatus:
        return AuditStatus.PASS if self.passed else AuditStatus.FAIL

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "checks": [check.as_dict() for check in self.checks],
        }


def _evidence(
    check: str,
    passed: bool,
    details: str,
    observed: object,
    expected: object,
) -> AuditEvidence:
    return AuditEvidence(
        check=check,
        status=AuditStatus.PASS if passed else AuditStatus.FAIL,
        details=details,
        observed=observed,
        expected=expected,
    )


def audit_adapters(
    adapters: Iterable[FormatAdapter],
    *,
    expected_count: int | None = None,
    expected_lanes: Mapping[str, Lane | str] | None = None,
) -> AuditEvidence:
    """Check adapter cardinality, unique names, and declared lane separation."""

    descriptions = tuple(adapter.describe() for adapter in adapters)
    names = tuple(description.name for description in descriptions)
    duplicate_names = tuple(sorted({name for name in names if names.count(name) > 1}))
    lanes_by_name: dict[str, set[str]] = {}
    for description in descriptions:
        lanes_by_name.setdefault(description.name, set()).add(description.lane.value)
    multi_lane_names = tuple(
        sorted(name for name, lanes in lanes_by_name.items() if len(lanes) > 1)
    )
    lane_mismatches: tuple[str, ...] = ()
    if expected_lanes is not None:
        lane_mismatches = tuple(
            sorted(
                f"{name}: expected {Lane(expected_lanes[name]).value}, got {lane.value}"
                for name, lane in (
                    (description.name, description.lane) for description in descriptions
                )
                if name not in expected_lanes or Lane(expected_lanes[name]) != lane
            )
        )
        missing_lanes = tuple(sorted(set(expected_lanes) - set(names)))
        lane_mismatches += tuple(f"missing adapter: {name}" for name in missing_lanes)
    count_ok = expected_count is None or len(descriptions) == expected_count
    passed = not duplicate_names and not multi_lane_names and not lane_mismatches and count_ok
    return _evidence(
        "adapter_count_and_lane_separation",
        passed,
        "adapter names are unique and each name has one declared lane"
        if passed
        else "adapter inventory or lane declarations are inconsistent",
        {
            "count": len(descriptions),
            "duplicate_names": duplicate_names,
            "multi_lane_names": multi_lane_names,
            "lane_mismatches": lane_mismatches,
        },
        {
            "count": expected_count,
            "lanes": {name: Lane(lane).value for name, lane in (expected_lanes or {}).items()},
        },
    )


def audit_lifecycle(states: Sequence[ExecutionState | str]) -> AuditEvidence:
    """Check every adjacent lifecycle transition, including terminal failures."""

    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    normalized = tuple(ExecutionState(state) for state in states)
    illegal: list[str] = []
    for current, target in zip(normalized, normalized[1:], strict=False):
        try:
            transition(current, target)
        except ValueError:
            illegal.append(f"{current.value} -> {target.value}")
    passed = bool(normalized) and not illegal
    return _evidence(
        "lifecycle_transition_legality",
        passed,
        "all lifecycle transitions are legal" if passed else "illegal lifecycle transition found",
        {"states": tuple(state.value for state in normalized), "illegal": tuple(illegal)},
        "DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED",
    )


def audit_safe_relative_paths(
    paths: Iterable[str | Path], *, root: Path | None = None
) -> AuditEvidence:
    """Check that artifact paths are non-empty relative paths without traversal."""

    values = tuple(Path(path) for path in paths)
    unsafe: list[str] = []
    for path in values:
        if not path.parts or path == Path(".") or path.is_absolute() or ".." in path.parts:
            unsafe.append(str(path))
            continue
        if root is not None:
            candidate = (root / path).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                unsafe.append(str(path))
    return _evidence(
        "safe_relative_paths",
        not unsafe,
        "all paths are safe relative paths" if not unsafe else "unsafe relative path found",
        {"paths": tuple(str(path) for path in values), "unsafe": tuple(unsafe)},
        "non-empty relative paths without '..' components",
    )


def audit_workload_coverage(
    workloads: Mapping[str, WorkloadSpec],
    required_operations: Iterable[str],
) -> AuditEvidence:
    """Check valid workload declarations cover every required operation."""

    required = tuple(dict.fromkeys(str(operation) for operation in required_operations))
    invalid: list[str] = []
    for operation, spec in workloads.items():
        if operation != spec.operation:
            invalid.append(f"{operation}: operation field is {spec.operation}")
            continue
        try:
            spec.validate()
        except ValueError as error:
            invalid.append(f"{operation}: {error}")
    missing = tuple(operation for operation in required if operation not in workloads)
    passed = not invalid and not missing
    return _evidence(
        "declared_workload_coverage",
        passed,
        "workload declarations cover the required operations"
        if passed
        else "workload declarations are invalid or incomplete",
        {"declared": tuple(sorted(workloads)), "missing": missing, "invalid": tuple(invalid)},
        {"required": required},
    )


def audit_implementation(
    adapters: Iterable[FormatAdapter],
    *,
    lifecycle: Sequence[ExecutionState | str],
    artifact_paths: Iterable[str | Path],
    workloads: Mapping[str, WorkloadSpec],
    required_operations: Iterable[str],
    expected_adapter_count: int | None = None,
    expected_lanes: Mapping[str, Lane | str] | None = None,
    path_root: Path | None = None,
) -> ImplementationAudit:
    """Run the bounded T-DESIGN-AUDIT checks without executing benchmark code."""

    return ImplementationAudit(
        checks=(
            audit_adapters(
                adapters,
                expected_count=expected_adapter_count,
                expected_lanes=expected_lanes,
            ),
            audit_lifecycle(lifecycle),
            audit_safe_relative_paths(artifact_paths, root=path_root),
            audit_workload_coverage(workloads, required_operations),
        )
    )


__all__ = [
    "AuditEvidence",
    "AuditStatus",
    "ImplementationAudit",
    "audit_adapters",
    "audit_implementation",
    "audit_lifecycle",
    "audit_safe_relative_paths",
    "audit_workload_coverage",
]
