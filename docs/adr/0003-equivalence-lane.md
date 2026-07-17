# ADR 0003: Pairwise Equivalence Lane

## Status

Accepted

## Context

CSV and TSV, Arrow IPC and Feather, or Parquet and ORC may be described as equivalent at a high level. That expectation can hide differences in delimiter handling, schema metadata, SQL execution, compression, or a particular workload. A global score would turn those different observations into a misleading conclusion.

## Decision

Add an `equivalence` lane with a registry of explicit pairs. Every candidate must pass the canonical round-trip and declared query-result contract before timing. Storage bytes are compared separately from operation timings. The runner uses independent bootstrap intervals because fresh processes for two formats are not matched trials.

SQLite and DuckDB use the separate `engine_container` lane. They are database containers and SQL engines, not file-format entries.

## Consequences

- Pair verdicts are `PRACTICALLY_EQUIVALENT`, `MEANINGFUL_DIFFERENCE`, `INCONCLUSIVE`, or `NOT_APPLICABLE`.
- A pair can be practically equivalent for size and materially different for one operation.
- Missing or failed adapters remain evidence and do not abort unrelated pairs.
- No result is a universal format ranking.
