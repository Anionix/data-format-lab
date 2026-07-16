# Format Selection Guide

This guide turns the v0.1.0 evidence into conditional choices. It does not
declare a universal winner: fair storage, native claims, and prompt tokens use
different inputs and success rules.

## Quick Decisions

| Workload | First choice | Evidence and caveat |
| --- | --- | --- |
| Typed analytics and interchange | Parquet default | All ranked fair formats passed the canonical gate. Parquet is the practical baseline for typed schemas, projection, predicate pushdown, and broad interoperability. |
| Static storage where bytes matter more than write time | Parquet zstd-19 | It was the smallest ranked fair artifact. Higher compression increases write cost, so it is better suited to archival or mostly-read data. |
| Large scans, filters, and random access | Vortex compact | The claims workload showed an advantage in the tested sorted, unsorted, and random-access stress cases. This is claim-specific evidence, not a general database ranking; validate the operations and ecosystem you need. |
| Full-text search | Lance | Lance is the tested option with a full-text index. Scalar and vector indexes were not evaluated. Keep base data, index, metadata, logical directory size, and transport size separate when budgeting storage. |
| LLM prompt payload | Compact TSV | It used the fewest measured tokens for the shared seven-field prompt contract. Include the taxonomy dictionary and schema, and use a self-describing representation when consumers cannot share that contract. |
| Human-readable structured exchange | Object JSONL | Field names travel with each record, making inspection and ad hoc tooling easier. It costs more bytes and tokens than array JSONL or Compact TSV. |
| Simple line-oriented interchange | CSV | It is widely supported and easy to inspect, but schema, NULL, quoting, and type rules must be supplied separately. It is not the typed storage baseline. |
| Measured device/tag time-range query | TsFile | The adapted synthetic workload used 100 devices with 10,000 points each and measured a 1,000-row time range. It was not a fair Stars comparison and had slower writes; other time-series access patterns were not evaluated. |

## Formats Without A Selection

Nimble and AnyBlox do not have a reproducible reader/writer path in the pinned
attempts. They remain research leads, not production recommendations. Their
exact commits, failures, and retry conditions are recorded in the
[negative-evidence records](../research/formats/).

FastLanes also has no general selection yet. Its corrected pipe-delimited
numeric case round-tripped, but partial-vector string cases failed, malformed
input terminated the process, and the pinned Python binding hit a reproducible
macOS build blocker. Keep it as experimental evidence until those retry
conditions are resolved.

DuckDB is a query engine and can be useful with several of these formats. It is
not a competing file-format row in this guide.

## Decision Rules

1. Start with the workload, not the format's headline claim.
2. Prefer Parquet when typed interchange, ecosystem breadth, and operational simplicity are the primary requirements.
3. Choose Lance or Vortex only when the index or scan behavior they provide is part of the actual workload and the deployment can accept their operational constraints.
4. Keep prompt representation separate from storage representation. Convert binary or indexed results to the same prompt payload before measuring tokens.
5. Reject any performance result whose canonical round trip, NULL behavior, values, or query result set does not match.
6. Treat `ADAPTED`, `PARTIAL`, and `UNAVAILABLE` as evidence qualifiers, not as hidden penalties in a composite score.

## Why There Is No Overall Score

Compression ratio, read latency, write latency, interoperability, prompt
tokens, and crash resistance have different units and different workloads. A
single weighted score would hide those boundaries and turn unavailable
evidence into an arbitrary number. The lab therefore publishes rankings only
inside a lane and gives a recommendation with a caveat for each workload.

## Traceability

- The measured values and platform separation are in the [v0.1.0 evidence summary](../reports/v0.1.0/README.md).
- The corrected questions, workload adaptations, and research decisions are in the [research log](research-log.md).
- The lifecycle and comparability contract is in [CONTEXT.md](../CONTEXT.md).
- FastLanes, Nimble, and AnyBlox failures are in the [negative-evidence records](../research/formats/).
