from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import cast

from .workload_contract import (
    ComparisonOperator,
    WorkloadScalar,
    is_comparison_operator,
)


class Lane(StrEnum):
    FAIR = "fair"
    CLAIMS = "claims"
    PROMPT = "prompt"
    ROBUSTNESS = "robustness"
    EQUIVALENCE = "equivalence"
    ENGINE_CONTAINER = "engine_container"


class Comparability(StrEnum):
    FULL_COMPARABLE = "FULL_COMPARABLE"
    ADAPTED = "ADAPTED"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class ExecutionState(StrEnum):
    DISCOVERED = "DISCOVERED"
    ENCODED = "ENCODED"
    ROUNDTRIP_VERIFIED = "ROUNDTRIP_VERIFIED"
    BENCHMARKED = "BENCHMARKED"
    REPORTED = "REPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class RobustnessExpectation(StrEnum):
    MUST_ROUNDTRIP = "MUST_ROUNDTRIP"
    MUST_REJECT = "MUST_REJECT"
    MUST_NOT_CRASH = "MUST_NOT_CRASH"


class ObservedOutcome(StrEnum):
    ROUNDTRIP_EQUAL = "ROUNDTRIP_EQUAL"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    CRASHED = "CRASHED"
    TIMED_OUT = "TIMED_OUT"
    UNSUPPORTED = "UNSUPPORTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    TARGET_FAILED = "TARGET_FAILED"
    HARNESS_FAILED = "HARNESS_FAILED"


class RobustnessVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INCOMPLETE = "INCOMPLETE"


