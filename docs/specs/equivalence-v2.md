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

## Decision boundaries

The v1 practical-equivalence bounds are unchanged:

- native size: `0.98..1.02`
- transport size: `0.98..1.02` (secondary)
- p50: `0.95..1.05` (secondary)
- p95: `0.90..1.10` (secondary)

Intervals crossing the applicable bound are `INCONCLUSIVE`. Missing or failed
evidence remains `NOT_APPLICABLE`; neither state is rankable.
