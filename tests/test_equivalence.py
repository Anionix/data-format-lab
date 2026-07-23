from __future__ import annotations

import pytest

from format_bench.equivalence import (
    EquivalenceBounds,
    EquivalenceVerdict,
    RatioInterval,
    bootstrap_ratio_interval,
    classify_interval,
    classify_metrics,
)
from format_bench.equivalence_compare import (
    PAIR_SPECS,
    compare_candidate,
    multiplicity_control,
    pair_contract,
    pair_evidence,
)
from format_bench.formats import OrcAdapter, ParquetAdapter


def test_equivalence_bounds_distinguish_inside_outside_and_crossing_intervals() -> None:
    bounds = EquivalenceBounds()
    assert (
        classify_interval(RatioInterval("native_bytes", 1.0, 0.99, 1.01), bounds)
        == EquivalenceVerdict.PRACTICALLY_EQUIVALENT
    )
    assert (
        classify_interval(RatioInterval("native_bytes", 1.2, 1.1, 1.3), bounds)
        == EquivalenceVerdict.MEANINGFUL_DIFFERENCE
    )
    assert (
        classify_interval(RatioInterval("native_bytes", 1.02, 1.0, 1.04), bounds)
        == EquivalenceVerdict.INCONCLUSIVE
    )
    assert classify_metrics((), bounds) == EquivalenceVerdict.NOT_APPLICABLE


def test_bootstrap_ratio_uses_independent_samples_and_is_seeded() -> None:
    first = bootstrap_ratio_interval(
        [10.0, 11.0, 12.0],
        [20.0, 22.0, 24.0],
        metric="p50_ms",
        seed=7,
        samples=100,
    )
    second = bootstrap_ratio_interval(
        [10.0, 11.0, 12.0],
        [20.0, 22.0, 24.0],
        metric="p50_ms",
        seed=7,
        samples=100,
    )
    assert first == second
    assert first.ratio == pytest.approx(2.0)
    assert first.lower <= first.ratio <= first.upper


def test_bootstrap_ratio_supports_bonferroni_comparison_alpha() -> None:
    pointwise = bootstrap_ratio_interval(
        [8.0, 9.0, 10.0, 11.0, 12.0],
        [9.0, 10.0, 11.0, 12.0, 14.0],
        metric="p50_ms",
        seed=7,
        samples=1000,
        alpha=0.05,
    )
    simultaneous = bootstrap_ratio_interval(
        [8.0, 9.0, 10.0, 11.0, 12.0],
        [9.0, 10.0, 11.0, 12.0, 14.0],
        metric="p50_ms",
        seed=7,
        samples=1000,
        alpha=multiplicity_control()["comparison_alpha"],
    )

    assert simultaneous.lower <= pointwise.lower
    assert simultaneous.upper >= pointwise.upper


def test_pair_registry_preregisters_one_primary_endpoint() -> None:
    assert {
        (spec["primary_endpoint"]["scope"], spec["primary_endpoint"]["metric"])
        for spec in PAIR_SPECS.values()
    } == {("storage", "native_bytes")}


def test_registered_pair_candidate_family_uses_bonferroni_control() -> None:
    control = multiplicity_control()

    assert control["planned_pairs"] == tuple(PAIR_SPECS)
    assert control["planned_comparisons"] == 7
    assert control["comparison_alpha"] == pytest.approx(0.05 / 7)
    assert control["secondary_metrics"] == "descriptive_only"
    assert control["cross_pair_inference"] == "simultaneous"
    assert control["error_control_target"] == "FWER"
    assert control["status"] == "PREREGISTERED_NO_COVERAGE"


