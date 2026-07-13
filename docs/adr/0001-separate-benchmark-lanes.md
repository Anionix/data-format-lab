# ADR 0001: Separate Benchmark Lanes

## Status

Accepted

## Context

The initial Stars experiments compared useful outputs that did not always contain the same columns. Format-native indexes and prompt projections also answer different questions from equal-schema storage.

## Decision

Use three independent lanes: `fair`, `claims`, and `prompt`. Store lane and comparability as separate fields. Rank only `FULL_COMPARABLE` observations within a lane.

DuckDB is modelled as a query engine. Lance base storage and Lance FTS are separate observations because the index changes both capability and size.

## Consequences

- Results cannot imply a universal winner.
- New adapters must declare their lane and comparability.
- Reports can preserve partial and negative evidence without polluting rankings.