class Applicability(StrEnum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TargetTier(StrEnum):
    CORE = "CORE"
    EXPERIMENTAL = "EXPERIMENTAL"


# LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
# Any active state may terminate as UNSUPPORTED or FAILED; terminal states never rank.
_NEXT: dict[ExecutionState, frozenset[ExecutionState]] = {
    ExecutionState.DISCOVERED: frozenset({ExecutionState.ENCODED}),
    ExecutionState.ENCODED: frozenset({ExecutionState.ROUNDTRIP_VERIFIED}),
    ExecutionState.ROUNDTRIP_VERIFIED: frozenset({ExecutionState.BENCHMARKED}),
    ExecutionState.BENCHMARKED: frozenset({ExecutionState.REPORTED}),
    ExecutionState.REPORTED: frozenset(),
    ExecutionState.UNSUPPORTED: frozenset(),
    ExecutionState.FAILED: frozenset(),
}
_FAILURES = frozenset({ExecutionState.UNSUPPORTED, ExecutionState.FAILED})
_ACTIVE = frozenset(
    {
        ExecutionState.DISCOVERED,
        ExecutionState.ENCODED,
        ExecutionState.ROUNDTRIP_VERIFIED,
        ExecutionState.BENCHMARKED,
    }
)


def transition(current: ExecutionState, target: ExecutionState) -> ExecutionState:
    allowed: frozenset[ExecutionState] = _NEXT[current]
    if current in _ACTIVE:
        allowed = allowed | _FAILURES
    if target not in allowed:
        raise ValueError(f"illegal evidence transition: {current} -> {target}")
    return target


def robustness_verdict(
    expectation: RobustnessExpectation | str,
    observed: ObservedOutcome | str,
    applicability: Applicability | str = Applicability.APPLICABLE,
) -> RobustnessVerdict:
    # Evidence is persisted as JSON strings and may be evaluated after reload.
    expectation = RobustnessExpectation(expectation)
    observed = ObservedOutcome(observed)
    applicability = Applicability(applicability)
    if applicability is Applicability.NOT_APPLICABLE:
        return RobustnessVerdict.NOT_APPLICABLE
    if observed in {
        ObservedOutcome.UNSUPPORTED,
        ObservedOutcome.BUDGET_EXHAUSTED,
        ObservedOutcome.HARNESS_FAILED,
    }:
        return RobustnessVerdict.INCOMPLETE
    if expectation is RobustnessExpectation.MUST_ROUNDTRIP:
        passed = observed is ObservedOutcome.ROUNDTRIP_EQUAL
    elif expectation is RobustnessExpectation.MUST_REJECT:
        passed = observed is ObservedOutcome.REJECTED
    else:
        passed = observed in {
            ObservedOutcome.ROUNDTRIP_EQUAL,
            ObservedOutcome.ACCEPTED,
            ObservedOutcome.REJECTED,
        }
    return RobustnessVerdict.PASS if passed else RobustnessVerdict.FAIL


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    arrow_type: str
    nullable: bool = True


class WorkloadKind(StrEnum):
    READ_ALL = "read_all"
    PROJECTION = "projection"
    FILTER = "filter"
    HEAD = "head"


@dataclass(frozen=True)
class WorkloadSpec:
    """Dataset-declared operation; generic runners never know Stars columns."""

    operation: str
    kind: WorkloadKind
    columns: tuple[str, ...] = ()
    column: str | None = None
    operator: ComparisonOperator | None = None
    value: WorkloadScalar | None = None
    limit: int | None = None
    expected_rows: int | None = None

    @classmethod
    def from_mapping(cls, operation: str, payload: Mapping[str, object]) -> "WorkloadSpec":
        raw_kind = payload.get("kind")
        if not isinstance(raw_kind, str):
            raise ValueError(f"invalid workload kind for {operation}")
        try:
            kind = WorkloadKind(raw_kind)
        except ValueError as error:
            raise ValueError(f"invalid workload kind for {operation}") from error
        raw_columns = payload.get("columns", ())
        if not isinstance(raw_columns, (list, tuple)):
            raise ValueError(f"workload columns for {operation} must be a list")
        untyped_columns = cast(list[object] | tuple[object, ...], raw_columns)
        if not all(isinstance(item, str) and item for item in untyped_columns):
            raise ValueError(f"workload columns for {operation} must contain strings")
        columns = tuple(cast(list[str] | tuple[str, ...], untyped_columns))
        column = payload.get("column")
        raw_operator = payload.get("operator")
        if column is not None and not isinstance(column, str):
            raise ValueError("workload column must be a string")
        operator: ComparisonOperator | None = None
        if raw_operator is not None:
            if not isinstance(raw_operator, str):
                raise ValueError("workload operator must be a string")
            if not is_comparison_operator(raw_operator):
                raise ValueError("workload operator must be supported")
            operator = raw_operator
        value = payload.get("value")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("workload filter value must be a scalar")
        expected = payload.get("expected_rows")
        limit = payload.get("limit")

        def optional_int(value: object, field: str) -> int | None:
            if value is None:
                return None
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"workload {field} must be an integer")
            return value

        spec = cls(
            operation=operation,
            kind=kind,
            columns=columns,
            column=column,
            operator=operator,
            value=value,
            limit=optional_int(limit, "limit"),
            expected_rows=optional_int(expected, "expected_rows"),
        )
        spec.validate()
        return spec

    def validate(self) -> None:
        if not self.operation:
            raise ValueError("workload operation must not be empty")
        if self.kind is WorkloadKind.PROJECTION and not self.columns:
            raise ValueError(f"projection workload {self.operation} needs columns")
        if self.kind is WorkloadKind.FILTER:
            if (
                not self.column
                or self.operator is None
                or self.value is None
            ):
                raise ValueError(f"filter workload {self.operation} needs a supported predicate")
        if self.kind is WorkloadKind.HEAD and (self.limit is None or self.limit <= 0):
            raise ValueError(f"head workload {self.operation} needs a positive limit")
        if self.expected_rows is not None and self.expected_rows < 0:
            raise ValueError(f"workload {self.operation} has a negative expected row count")


@dataclass(frozen=True)
class DatasetSpec:
    schema_version: str
    dataset_id: str
    asset_name: str
    source_sha256: str
    canonical_hash: str
    rows: int
    columns: tuple[ColumnSpec, ...]
    expected_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "expected_counts", MappingProxyType(dict(self.expected_counts))
        )

    def asset_path(self, root: Path) -> Path:
        path = Path(self.asset_name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("dataset asset_name must be a safe relative path")
        return root / path