@pytest.mark.parametrize(
    ("candidate_native_bytes", "candidate_transport_bytes", "candidate_p95", "expected"),
    [
        (101, 200, 2.0, EquivalenceVerdict.PRACTICALLY_EQUIVALENT),
        (120, 100, 1.0, EquivalenceVerdict.MEANINGFUL_DIFFERENCE),
    ],
)
def test_primary_endpoint_alone_controls_candidate_verdict(
    candidate_native_bytes: int,
    candidate_transport_bytes: int,
    candidate_p95: float,
    expected: EquivalenceVerdict,
) -> None:
    operation = {
        "warm_process_p50_ms": [1.0, 1.0],
        "warm_process_p95_ms": [1.0, 1.0],
    }
    comparison = compare_candidate(
        {
            "status": "MEASURED",
            "native_bytes": 100,
            "transport_zstd_bytes": 100,
            "operations": {"read_all": operation},
        },
        {
            "status": "MEASURED",
            "native_bytes": candidate_native_bytes,
            "transport_zstd_bytes": candidate_transport_bytes,
            "operations": {
                "read_all": {
                    **operation,
                    "warm_process_p95_ms": [candidate_p95, candidate_p95],
                }
            },
        },
        bounds=EquivalenceBounds(),
        seed=7,
        primary_endpoint={"scope": "storage", "metric": "native_bytes"},
        operations=("read_all",),
    )

    assert comparison["verdict"] == expected
    assert comparison["verdict_basis"] == "primary_endpoint"
    assert comparison["primary_endpoint"]["metric"] == "native_bytes"
    if expected is EquivalenceVerdict.PRACTICALLY_EQUIVALENT:
        assert comparison["storage"]["verdict"] is EquivalenceVerdict.MEANINGFUL_DIFFERENCE
        assert (
            comparison["operations"]["read_all"]["verdict"]
            is EquivalenceVerdict.MEANINGFUL_DIFFERENCE
        )


def test_parquet_orc_declares_the_remaining_reader_asymmetry() -> None:
    spec = PAIR_SPECS["parquet-orc"]

    assert spec["comparison_scope"] == "configured_system"
    assert spec["execution_plan"] == {
        "parquet_default": {
            "projection_pushdown": True,
            "predicate_pushdown": True,
        },
        "orc_zlib": {
            "projection_pushdown": True,
            "predicate_pushdown": False,
        },
    }
    assert spec["writer_plan"] == {
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
    }
    assert spec["writer_plan"]["parquet_default"] == (
        ParquetAdapter().describe().settings
    )
    assert spec["writer_plan"]["orc_zlib"] == OrcAdapter().describe().settings
    assert "predicate" in spec["accepted_risk"]
    assert "codec" in spec["accepted_risk"]
    assert pair_contract(spec)["accepted_risk"] == spec["accepted_risk"]

    samples = {
        f"{name}/read_all": {
            "warm_process_p50_ms": [1.0, 1.0],
            "warm_process_p95_ms": [1.0, 1.0],
        }
        for name in ("parquet_default", "orc_zlib")
    }
    entries = {
        name: {"native_bytes": 10, "transport_zstd_bytes": 10}
        for name in ("parquet_default", "orc_zlib")
    }
    evidence = pair_evidence(
        spec,
        samples,
        entries,
        EquivalenceBounds(),
        seed=1,
        operations=("read_all",),
    )

    assert evidence["execution_plan"] == spec["execution_plan"]
    assert evidence["writer_plan"] == spec["writer_plan"]
    assert evidence["accepted_risk"] == spec["accepted_risk"]


@pytest.mark.parametrize(
    "reference,candidate,samples",
    [([], [1.0], 10), ([1.0], [], 10), ([1.0], [1.0], 0)],
)
def test_bootstrap_ratio_rejects_invalid_inputs(
    reference: list[float], candidate: list[float], samples: int
) -> None:
    with pytest.raises(ValueError):
        bootstrap_ratio_interval(reference, candidate, metric="p50_ms", samples=samples)


@pytest.mark.parametrize("alpha", [0.0, 1.0, -0.1])
def test_bootstrap_ratio_rejects_invalid_alpha(alpha: float) -> None:
    with pytest.raises(ValueError, match="alpha"):
        bootstrap_ratio_interval([1.0], [1.0], metric="p50_ms", alpha=alpha)
