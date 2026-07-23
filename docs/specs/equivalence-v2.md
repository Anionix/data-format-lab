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

`native_bytes` currently has a deterministic exact observed-ratio interval.
The multiplicity record therefore declares
`status = "PREREGISTERED_NO_COVERAGE"` and `coverage_claim = "none"`:
Bonferroni is preregistered but does not create statistical coverage from one
encoding. Repeated-encoding size uncertainty remains tracked by
[issue #274](https://github.com/Anionix/data-format-lab/issues/274).

## Decision boundaries

The v1 practical-equivalence bounds are unchanged:

- native size: `0.98..1.02`
- transport size: `0.98..1.02` (secondary)
- p50: `0.95..1.05` (secondary)
- p95: `0.90..1.10` (secondary)

Intervals crossing the applicable bound are `INCONCLUSIVE`. Missing or failed
evidence remains `NOT_APPLICABLE`; neither state is rankable.
