# ADR 0002: Separate Conformance And Robustness

## Status

Accepted

## Context

The fair, claims, and prompt lanes answer performance and representation questions only after a format reproduces the canonical table. They do not describe behavior at vector-size boundaries, on malformed input, or when a native reader terminates its process.

An early FastLanes experiment mixed two findings. The lab passed comma-separated input to a reader configured for a pipe delimiter, so the reported numeric crash was a harness defect. With the documented delimiter, one million rows by eight numeric columns round-trip. Separate string tests still fail at partial 1,024-row vectors, and malformed delimiter input can terminate the process.

Combining those observations into one maturity score would hide both the corrected lab defect and the remaining reproducible behavior.

## Decision

Keep canonical round-trip verification as the conformance gate for performance lanes. Add an independent `robustness` lane for named boundary cases, deterministic mutations, and official native fuzz targets.

Each case records its expectation, observed outcome, and verdict separately. Arbitrary mutated bytes that parse as different valid data are not called silent corruption. A value mismatch is reported only when an unmodified valid artifact fails to reproduce its source table.

Every case runs in a fresh child process. Process signals and timeouts become evidence instead of terminating the parent run. Core installed targets gate CI; optional and research targets publish evidence without gating.

Robustness results do not rank formats and do not alter fair, claims, or prompt rankings.

## Consequences

- The existing evidence lifecycle remains the single publication lifecycle.
- All registered adapters can share one bounded harness without expanding their public interface.
- Official native fuzzers remain supplemental because their harnesses and coverage are not comparable.
- Complete case artifacts are retained under a bounded storage budget.
- A future extraction into another package requires a second independent consumer.
