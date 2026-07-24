from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from .equivalence import (
    EquivalenceBounds,
    EquivalenceVerdict,
    RatioInterval,
    bootstrap_ratio_interval,
    classify_interval,
    classify_metrics,
)
from .fair import OPERATIONS
from .model import Lane

EQUIVALENCE_CONTRACT_VERSION = "2"


class PrimaryEndpoint(TypedDict):
    scope: Literal["storage", "operation"]
    metric: Literal["native_bytes", "transport_zstd_bytes", "p50_ms", "p95_ms"]
    operation: NotRequired[str]


class StorageEstimand(TypedDict):
    metric: Literal["native_bytes"]
    grouping: Literal["format"]
    numerator: Literal["candidate_group_median"]
    denominator: Literal["reference_group_median"]
    point_estimator: Literal["candidate_group_median_divided_by_reference_group_median"]
    interval_estimator: Literal["unpaired_ratio_of_medians"]
    resampling_unit: Literal["same_process_encode_invocation"]
    interval_method: Literal["bootstrap_percentile"]
    coverage_claim: Literal["none"]


class MultiplicityControl(TypedDict):
    contract_version: Literal["1"]
    error_control_target: Literal["FWER"]
    method: Literal["bonferroni_simultaneous_intervals"]
    family_id: str
    family_scope: Literal["registered_pairs"]
    dimensions: tuple[str, ...]
    family_alpha: float
    planned_pairs: tuple[str, ...]
    planned_comparisons: int
    comparison_alpha: float
    secondary_metrics: Literal["descriptive_only"]
    cross_pair_inference: Literal["simultaneous"]
    primary_interval_method: Literal["bootstrap_percentile"]
    coverage_claim: Literal["none"]
    status: Literal["PREREGISTERED_NO_COVERAGE"]
    accepted_risk: str


class PairSpec(TypedDict):
    lane: Lane
    allowed_lanes: tuple[Lane, ...]
    reference: str
    candidates: tuple[str, ...]
    comparison_scope: NotRequired[Literal["configured_system"]]
    execution_plan: NotRequired[dict[str, "ExecutionPlan"]]
    writer_plan: NotRequired[dict[str, dict[str, object]]]
    accepted_risk: NotRequired[str]
    primary_endpoint: PrimaryEndpoint


class ExecutionPlan(TypedDict):
    projection_pushdown: bool
    predicate_pushdown: bool


PRIMARY_ENDPOINT: PrimaryEndpoint = {
    "scope": "storage",
    "metric": "native_bytes",
}
FAMILY_ALPHA = 0.05

STORAGE_ESTIMAND: StorageEstimand = {
    "metric": "native_bytes",
    "grouping": "format",
    "numerator": "candidate_group_median",
    "denominator": "reference_group_median",
    "point_estimator": "candidate_group_median_divided_by_reference_group_median",
    "interval_estimator": "unpaired_ratio_of_medians",
    "resampling_unit": "same_process_encode_invocation",
    "interval_method": "bootstrap_percentile",
    "coverage_claim": "none",
}


PAIR_SPECS: dict[str, PairSpec] = {
    "csv-tsv": {
        "lane": Lane.EQUIVALENCE,
        "allowed_lanes": (Lane.FAIR, Lane.EQUIVALENCE),
        "reference": "csv",
        "candidates": ("tsv",),
        "primary_endpoint": PRIMARY_ENDPOINT,
    },
    "arrow-feather": {
        "lane": Lane.EQUIVALENCE,
        "allowed_lanes": (Lane.FAIR, Lane.EQUIVALENCE),
        "reference": "arrow_ipc",
        "candidates": ("feather_v2",),
        "primary_endpoint": PRIMARY_ENDPOINT,
    },
    "parquet-orc": {
        "lane": Lane.EQUIVALENCE,
        "allowed_lanes": (Lane.FAIR, Lane.EQUIVALENCE),
        "reference": "parquet_default",
        "candidates": ("orc_zlib",),
        "primary_endpoint": PRIMARY_ENDPOINT,
        "comparison_scope": "configured_system",
        "execution_plan": {
            "parquet_default": {
                "projection_pushdown": True,
                "predicate_pushdown": True,
            },
            "orc_zlib": {
                "projection_pushdown": True,
                "predicate_pushdown": False,
            },
        },
        "writer_plan": {
            "parquet_default": {
                "compression": "zstd",
                "level": "library-default",
                "dictionary": True,
            },
            "orc_zlib": {
                "compression": "zlib",
                "compression_strategy": "speed",
                "dictionary_key_size_threshold": 0.0,
            },
        },
        "accepted_risk": (
            "PyArrow ORC predicate evaluation remains post-read; timing therefore "
            "compares configured reader systems, not isolated format layouts. "
            "Writer codecs also differ: Parquet uses Zstd and ORC uses Zlib."
        ),
    },
    "jsonl-avro": {
        "lane": Lane.EQUIVALENCE,
        "allowed_lanes": (Lane.FAIR, Lane.EQUIVALENCE),
        "reference": "object_jsonl",
        "candidates": ("avro_ocf",),
        "primary_endpoint": PRIMARY_ENDPOINT,
    },
    "jsonl-msgpack-cbor": {
        "lane": Lane.EQUIVALENCE,
        "allowed_lanes": (Lane.FAIR, Lane.EQUIVALENCE),
        "reference": "object_jsonl",
        "candidates": ("msgpack_rows", "cbor_rows"),
        "primary_endpoint": PRIMARY_ENDPOINT,
    },
    "sqlite-duckdb": {
        "lane": Lane.ENGINE_CONTAINER,
        "allowed_lanes": (Lane.ENGINE_CONTAINER,),
        "reference": "sqlite_db",
        "candidates": ("duckdb_db",),
        "primary_endpoint": PRIMARY_ENDPOINT,
    },
}


