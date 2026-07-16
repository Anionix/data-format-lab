# Research Log

This is a reconstruction of the questions, experiments, corrections, and decisions that led to Data Format Lab. It is not a transcript. Early numbers were exploratory and are intentionally not promoted as current benchmark results.

## 2026-07-03: from classification to representation

The work began by classifying 2,331 repositories starred by one public GitHub account. Repeated requests for finer categories produced a useful research dataset, but also exposed two limits: the sample is strongly influenced by Apple-oriented interests, and generated categories are not ground-truth labels.

The next question was how to store and search the classified rows. Compact TSV and JSONL were compared for human inspection, machine parsing, search, compression, and estimated LLM token cost. Parquet was then added as a typed columnar baseline.

Correction: the first table was not fair. Compact TSV projected 7 fields, TsFile used 10, FastLanes covered one numeric column, while other formats held 13. Those capacity values answered different questions.

## Emerging formats and engines

[Lance](https://github.com/lance-format/lance) was tested because its table format and indexes target search-oriented AI data. This led to a distinction between base data, FTS index bytes, metadata, logical directory bytes, and external compressed transport size.

DuckDB prompted a terminology correction: it is a query engine, while Parquet and Vortex are file formats and Lance also provides dataset-level behavior. An engine may read a format, but it should not occupy the same ranking row as that format.

[Vortex](https://github.com/vortex-data/vortex) shifted the question from small-file size to scan behavior. A first small Stars run did not exercise its advertised strengths. The revised claim workload expands the table to 466,200 rows, tests sorted and unsorted layouts, and compares projection, many matches, zero matches, and 1,000 random rows with Parquet. Parquet random access reads only relevant row groups.

[Apache TsFile](https://github.com/apache/tsfile) was initially very slow and large on Stars data. That was evidence of a workload mismatch, not a universal failure. It remains `ADAPTED` for Stars and receives a separate one-million-row time-series query against Parquet.

## Claims under scrutiny

The investigation then asked whether vendor and project claims were plausible, and whether Parquet's advantages had been represented fairly. Parquet became the exchange and analytical baseline because it is mature, widely readable, typed, and supports projection and predicate pushdown. A claim-specific winner does not displace that operational value.

[FastLanes](https://github.com/cwida/FastLanes), [Nimble](https://github.com/facebookincubator/nimble), and [AnyBlox](https://github.com/AnyBlox/vldb-2025) were attempted from pinned source commits. Mixed-column conversion, official build, or toolchain reproduction did not complete. Their failures are versioned evidence with retry conditions, not blank table cells.

Correction: the FastLanes numeric failure was caused by the lab writing comma-separated input to a reader configured for a pipe delimiter. With `|`, one million rows by eight numeric columns round-trip. Separate string tests still show a partial-vector boundary: 1,024 and 2,048 rows succeed while 1,023, 1,025, and 2,049 fail dictionary lookup. Invalid comma input can also terminate the process. The robustness lane records these as distinct harness, conformance, and crash-resistance observations rather than one format verdict.

Follow-up on 2026-07-17: the pinned FastLanes Python binding was rebuilt from the official source before attempting the mixed 13-column table. On macOS ARM64 with the lab's Python 3.12 and Clang 21 environment, compilation stopped at `TypedStats<std::string>` with `-Werror,-Wnonnull`. This is a reproducible build blocker, not evidence that the mixed-schema writer itself failed; the machine-readable attempt and exact pinned commit remain in `research/formats/fastlanes.json`.

The claims runner keeps the corrected TsFile time-series workload as `ADAPTED` and marks both TsFile and the pinned FastLanes execution as `EXPERIMENTAL`. FastLanes cases run in fresh child processes, retain per-case artifacts, and do not gate Core CI when the optional reader is unavailable or terminates.

The 2026-07-17 retry added the exact 13-column mixed-schema case and corrected fatal classification for worker failures and crashes. The lock-pinned Python package could not build under macOS arm64 Clang 21 because `src/table/stats.cpp` promotes a `std::string` null-argument warning to an error. The official C++ `quick_fuzz_test` built after downgrading the two observed warning classes, but all ten pinned cases exited `SIGTRAP`; this is experimental evidence, not an upstream bug claim.

The Linux x86_64 retry on [workflow run 29520329351](https://github.com/Anionix/data-format-lab/actions/runs/29520329351) built the pinned Python extension successfully with Python 3.12.13, Clang 21.1.8, CMake 4.1.2, and Ninja 1.13.2. The 1,000,000-row numeric control and all five string-boundary cases exited `SIGSEGV`; the 13-column mixed case raised `UNREACHABLE` at `src/wizard/wizard.cpp:1252`. Malformed comma input raised a typed-cast error in this Linux run. The result is `FAILED` and remains outside every ranking; it is distinct from the earlier macOS build blocker and from the lab's historical comma-delimiter mistake.

The 2026-07-17 Nimble retry pinned core `9da673...`, Velox `e06dd...`, and OpenZL `6b48...`. The dependency provenance was not fully lock-pure: protobuf library `35.1` came from Nix, `protoc 33.4` and fmt `12.1.0` came from Homebrew, and CMake reported the compiler/library mismatch. A dependency-resolving CMake path reached the bundled xsimd project but stopped at its pre-3.5 minimum-version declaration under CMake 4.1.2. The earlier protobuf/fmt target failure and this newer configure failure are both `UNSUPPORTED` build evidence; the 1,024-column projection comparison was not run.

The 2026-07-17 AnyBlox retry found official bundler and `anyblox2csv` targets at the pinned commits, but the artifact still required an undated nightly Rust toolchain. This host had Homebrew Rust 1.93.1 and no `rustup`; stable compilation failed with `E0554/E0599`. The input bundle and compiler were not checksum-complete, so no round trip or performance result was promoted.

The format survey was inspired in part by [this Japanese overview](https://zenn.dev/mrasu/articles/47dfb30436ebf3), but implementation claims are checked against each project's primary repository or documentation.

## Token questions

Estimated token counts were replaced with exact `o200k_base` and `cl100k_base` measurements. The prompt contract fixes seven semantic fields. Compact TSV includes its taxonomy dictionary in both byte and token totals. Object and array JSONL encode the same records.

Binary files do not receive a direct corpus token count: raw binary is not the prompt representation. When search results are passed to an LLM, every backend is converted to the same Compact TSV payload, measured at 5, 10, and 20 rows.

## Revalidation contract

The corrected design separated three lanes: equal-data storage (`fair`), format-native claim verification (`claims`), and LLM representation (`prompt`). Four comparability states prevent adapted or partial evidence from entering a main ordering.

The evidence lifecycle requires encode, round-trip verification, benchmark, and report phases. Every public run records dataset identity, code and environment identity, writer settings, deterministic seed, result counts, failure reasons, and relative paths. Fresh-process and warm measurements are distinct; OS caches are not forcibly purged.

## Public lab decision

The final question was how to preserve the reasoning without publishing a private chat transcript. The answer is this public, Apache-2.0 research repository: immutable data contracts and small fixtures in Git, large data and raw results in Releases, generated Markdown for readers, JSON evidence for machines, and explicit follow-up issues for unfinished work.

Current conclusions are intentionally conditional:

- Compact TSV is an LLM representation, not a replacement for typed storage.
- Parquet is the stable analytical and interchange baseline.
- Lance deserves separate evaluation when indexes and search are part of the workload.
- Vortex should be judged on scan and random-access claims at meaningful scale.
- TsFile should be judged on time-series workloads, not forced into a Stars ranking.
- Unsupported formats remain research leads until a reproducible round trip exists.

Published measurements are generated only from a public repository commit. Earlier exploratory figures remain historical context and must not be copied into the current result tables.
