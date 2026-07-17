from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import StrEnum
from statistics import median
from typing import Iterable


class EquivalenceVerdict(StrEnum):
    PRACTICALLY_EQUIVALENT = "PRACTICALLY_EQUIVALENT"
    MEANINGFUL_DIFFERENCE = "MEANINGFUL_DIFFERENCE"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class EquivalenceBounds:
    size_ratio: float = 0.02
    p50_ratio: float = 0.05
    p95_ratio: float = 0.10

    def for_metric(self, metric: str) -> float:
        try:
            return {
                "native_bytes": self.size_ratio,
                "transport_zstd_bytes": self.size_ratio,
                "p50_ms": self.p50_ratio,
                "p95_ms": self.p95_ratio,
            }[metric]
        except KeyError as error:
            raise ValueError(f"unsupported equivalence metric: {metric}") from error


@dataclass(frozen=True)
class RatioInterval:
    metric: str
    ratio: float
    lower: float
    upper: float


def classify_interval(
    interval: RatioInterval, bounds: EquivalenceBounds
) -> str:
    delta = bounds.for_metric(interval.metric)
    lower = 1.0 - delta
    upper = 1.0 + delta
    if interval.lower >= lower and interval.upper <= upper:
        return EquivalenceVerdict.PRACTICALLY_EQUIVALENT
    if interval.upper < lower or interval.lower > upper:
        return EquivalenceVerdict.MEANINGFUL_DIFFERENCE
    return EquivalenceVerdict.INCONCLUSIVE


def classify_metrics(
    intervals: Iterable[RatioInterval], bounds: EquivalenceBounds | None = None
) -> str:
    bounds = bounds or EquivalenceBounds()
    metrics = tuple(intervals)
    if not metrics:
        return EquivalenceVerdict.NOT_APPLICABLE
    verdicts = {classify_interval(item, bounds) for item in metrics}
    if EquivalenceVerdict.MEANINGFUL_DIFFERENCE in verdicts:
        return EquivalenceVerdict.MEANINGFUL_DIFFERENCE
    if verdicts == {EquivalenceVerdict.PRACTICALLY_EQUIVALENT}:
        return EquivalenceVerdict.PRACTICALLY_EQUIVALENT
    return EquivalenceVerdict.INCONCLUSIVE


def bootstrap_ratio_interval(
    reference: Iterable[float],
    candidate: Iterable[float],
    *,
    metric: str,
    seed: int = 20260703,
    samples: int = 2000,
) -> RatioInterval:
    """Estimate an independent ratio interval; samples are not trial-paired."""
    left = tuple(float(value) for value in reference)
    right = tuple(float(value) for value in candidate)
    if not left or not right:
        raise ValueError("ratio samples must be non-empty")
    if samples <= 0:
        raise ValueError("bootstrap samples must be positive")
    if any(not math.isfinite(value) or value <= 0 for value in left + right):
        raise ValueError("ratio samples must be finite and positive")
    point = median(right) / median(left)
    rng = random.Random(seed)
    bootstrapped: list[float] = []
    for _ in range(samples):
        left_median = median(left[rng.randrange(len(left))] for _ in left)
        right_median = median(right[rng.randrange(len(right))] for _ in right)
        bootstrapped.append(right_median / left_median)
    bootstrapped.sort()
    lower_index = max(0, int(0.025 * len(bootstrapped)) - 1)
    upper_index = min(len(bootstrapped) - 1, int(0.975 * len(bootstrapped)))
    return RatioInterval(
        metric, point, bootstrapped[lower_index], bootstrapped[upper_index]
    )
