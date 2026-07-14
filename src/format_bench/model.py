from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType


class Lane(StrEnum):
    FAIR = "fair"
    CLAIMS = "claims"
    PROMPT = "prompt"


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
    allowed = _NEXT[current] | (_FAILURES if current in _ACTIVE else frozenset())
    if target not in allowed:
        raise ValueError(f"illegal evidence transition: {current} -> {target}")
    return target


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    arrow_type: str
    nullable: bool = True


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
