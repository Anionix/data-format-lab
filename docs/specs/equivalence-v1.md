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

## Parquet/ORC accepted risk

With pinned PyArrow 23.0.1, both adapters project columns at the reader
boundary. Parquet also passes predicates to `pyarrow.parquet.read_table`;
`pyarrow.orc.read_table` has a `columns` argument but no equivalent `filters`
argument. ORC predicates therefore remain post-read Arrow operations.

The `parquet-orc` result records this execution plan, uses
`comparison_scope = "configured_system"`, and carries the accepted-risk text
into the report. Its timings compare the pinned reader implementations and
settings; they do not isolate file-layout effects.

The writer plan is also asymmetric. `parquet_default` uses Zstd with
dictionary encoding and a library-default compression level; `orc_zlib` uses
Zlib with the ORC defaults of the speed strategy and a zero dictionary-key
threshold. The result envelope records both plans. Storage and timing ratios
therefore remain configured-system evidence rather than codec-controlled
format evidence.

Primary APIs:
[Parquet `read_table`](https://arrow.apache.org/docs/23.0/python/generated/pyarrow.parquet.read_table.html) and
[ORC `read_table`](https://arrow.apache.org/docs/23.0/python/generated/pyarrow.orc.read_table.html);
[Parquet writer settings](https://arrow.apache.org/docs/23.0/python/parquet.html#compression-encoding-and-file-compatibility) and
[ORC writer arguments](https://arrow.apache.org/docs/23.0/_modules/pyarrow/orc.html).
