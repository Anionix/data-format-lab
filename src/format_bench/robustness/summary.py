from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TypedDict


TargetSummary = TypedDict(
    "TargetSummary",
    {
        "tier": str,
        "cases": int,
        "applicable": int,
        "pass": int,
        "fail": int,
        "incomplete": int,
        "crashed": int,
        "timed_out": int,
        "unsupported": int,
        "harness_failed": int,
        "budget_exhausted": int,
        "duration_ms_p50": float | None,
        "artifact_sha256": list[str],
        "source_identities": list[str],
    },
)


@dataclass
class _TargetAccumulator:
    tier: str
    cases: int = 0
    applicable: int = 0
    passed: int = 0
    fail: int = 0
    incomplete: int = 0
    crashed: int = 0
    timed_out: int = 0
    unsupported: int = 0
    harness_failed: int = 0
    budget_exhausted: int = 0
    durations: list[float] = field(default_factory=list)
    artifact_sha256: set[str] = field(default_factory=set)
    source_identities: set[str] = field(default_factory=set)

    def observe_outcome(self, observed: str) -> None:
        if observed == "CRASHED":
            self.crashed += 1
        elif observed == "TIMED_OUT":
            self.timed_out += 1
        elif observed == "UNSUPPORTED":
            self.unsupported += 1
        elif observed == "HARNESS_FAILED":
            self.harness_failed += 1
        elif observed == "BUDGET_EXHAUSTED":
            self.budget_exhausted += 1

    def emit(self) -> TargetSummary:
        return {
            "tier": self.tier,
            "cases": self.cases,
            "applicable": self.applicable,
            "pass": self.passed,
            "fail": self.fail,
            "incomplete": self.incomplete,
            "crashed": self.crashed,
            "timed_out": self.timed_out,
            "unsupported": self.unsupported,
            "harness_failed": self.harness_failed,
            "budget_exhausted": self.budget_exhausted,
            "duration_ms_p50": (
                round(statistics.median(self.durations), 3) if self.durations else None
            ),
            "artifact_sha256": sorted(self.artifact_sha256),
            "source_identities": sorted(self.source_identities),
        }


def _value(value: object) -> str:
    enum_value = getattr(value, "value", value)
    return str(enum_value)


def _hash_values(value: object) -> set[str]:
    if not isinstance(value, Mapping):
        return set()
    found: set[str] = set()
    for key, item in value.items():
        if isinstance(item, str) and (
            str(key).endswith("_sha256") or str(key) in {"source_commit", "binary_sha256"}
            or str(key) == "sha256"
        ):
            found.add(item)
        elif str(key) in {"source_commits", "identities"}:
            found.update(_hash_values(item))
    return found


def summarize_cases(cases: Sequence[Mapping[str, object]]) -> dict[str, TargetSummary]:
    """Aggregate robustness cases without turning them into a score."""

    groups: dict[str, _TargetAccumulator] = {}
    for case in cases:
        target = _value(case.get("target", "unknown"))
        group = groups.setdefault(
            target,
            _TargetAccumulator(tier=_value(case.get("tier", "N/A"))),
        )
        group.cases += 1
        verdict = _value(case.get("verdict"))
        observed = _value(case.get("observed"))
        if verdict != "NOT_APPLICABLE":
            group.applicable += 1
        if verdict == "PASS":
            group.passed += 1
        elif verdict == "FAIL":
            group.fail += 1
        elif verdict == "INCOMPLETE":
            group.incomplete += 1
        group.observe_outcome(observed)

        process = case.get("process")
        duration = process.get("duration_ms") if isinstance(process, Mapping) else None
        if isinstance(duration, (int, float)):
            group.durations.append(float(duration))
        records = case.get("artifact_records")
        if isinstance(records, Sequence) and not isinstance(records, (str, bytes)):
            for record in records:
                group.artifact_sha256.update(_hash_values(record))
        group.source_identities.update(_hash_values(case.get("details")))

    result: dict[str, TargetSummary] = {}
    for target, group in sorted(groups.items()):
        result[target] = group.emit()
    return result
