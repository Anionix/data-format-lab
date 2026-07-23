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
from format_bench.equivalence_compare import PAIR_SPECS, pair_contract, pair_evidence
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
