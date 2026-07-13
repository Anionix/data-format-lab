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
- **Comparability**: Whether an observation can enter its lane's ranking.
- **Lifecycle**: Evidence state from discovery through publication.

## Invariants

1. Only `FULL_COMPARABLE` observations rank within one lane.
2. Round-trip verification precedes performance measurement.
3. Index bytes never disappear into base data size.
4. Binary files have no direct LLM token count.
5. Different hardware produces different result sets.
6. Unsupported and failed results remain publishable evidence.
