from __future__ import annotations

from typing import TypedDict

from .equivalence import (
    EquivalenceBounds,
    EquivalenceVerdict,
    RatioInterval,
    bootstrap_ratio_interval,
    classify_metrics,
)
from .fair import OPERATIONS
from .model import Lane


class PairSpec(TypedDict):
    lane: Lane
    allowed_lanes: tuple[Lane, ...]
    reference: str
    candidates: tuple[str, ...]


PAIR_SPECS: dict[str, PairSpec] = {
    "csv-tsv": {
        "lane": Lane.EQUIVALENCE,
        "allowed_lanes": (Lane.FAIR, Lane.EQUIVALENCE),
        "reference": "csv",
        "candidates": ("tsv",),
    },
    "arrow-feather": {
        "lane": Lane.EQUIVALENCE,
        "allowed_lanes": (Lane.FAIR, Lane.EQUIVALENCE),
        "reference": "arrow_ipc",
        "candidates": ("feather_v2",),
    },
    "parquet-orc": {
        "lane": Lane.EQUIVALENCE,
        "allowed_lanes": (Lane.FAIR, Lane.EQUIVALENCE),
        "reference": "parquet_default",
        "candidates": ("orc_zlib",),
    },
    "jsonl-avro": {
        "lane": Lane.EQUIVALENCE,
        "allowed_lanes": (Lane.FAIR, Lane.EQUIVALENCE),
        "reference": "object_jsonl",
        "candidates": ("avro_ocf",),
    },
    "jsonl-msgpack-cbor": {
        "lane": Lane.EQUIVALENCE,
        "allowed_lanes": (Lane.FAIR, Lane.EQUIVALENCE),
        "reference": "object_jsonl",
        "candidates": ("msgpack_rows", "cbor_rows"),
    },
    "sqlite-duckdb": {
        "lane": Lane.ENGINE_CONTAINER,
        "allowed_lanes": (Lane.ENGINE_CONTAINER,),
        "reference": "sqlite_db",
        "candidates": ("duckdb_db",),
    },
}


def _interval_json(interval: RatioInterval) -> dict[str, float | str]:
    return {
        "metric": interval.metric,
        "ratio": interval.ratio,
        "lower": interval.lower,
        "upper": interval.upper,
    }


def _exact_interval(metric: str, reference: float, candidate: float) -> RatioInterval:
    if reference <= 0 or candidate <= 0:
        raise ValueError(f"{metric} values must be positive")
    ratio = candidate / reference
    return RatioInterval(metric, ratio, ratio, ratio)


def _not_applicable(reason: str) -> dict:
    return {
        "verdict": EquivalenceVerdict.NOT_APPLICABLE,
        "failure_reason": reason,
        "storage": {},
        "operations": {},
    }


def compare_candidate(
    reference: dict,
    candidate: dict,
    *,
    bounds: EquivalenceBounds,
    seed: int,
    operations: tuple[str, ...] | None = None,
) -> dict:
    operation_names = operations or tuple(operation.value for operation in OPERATIONS)
    if reference.get("status") != "MEASURED" or candidate.get("status") != "MEASURED":
        return _not_applicable("one or more benchmark jobs failed")
    reference_operations = reference["operations"]
    candidate_operations = candidate["operations"]
    if any(
        len(reference_operations[operation].get("warm_process_p50_ms", ())) < 2
        or len(candidate_operations[operation].get("warm_process_p50_ms", ())) < 2
        for operation in operation_names
    ):
        return {
            "verdict": EquivalenceVerdict.INCONCLUSIVE,
            "failure_reason": "at least two fresh-process samples are required for an interval",
            "storage": {},
            "operations": {},
        }

    storage_intervals = [
        _exact_interval("native_bytes", reference["native_bytes"], candidate["native_bytes"]),
        _exact_interval(
            "transport_zstd_bytes",
            reference["transport_zstd_bytes"],
            candidate["transport_zstd_bytes"],
        ),
    ]
    operations: dict[str, dict] = {}
    all_intervals = list(storage_intervals)
    for offset, operation in enumerate(operation_names):
        reference_evidence = reference_operations[operation]
        candidate_evidence = candidate_operations[operation]
        intervals = [
            bootstrap_ratio_interval(
                reference_evidence["warm_process_p50_ms"],
                candidate_evidence["warm_process_p50_ms"],
                metric="p50_ms",
                seed=seed + offset * 2,
            ),
            bootstrap_ratio_interval(
                reference_evidence["warm_process_p95_ms"],
                candidate_evidence["warm_process_p95_ms"],
                metric="p95_ms",
                seed=seed + offset * 2 + 1,
            ),
        ]
        all_intervals.extend(intervals)
        operations[operation] = {
            "verdict": classify_metrics(intervals, bounds),
            "metrics": [_interval_json(item) for item in intervals],
        }
    return {
        "verdict": classify_metrics(all_intervals, bounds),
        "failure_reason": None,
        "storage": {
            "verdict": classify_metrics(storage_intervals, bounds),
            "metrics": [_interval_json(item) for item in storage_intervals],
        },
        "operations": operations,
    }


def pair_evidence(
    spec: PairSpec,
    measured: dict[str, dict],
    entries: dict[str, dict],
    bounds: EquivalenceBounds,
    seed: int,
    operations: tuple[str, ...] | None = None,
) -> dict:
    operation_names = operations or tuple(operation.value for operation in OPERATIONS)
    reference_name = spec["reference"]
    names = (reference_name, *spec["candidates"])
    formats: dict[str, dict] = {}
    for candidate_name in spec["candidates"]:
        reference = {
            **entries[reference_name],
            "status": "MEASURED",
            "operations": {
                operation: measured[f"{reference_name}/{operation}"]
                for operation in operation_names
            },
        }
        candidate = {
            **entries[candidate_name],
            "status": "MEASURED",
            "operations": {
                operation: measured[f"{candidate_name}/{operation}"]
                for operation in operation_names
            },
        }
        formats[candidate_name] = compare_candidate(
            reference, candidate, bounds=bounds, seed=seed, operations=operation_names
        )
    verdicts = [item["verdict"] for item in formats.values()]
    if any(item == EquivalenceVerdict.MEANINGFUL_DIFFERENCE for item in verdicts):
        verdict = EquivalenceVerdict.MEANINGFUL_DIFFERENCE
    elif all(item == EquivalenceVerdict.PRACTICALLY_EQUIVALENT for item in verdicts):
        verdict = EquivalenceVerdict.PRACTICALLY_EQUIVALENT
    elif any(item == EquivalenceVerdict.INCONCLUSIVE for item in verdicts):
        verdict = EquivalenceVerdict.INCONCLUSIVE
    else:
        verdict = EquivalenceVerdict.NOT_APPLICABLE
    return {
        "lane": spec["lane"],
        "reference": reference_name,
        "candidates": spec["candidates"],
        "verdict": verdict,
        "formats": formats,
        "measured_formats": names,
    }
