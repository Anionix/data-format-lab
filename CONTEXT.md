# Data Format Lab Context

## Purpose

Data Format Lab tests storage and database claims against explicit contracts. It publishes evidence, including failed or unsupported experiments, without declaring one universal winner.

## Glossary

- **Dataset**: Immutable input plus schema, hashes, provenance, and expected query counts.
- **File format**: Byte-level representation such as Parquet or Vortex.
- **Table format**: Dataset-level metadata, versioning, and transaction conventions such as Lance datasets.
- **Query engine**: Software that executes queries, such as DuckDB. An engine is not ranked as a file format.
- **Codec**: Compression or encoding used inside or around a format.
- **Index**: Additional data that accelerates access and must be measured separately.
- **Adapter**: The small boundary that encodes, reads, and verifies one format variant.
- **Lane**: A comparison whose inputs and success rules are internally consistent.
- **Fair lane**: Equal Arrow table, schema, query results, and measurement protocol.
- **Claims lane**: A format-native workload derived from a primary-source claim.
- **Prompt lane**: Equal projected content measured as model tokens.
- **Equivalence lane**: Pairwise comparison of formats with the same logical table and workload; it never creates a global ranking.
- **Estimand**: Preregistered target population, condition, variable, population summary, and failure strategy for a reported measurement.
- **Engine-container lane**: SQL engine and database-file evidence, kept separate from file-format comparisons.
- **Robustness lane**: Boundary, malformed-input, and crash-resistance evidence with no performance ranking.
- **Conformance gate**: Canonical round-trip verification required before performance evidence is eligible.
- **Expectation**: The behavior a robustness case requires: round-trip, rejection, or no process crash.
- **Observed outcome**: What the isolated target process actually did, kept separate from the verdict.
- **Comparability**: Whether an observation can enter its lane's ranking.
- **Lifecycle**: Evidence state from discovery through publication.

## Invariants

1. Only `FULL_COMPARABLE` observations rank within one lane.
2. Round-trip verification precedes performance measurement.
3. Index bytes never disappear into base data size.
4. Binary files have no direct LLM token count.
5. Different hardware produces different result sets.
6. Unsupported and failed results remain publishable evidence.
7. Robustness evidence never changes rankings in the other lanes.
8. Equivalence verdicts are pair-local: `PRACTICALLY_EQUIVALENT`, `MEANINGFUL_DIFFERENCE`, `INCONCLUSIVE`, or `NOT_APPLICABLE`.