def multiplicity_control() -> MultiplicityControl:
    planned_pairs = tuple(PAIR_SPECS)
    planned_comparisons = sum(len(spec["candidates"]) for spec in PAIR_SPECS.values())
    if planned_comparisons < 1:
        raise ValueError("equivalence registry needs at least one candidate")
    return {
        "contract_version": "1",
        "error_control_target": "FWER",
        "method": "bonferroni_simultaneous_intervals",
        "family_id": "equivalence.primary.v2",
        "family_scope": "registered_pairs",
        "dimensions": ("pair", "candidate"),
        "family_alpha": FAMILY_ALPHA,
        "planned_pairs": planned_pairs,
        "planned_comparisons": planned_comparisons,
        "comparison_alpha": FAMILY_ALPHA / planned_comparisons,
        "secondary_metrics": "descriptive_only",
        "cross_pair_inference": "simultaneous",
        "primary_interval_method": "bootstrap_percentile",
        "coverage_claim": "none",
        "status": "PREREGISTERED_NO_COVERAGE",
        "accepted_risk": (
            "Bonferroni allocation is preregistered, but same-process repeated "
            "encoding intervals have no validated coverage; bootstrap coverage "
            "validation remains tracked by issue #271."
        ),
    }


def pair_contract(spec: PairSpec) -> dict[str, object]:
    contract: dict[str, object] = {
        "primary_endpoint": dict(spec["primary_endpoint"]),
        "verdict_basis": "primary_endpoint",
        "storage_estimand": STORAGE_ESTIMAND.copy(),
        "multiplicity_control": multiplicity_control(),
    }
    if "comparison_scope" in spec:
        contract["comparison_scope"] = spec["comparison_scope"]
    if "execution_plan" in spec:
        contract["execution_plan"] = spec["execution_plan"]
    if "writer_plan" in spec:
        contract["writer_plan"] = spec["writer_plan"]
    if "accepted_risk" in spec:
        contract["accepted_risk"] = spec["accepted_risk"]
    return contract


def _interval_json(interval: RatioInterval) -> dict[str, object]:
    payload: dict[str, object] = {
        "metric": interval.metric,
        "ratio": interval.ratio,
        "lower": interval.lower,
        "upper": interval.upper,
    }
    if interval.bootstrap is not None:
        evidence = interval.bootstrap
        payload["bootstrap"] = {
            "method": evidence.method,
            "samples": evidence.samples,
            "seed": evidence.seed,
            "alpha": evidence.alpha,
            "quantile_rule": evidence.quantile_rule,
            "lower_index": evidence.lower_index,
            "upper_index": evidence.upper_index,
            "resampling_unit": evidence.resampling_unit,
            "reference_observations": evidence.reference_observations,
            "candidate_observations": evidence.candidate_observations,
            "rng": evidence.rng,
            "runtime": evidence.runtime,
        }
    return payload


def _primary_endpoint_contract(primary_endpoint: PrimaryEndpoint) -> dict[str, object]:
    payload = dict(primary_endpoint)
    if primary_endpoint["scope"] == "storage":
        payload["storage_estimand"] = STORAGE_ESTIMAND.copy()
    return payload


