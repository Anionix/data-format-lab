# Robustness Evidence v1

## Problem Statement

Data Format Lab verifies canonical round trips before benchmarking, but it cannot yet publish consistent evidence about boundary values, malformed input, corrupt artifacts, process crashes, or official native fuzzers. Earlier FastLanes evidence also combined a lab delimiter defect with a separate partial-vector string failure. Readers need a reproducible contract that reports what happened without turning unlike tests into a maturity ranking.

## Solution

Formalize the existing canonical verification as the conformance gate and add a fourth, non-ranking robustness lane. Run deterministic valid and mutated cases in isolated processes, retain the complete evidence within a fixed budget, and supplement the common harness with official project-native targets where they exist.

## User Stories

1. As a benchmark reader, I want performance results to require a canonical round trip, so that fast but incorrect readers cannot rank.
2. As a format maintainer, I want observed outcomes separated from verdicts, so that the report does not overstate a finding.
3. As a researcher, I want vector-boundary cases, so that fixed-width implementation errors are reproducible.
4. As a researcher, I want string-cardinality and NULL cases, so that dictionary and validity behavior is exercised.
5. As a parser maintainer, I want malformed and truncated inputs, so that rejection and process crashes are distinguishable.
6. As a report reader, I want accepted mutations described without a silent-corruption label, so that valid alternate data is not misclassified.
7. As a CI maintainer, I want core targets to gate while optional targets only record evidence, so that unavailable research dependencies do not block routine changes.
8. As a failure investigator, I want stdout, stderr, signals, hashes, and artifacts, so that a result can be reproduced outside the runner.
9. As a release consumer, I want only relative safe paths, so that evidence archives are portable and do not escape their run directory.
10. As a repository maintainer, I want a hard artifact budget, so that fuzz evidence cannot exhaust a runner disk.
11. As an upstream maintainer, I want official native targets pinned to commits, so that reports identify the exact code tested.
12. As a project reader, I want unsupported native targets reported explicitly, so that absence is not mistaken for a passing fuzz run.
13. As a FastLanes maintainer, I want the delimiter harness defect corrected separately from the string-tail reproducer, so that the upstream claim is precise.
14. As a cross-platform reader, I want macOS ARM and Linux x86_64 runs separated, so that hardware differences do not become rankings.

## Implementation Decisions

- Add `robustness` beside the existing three lanes without changing the lifecycle state machine.
- Keep the common JSON envelope at schema version 1 and version the nested robustness contract independently as version 1.
- Model expectations as `MUST_ROUNDTRIP`, `MUST_REJECT`, or `MUST_NOT_CRASH`.
- Model observed outcomes as round-trip equality, acceptance, rejection, value mismatch, crash, timeout, unsupported, budget exhaustion, or harness failure.
- Model verdicts as pass, fail, not applicable, or incomplete.
- Run every bounded case through a fresh Python module subprocess with no shell interpolation.
- Treat CSV, object JSONL, both Parquet settings, Lance base, and both Vortex settings as core targets.
- Treat TsFile and the pinned FastLanes experiment as evidence-only targets.
- Cover row counts 0, 1, 1023, 1024, 1025, 2048, and 2049; dictionary cardinalities 1, 2, 255, and 256; NULL positions; UTF-8 and parser-sensitive strings; numeric boundaries; column-count errors; and truncation.
- Add deterministic Arrow-table generation and empty, truncate, bit-flip, zero-range, append, and region mutation recipes.
- Default full bounded runs to seed 20260703, 32 generated cases, 64 mutations per target, 30 seconds per case, and a 1 GiB artifact budget.
- Preserve all input, output, recipe, process, digest, and case-result artifacts until the budget is exhausted.
- Record `cleanup_incomplete` when a detached descendant outlives the process-group drain grace; classify that case as `TIMED_OUT` rather than silently claiming cleanup success.
- Stream deterministic release archives rather than buffering an entire tar file in memory.
- Pin native sources to Apache Arrow `7932e197eaa00577ff3e83ddf956022df3ef174c`, Vortex `5abaf9823dee973dde7295a6a36234935f08d060`, and FastLanes `f0edc1020a538f1f8098640fce8347c9ac247a0d`.
- Run official Arrow CSV and Parquet fuzz executables, Vortex `file_io` and `compress_roundtrip`, and FastLanes `quick_fuzz_test`. Record the FastLanes target as project-seeded rather than coverage-guided.
- Record Lance, object JSONL, and TsFile native targets as unavailable unless an official target is published.

## Testing Decisions

- Test behavior through the CLI, result JSON, report, and release archive seams.
- Preserve the existing dataset row, type, NULL, value, canonical-hash, and query-count assertions as the conformance gate.
- Use fixture child programs to prove exception, signal, timeout, partial-output, and budget classifications.
- Require stable case identifiers, input canonical hashes, and mutation recipes for the same seed; do not require byte-identical output from nondeterministic writers.
- Reject absolute paths, parent traversal, symlinks, and missing referenced artifacts.
- Require report regeneration and release packaging to be idempotent.
- Gate pull requests only on core-target failures. Publish optional-target failure and unsupported evidence without failing CI.

## Out Of Scope

- A universal maturity score or ranking across robustness and performance lanes.
- Comparing coverage numbers across unlike native fuzz harnesses.
- Windows, cloud object storage, or true cold-cache testing.
- Nimble and AnyBlox execution until reproducible readers and writers are available.
- Extracting the framework before a second repository consumes it.

## Further Notes

The native suite is manual, Linux-based, and defaults to 900 seconds per target. Workflow artifacts retain all generated evidence up to 1 GiB for 14 days. Public macOS and Linux observations remain separate runs.
