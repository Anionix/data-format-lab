# Equivalence Lane v1

## Contract

`format-bench run --profile equivalence --dataset <id>` runs all registered pairs. Repeatable `--pair` selects a subset. The input must already have passed the canonical round-trip gate.

The lifecycle remains:

```text
DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED
```

The runner writes `equivalence.contract_version = "1"` and keeps the common manifest/result envelope at schema version `1`.

## Pair registry

| Pair | Reference | Candidate(s) | Lane |
| --- | --- | --- | --- |
| `csv-tsv` | CSV | TSV | equivalence |
| `arrow-feather` | Arrow IPC | Feather v2 | equivalence |
| `parquet-orc` | Parquet | ORC | equivalence |
| `jsonl-avro` | object JSONL | Avro OCF | equivalence |
| `jsonl-msgpack-cbor` | object JSONL | MessagePack, CBOR | equivalence |
| `sqlite-duckdb` | SQLite | DuckDB | engine_container |

## Decision boundaries

The runner stores the point ratio and an independent 95% bootstrap interval for every operation. Practical equivalence requires the entire interval to remain inside:

- size: `0.98..1.02`
- p50: `0.95..1.05`
- p95: `0.90..1.10`

Intervals crossing a boundary are `INCONCLUSIVE`; they are not silently treated as no difference. A candidate can have different verdicts for different operations.

Binary formats do not receive a direct corpus token count. Prompt-token measurements remain in the separate `prompt` lane.
