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


@pytest.mark.parametrize(
    "reference,candidate,samples",
    [([], [1.0], 10), ([1.0], [], 10), ([1.0], [1.0], 0)],
)
def test_bootstrap_ratio_rejects_invalid_inputs(
    reference: list[float], candidate: list[float], samples: int
) -> None:
    with pytest.raises(ValueError):
        bootstrap_ratio_interval(
            reference, candidate, metric="p50_ms", samples=samples
        )