def _not_applicable(reason: str, primary_endpoint: PrimaryEndpoint) -> dict:
    return {
        "verdict": EquivalenceVerdict.NOT_APPLICABLE,
        "verdict_basis": "primary_endpoint",
        "primary_endpoint": _primary_endpoint_contract(primary_endpoint),
        "failure_reason": reason,
        "storage": {},
        "operations": {},
    }


def _primary_interval(
    primary_endpoint: PrimaryEndpoint,
    storage: list[RatioInterval],
    operations: dict[str, list[RatioInterval]],
) -> RatioInterval:
    scope = primary_endpoint["scope"]
    if scope == "storage":
        intervals = storage
    else:
        operation = primary_endpoint.get("operation")
        if operation is None or operation not in operations:
            raise ValueError("primary operation endpoint is unavailable")
        intervals = operations[operation]
    matches = [
        interval
        for interval in intervals
        if interval.metric == primary_endpoint["metric"]
    ]
    if len(matches) != 1:
        raise ValueError("primary endpoint must resolve to exactly one interval")
    return matches[0]


def _size_samples(entry: dict, metric: str) -> tuple[int, ...]:
    evidence = entry.get("size_observations")
    if not isinstance(evidence, dict):
        return ()
    attempts = evidence.get("attempts")
    if (
        evidence.get("contract_version") != "1"
        or evidence.get("resampling_unit") != "same_process_encode_invocation"
        or not isinstance(attempts, list)
        or evidence.get("attempted") != evidence.get("completed")
        or evidence.get("completed") != len(attempts)
    ):
        return ()
    values = []
    for expected_index, attempt in enumerate(attempts):
        if not isinstance(attempt, dict):
            return ()
        value = attempt.get(metric)
        digest = attempt.get("artifact_sha256")
        if (
            attempt.get("index") != expected_index
            or attempt.get("status") != "MEASURED"
            or attempt.get("roundtrip_verified") is not True
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            return ()
        values.append(value)
    return tuple(values)


def _storage_evidence(
    reference: dict,
    candidate: dict,
    *,
    bounds: EquivalenceBounds,
    seed: int,
    primary_endpoint: PrimaryEndpoint,
    comparison_alpha: float,
) -> tuple[list[RatioInterval], dict]:
    intervals = []
    records = []
    missing = []
    for offset, metric in enumerate(("native_bytes", "transport_zstd_bytes")):
        reference_samples = _size_samples(reference, metric)
        candidate_samples = _size_samples(candidate, metric)
        if len(reference_samples) < 2 or len(candidate_samples) < 2:
            missing.append(metric)
            records.append(
                {
                    "metric": metric,
                    "verdict": EquivalenceVerdict.NOT_APPLICABLE,
                    "failure_reason": "incomplete repeated encoding observations",
                    "reference_observations": len(reference_samples),
                    "candidate_observations": len(candidate_samples),
                }
            )
            continue
        interval = bootstrap_ratio_interval(
            reference_samples,
            candidate_samples,
            metric=metric,
            seed=seed + 10_000 + offset,
            alpha=(
                comparison_alpha
                if primary_endpoint == {"scope": "storage", "metric": metric}
                else FAMILY_ALPHA
            ),
            resampling_unit="same_process_encode_invocation",
        )
        intervals.append(interval)
        records.append(
            {
                **_interval_json(interval),
                "verdict": classify_interval(interval, bounds),
            }
        )
    return intervals, {
        "verdict": (
            EquivalenceVerdict.NOT_APPLICABLE
            if missing
            else classify_metrics(intervals, bounds)
        ),
        "metrics": records,
        "failure_reason": (
            "incomplete repeated encoding observations" if missing else None
        ),
    }


def compare_candidate(
    reference: dict,
    candidate: dict,
    *,
    bounds: EquivalenceBounds,
    seed: int,
    primary_endpoint: PrimaryEndpoint,
    comparison_alpha: float = FAMILY_ALPHA,
    operations: tuple[str, ...] | None = None,
) -> dict:
    operation_names = (
        tuple(operation.value for operation in OPERATIONS)
        if operations is None
        else operations
    )
    if reference.get("status") != "MEASURED" or candidate.get("status") != "MEASURED":
        return _not_applicable("one or more benchmark jobs failed", primary_endpoint)
    reference_operations = reference["operations"]
    candidate_operations = candidate["operations"]
    storage_intervals, storage = _storage_evidence(
        reference,
        candidate,
        bounds=bounds,
        seed=seed,
        primary_endpoint=primary_endpoint,
        comparison_alpha=comparison_alpha,
    )
    operation_results: dict[str, dict] = {}
    operation_intervals: dict[str, list[RatioInterval]] = {}
    for offset, operation in enumerate(operation_names):
        reference_evidence = reference_operations[operation]
        candidate_evidence = candidate_operations[operation]
        intervals = []
        metric_records = []
        missing = []
        for metric_offset, (metric, field) in enumerate(
            (
                ("p50_ms", "warm_process_p50_ms"),
                ("p95_ms", "warm_process_p95_ms"),
            )
        ):
            reference_samples = reference_evidence.get(field, ())
            candidate_samples = candidate_evidence.get(field, ())
            if len(reference_samples) < 2 or len(candidate_samples) < 2:
                missing.append(metric)
                metric_records.append(
                    {
                        "metric": metric,
                        "verdict": EquivalenceVerdict.INCONCLUSIVE,
                        "failure_reason": "fewer than two observations",
                        "reference_observations": len(reference_samples),
                        "candidate_observations": len(candidate_samples),
                    }
                )
                continue
            interval = bootstrap_ratio_interval(
                reference_samples,
                candidate_samples,
                metric=metric,
                seed=seed + offset * 2 + metric_offset,
                alpha=comparison_alpha
                if primary_endpoint
                == {
                    "scope": "operation",
                    "operation": operation,
                    "metric": metric,
                }
                else FAMILY_ALPHA,
            )
            intervals.append(interval)
            metric_records.append(
                {
                    **_interval_json(interval),
                    "verdict": classify_interval(interval, bounds),
                }
            )
        operation_intervals[operation] = intervals
        operation_results[operation] = {
            "verdict": (
                EquivalenceVerdict.INCONCLUSIVE
                if missing
                else classify_metrics(intervals, bounds)
            ),
            "metrics": metric_records,
            "failure_reason": (
                f"fewer than two observations for: {', '.join(missing)}"
                if missing
                else None
            ),
        }
    try:
        primary = _primary_interval(
            primary_endpoint, storage_intervals, operation_intervals
        )
    except ValueError:
        unavailable = (
            EquivalenceVerdict.NOT_APPLICABLE
            if primary_endpoint["scope"] == "storage"
            else EquivalenceVerdict.INCONCLUSIVE
        )
        return {
            "verdict": unavailable,
            "verdict_basis": "primary_endpoint",
            "primary_endpoint": {
                **_primary_endpoint_contract(primary_endpoint),
                "verdict": unavailable,
            },
            "failure_reason": "primary endpoint has insufficient observations",
            "storage": storage,
            "operations": operation_results,
        }
    primary_verdict = classify_interval(primary, bounds)
    primary_evidence = {
        **_primary_endpoint_contract(primary_endpoint),
        **_interval_json(primary),
        "verdict": primary_verdict,
        "comparison_alpha": comparison_alpha,
        "interval_method": "bootstrap_percentile",
        "coverage_claim": (
            "none" if primary_endpoint["scope"] == "storage" else "familywise_target"
        ),
    }
    return {
        "verdict": primary_verdict,
        "verdict_basis": "primary_endpoint",
        "primary_endpoint": primary_evidence,
        "failure_reason": None,
        "storage": storage,
        "operations": operation_results,
    }


def pair_evidence(
    spec: PairSpec,
    measured: dict[str, dict],
    entries: dict[str, dict],
    bounds: EquivalenceBounds,
    seed: int,
    operations: tuple[str, ...] | None = None,
) -> dict:
    operation_names = (
        tuple(operation.value for operation in OPERATIONS)
        if operations is None
        else operations
    )
    reference_name = spec["reference"]
    names = (reference_name, *spec["candidates"])
    formats: dict[str, dict] = {}
    control = multiplicity_control()
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
            reference,
            candidate,
            bounds=bounds,
            seed=seed,
            primary_endpoint=spec["primary_endpoint"],
            comparison_alpha=control["comparison_alpha"],
            operations=operation_names,
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
    # LLM contract: ROUNDTRIP_VERIFIED -> BENCHMARKED records the reader plan
    # before a configured-system comparison can become reportable evidence.
    return {
        "lane": spec["lane"],
        "reference": reference_name,
        "candidates": spec["candidates"],
        "verdict": verdict,
        **pair_contract(spec),
        "formats": formats,
        "measured_formats": names,
    }
