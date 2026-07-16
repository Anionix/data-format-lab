from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence


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


def summarize_cases(cases: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    """Aggregate robustness cases without turning them into a score."""

    groups: dict[str, dict[str, object]] = {}
    for case in cases:
        target = _value(case.get("target", "unknown"))
        group = groups.setdefault(
            target,
            {
                "tier": _value(case.get("tier", "N/A")),
                "cases": 0,
                "applicable": 0,
                "pass": 0,
                "fail": 0,
                "incomplete": 0,
                "crashed": 0,
                "timed_out": 0,
                "unsupported": 0,
                "harness_failed": 0,
                "budget_exhausted": 0,
                "durations": [],
                "artifact_sha256": set(),
                "source_identities": set(),
            },
        )
        group["cases"] = int(group["cases"]) + 1
        verdict = _value(case.get("verdict"))
        observed = _value(case.get("observed"))
        if verdict != "NOT_APPLICABLE":
            group["applicable"] = int(group["applicable"]) + 1
        if verdict == "PASS":
            group["pass"] = int(group["pass"]) + 1
        elif verdict == "FAIL":
            group["fail"] = int(group["fail"]) + 1
        elif verdict == "INCOMPLETE":
            group["incomplete"] = int(group["incomplete"]) + 1
        for outcome, field in {
            "CRASHED": "crashed",
            "TIMED_OUT": "timed_out",
            "UNSUPPORTED": "unsupported",
            "HARNESS_FAILED": "harness_failed",
            "BUDGET_EXHAUSTED": "budget_exhausted",
        }.items():
            if observed == outcome:
                group[field] = int(group[field]) + 1

        process = case.get("process")
        if isinstance(process, Mapping) and isinstance(process.get("duration_ms"), (int, float)):
            durations = group["durations"]
            assert isinstance(durations, list)
            durations.append(float(process["duration_ms"]))
        artifact_hashes = group["artifact_sha256"]
        assert isinstance(artifact_hashes, set)
        records = case.get("artifact_records")
        if isinstance(records, Sequence) and not isinstance(records, (str, bytes)):
            for record in records:
                artifact_hashes.update(_hash_values(record))
        source_identities = group["source_identities"]
        assert isinstance(source_identities, set)
        source_identities.update(_hash_values(case.get("details")))

    result: dict[str, dict[str, object]] = {}
    for target, group in sorted(groups.items()):
        durations = group.pop("durations")
        assert isinstance(durations, list)
        group["duration_ms_p50"] = round(statistics.median(durations), 3) if durations else None
        for field in ("artifact_sha256", "source_identities"):
            values = group[field]
            assert isinstance(values, set)
            group[field] = sorted(values)
        result[target] = group
    return result
