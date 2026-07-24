# Equivalence Lane v2

## Primary endpoint contract

Every registered pair declares one primary endpoint before measurement:

```json
{
  "scope": "storage",
  "metric": "native_bytes"
}
```

The runner writes `equivalence.contract_version = "2"` and the
`primary_endpoints` map to the run manifest before starting benchmark jobs.
Each pair record repeats the declaration and sets
`verdict_basis = "primary_endpoint"`.

The pair and candidate verdicts use only this endpoint. Transport size,
operation p50/p95, and all other intervals remain visible secondary evidence;
they cannot change the primary verdict. Historical v1 artifacts retain their
recorded all-metrics verdict and remain reportable as legacy evidence.

`native_bytes` is the primary endpoint because the equivalence lane's
confirmatory question is whether two encoded representations have practically
equivalent storage footprint. It is available for every registered pair.
Transport compression and operation latency depend on additional configured
systems, so they remain secondary.

The machine-readable `storage_estimand` metadata is identical in the run
contract, pair contract, and primary-endpoint evidence:

```json
{
  "metric": "native_bytes",
  "grouping": "format",
  "numerator": "candidate_group_median",
  "denominator": "reference_group_median",
  "point_estimator": "candidate_group_median_divided_by_reference_group_median",
  "interval_estimator": "unpaired_ratio_of_medians",
  "resampling_unit": "same_process_encode_invocation",
  "interval_method": "bootstrap_percentile",
  "coverage_claim": "none"
}
```

The point estimate is the candidate group median divided by the reference
group median. The interval estimator is an unpaired ratio-of-medians, using
same-process encode invocation resampling and a percentile bootstrap interval.
This storage interval has no coverage claim.

This ordering adapts the endpoint-family principle in the FDA's
[Multiple Endpoints in Clinical Trials guidance](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/multiple-endpoints-clinical-trials):
one prespecified endpoint supports the primary conclusion, while secondary
endpoints extend interpretation. This repository does not treat benchmark
evidence as a clinical trial.

## Multiplicity contract

The confirmatory family contains every registered `(pair, candidate)`
comparison. The current registry has seven comparisons. A Bonferroni
allocation fixes family alpha at `0.05` and comparison alpha at `0.05 / 7`;
using the complete registry keeps single-pair runs and merged shards under the
same preregistered family.

Operations, transport size, p50, and p95 are descriptive secondary evidence
and do not support confirmatory conclusions. Pair verdicts are shown together,
so the primary family is simultaneous across pairs rather than pair-local.

`native_bytes` uses the `bootstrap_percentile` interval method over repeated
encoding invocations, as declared by `storage_estimand`.
Automatically created fixture runs record two observations per format and
standard runs record ten. A separate `prepare` workflow must pass
`--size-observations 2` or `10`; an existing equivalence run with fewer
observations is rejected before measurement.
Each temporary artifact is round-trip verified and removed after its byte
counts and digest are recorded. The canonical artifact is verified before the
comparison can run.

The resampling unit is `same_process_encode_invocation`: these observations are
not claimed to be independent fresh processes and generalize only to the
recorded dataset, settings, runtime, host, and filesystem policy. The
multiplicity record therefore declares
`status = "PREREGISTERED_NO_COVERAGE"` and `coverage_claim = "none"`:
Bonferroni is preregistered but does not validate bootstrap coverage. Coverage
simulation, fresh-process or block designs, BCa, studentization, and Monte
Carlo error remain tracked by
[issue #271](https://github.com/Anionix/data-format-lab/issues/271).
The repeated-observation framing follows NIST's
[Type A uncertainty guidance](https://physics.nist.gov/cuu/Uncertainty/typea.html);
this implementation does not claim validated coverage.

## Timing bootstrap contract

The standard timing configuration independently resamples ten fresh-process
summaries for each format 2,000 times. Fixture and explicitly configured runs
use their scheduled process count. Every emitted interval records the actual
observation counts, effective seed, alpha, replicate count, resampling unit,
RNG, and percentile-index rule. The lower order statistic is `floor(qB)` and
the upper is `ceil((1-q)B)-1`, using zero-based indexes and `q = alpha / 2`.

Independent resampling follows NIST's distinction between unpaired and paired
bootstrap groups. The percentile interval is first-order accurate; BCa,
studentization, coverage simulation, and Monte Carlo error remain tracked by
[issue #271](https://github.com/Anionix/data-format-lab/issues/271).
The implementation uses `Random.randrange`, whose stream is not guaranteed
across Python versions. Evidence therefore records the exact Python
implementation and version, and replay requires that pinned runtime. Python's
stronger cross-version guarantee applies only to the seeded `random()` stream.

- [NIST bootstrap reference](https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/bootplot.htm)
- [Python random reproducibility](https://docs.python.org/3/library/random.html#notes-on-reproducibility)

## Decision boundaries

The v1 practical-equivalence bounds are unchanged:

- native size: `0.98..1.02`
- transport size: `0.98..1.02` (secondary)
- p50: `0.95..1.05` (secondary)
- p95: `0.90..1.10` (secondary)

Intervals crossing the applicable bound are `INCONCLUSIVE`. Missing or failed
evidence remains `NOT_APPLICABLE`; neither state is rankable.
