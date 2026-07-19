# Strict Audit Registry

Audit date: `2026-07-19`
Audited commit: `52748f552bf2f5e7922725ea2e8f85bea291bce0`
Generated from [`audit.json`](audit.json). Do not edit this report directly.

## Summary

| Disposition | Count |
| --- | ---: |
| ISSUE | 85 |
| MONITOR | 36 |
| REGRESSION_GUARD | 53 |

## Correctness and canonicalization

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-001 | File/table/engine/codec/index taxonomy | 8 | REGRESSION_GUARD | - | Agent | Explicit glossary in `CONTEXT.md:9-22`; not fully enforced by separate adapter types. |
| DFL-AUDIT-002 | Fair/claims/prompt separation | 9 | REGRESSION_GUARD | - | Agent | Separate lanes and no cross-lane ranking in `CONTEXT.md:29-38`. |
| DFL-AUDIT-003 | Equivalence lane isolation | 8 | REGRESSION_GUARD | - | Agent | Pair-local registry and lane checks in `equivalence_compare.py:23-59`. |
| DFL-AUDIT-004 | Engine-container separation | 8 | REGRESSION_GUARD | - | Agent | SQLite/DuckDB are not file-format ranking rows. |
| DFL-AUDIT-005 | Robustness/performance separation | 9 | REGRESSION_GUARD | - | Agent | Robustness cannot change performance ranking. |
| DFL-AUDIT-006 | Comparability eligibility | 8 | REGRESSION_GUARD | - | Agent | Only `FULL_COMPARABLE` entries rank; aggregate publication sometimes omits this clearly. |
| DFL-AUDIT-007 | Fixture non-rankability | 9 | REGRESSION_GUARD | - | Agent | Fixture runs are explicitly marked non-rankable. |
| DFL-AUDIT-008 | Lifecycle model | 8 | REGRESSION_GUARD | - | Agent | Executable transitions are strong; global verification aggregation has a defect. |
| DFL-AUDIT-009 | Failure as publishable evidence | 9 | REGRESSION_GUARD | - | Agent | `FAILED`/`UNSUPPORTED` are retained and non-rankable. |
| DFL-AUDIT-010 | No universal winner | 9 | REGRESSION_GUARD | - | Agent | Consistent doctrine in context, ADR, report and selection guide. |
| DFL-AUDIT-011 | Manifest-driven Arrow schema | 7 | MONITOR | - | Agent | Exact schema exists, but only four Arrow types are supported. |
| DFL-AUDIT-012 | Primitive type breadth | 4 | ISSUE | P2 | Agent | Only string, float64, int64 and bool in `canonical.py:15-20`. |
| DFL-AUDIT-013 | Exact schema equality | 9 | REGRESSION_GUARD | - | Agent | `verify_table()` rejects schema mismatch. |
| DFL-AUDIT-014 | NULL rule enforcement | 7 | MONITOR | - | Agent | Nullable fields are checked; empty string is globally collapsed into NULL. |
| DFL-AUDIT-015 | Canonical hash determinism | 7 | MONITOR | - | Agent | Stable JSON/SHA-256 process; limited to Python/JSON semantics. |
| DFL-AUDIT-016 | Canonical hash genericity | 5 | ISSUE | P3 | Agent | Dataset-specific normalization for Stars fields remains in generic core. |
| DFL-AUDIT-017 | Row-order preservation | 3 | ISSUE | P1 | Agent | `canonical_hash()` sorts rows, so permutations can pass conformance. |
| DFL-AUDIT-018 | NaN/infinity handling | 4 | ISSUE | P2 | Agent | Standard JSON canonicality is not enforced; `allow_nan` remains default. |
| DFL-AUDIT-019 | Full round-trip gate | 9 | REGRESSION_GUARD | - | Agent | Schema, rows, hash and expected counts required before timing. |
| DFL-AUDIT-020 | Query count equality | 8 | REGRESSION_GUARD | - | Agent | Exact result counts are checked. |
| DFL-AUDIT-021 | Query content equality | 7 | MONITOR | - | Agent | Normalized result hashes exist, but ordering differences can be masked. |
| DFL-AUDIT-022 | HEAD operation semantics | 4 | ISSUE | P2 | Agent | Head is order-sensitive, while canonical result evidence is order-insensitive. |
| DFL-AUDIT-023 | Adapter verification consistency | 7 | MONITOR | - | Agent | Most adapters converge on `verify_table`; casting/read semantics vary. |
| DFL-AUDIT-024 | Corruption versus mismatch semantics | 7 | MONITOR | - | Agent | Robustness avoids falsely calling arbitrary mutation acceptance silent corruption. |
| DFL-AUDIT-102 | Global verification aggregation | 3 | ISSUE | P1 | Agent | All adapters may be FAILED/UNSUPPORTED while run becomes `ROUNDTRIP_VERIFIED`. |

## Measurement execution and isolation

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-025 | Monotonic timing clock | 8 | REGRESSION_GUARD | - | Agent | `perf_counter_ns` surrounds target invocation. |
| DFL-AUDIT-026 | Fresh process isolation | 8 | REGRESSION_GUARD | - | Agent | Each replicate is a subprocess. |
| DFL-AUDIT-027 | Repetition hierarchy | 8 | REGRESSION_GUARD | - | Agent | 10 processes, 5 warmups, 30 iterations; per-process summaries retained. |
| DFL-AUDIT-028 | Warmup rationale | 6 | MONITOR | - | Agent | Implemented but no stabilization diagnostic justifies five warmups. |
| DFL-AUDIT-029 | Fresh-open naming | 6 | MONITOR | - | Agent | Fresh artifact invocation, not end-to-end cold application startup. |
| DFL-AUDIT-030 | True cold-cache measurement | 3 | ISSUE | P2 | Agent | OS cache is not purged; correctly disclosed, but cold-read claims are unavailable. |
| DFL-AUDIT-031 | Job order randomization | 5 | ISSUE | P3 | Agent | One seeded job shuffle; replicate blocks are not interleaved. |
| DFL-AUDIT-032 | Temporal/thermal drift control | 4 | ISSUE | P2 | Agent | No paired blocks, CPU governor, temperature or power-state control. |
| DFL-AUDIT-033 | Serial default | 8 | REGRESSION_GUARD | - | Agent | Fair jobs default to serial execution. |
| DFL-AUDIT-034 | Parallel-run interference | 5 | ISSUE | P3 | Agent | Worker count is recorded, but contention is not removed or modeled. |
| DFL-AUDIT-035 | CPU affinity/resource isolation | 3 | ISSUE | P2 | Agent | No affinity, cgroup, quota or bandwidth controls. |
| DFL-AUDIT-036 | Write-time measurement | 3 | ISSUE | P2 | Agent | Artifact write is generally one preparation observation, not repeated inference. |
| DFL-AUDIT-038 | Pushdown comparability | 6 | MONITOR | - | Agent | Same logical result, but pushdown and Arrow conversion differ by reader. |
| DFL-AUDIT-040 | RSS measurement | 4 | ISSUE | P2 | Agent | Process-wide max RSS includes interpreter/source/expected tables; no baseline subtraction. |
| DFL-AUDIT-041 | Result validation outside timer | 8 | REGRESSION_GUARD | - | Agent | Validation does not contaminate measured invocation. |
| DFL-AUDIT-042 | Hardware separation | 9 | REGRESSION_GUARD | - | Agent | macOS ARM and Linux x86_64 are separate result sets. |
| DFL-AUDIT-127 | Machine-load capture | 4 | ISSUE | P2 | Agent | Governor, thermal state, filesystem and background load omitted. |

## Workload and reader causal validity

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-037 | Scan operation breadth | 4 | ISSUE | P2 | Agent | Read, projection, simple filter and head only. |
| DFL-AUDIT-039 | Reader/format causal separation | 5 | ISSUE | P3 | Agent | Measures format plus library plus reader implementation, not format alone. |
| DFL-AUDIT-064 | Row-group/page/chunk normalization | 4 | ISSUE | P2 | Agent | Key physical controls are not systematically fixed across formats. |
| DFL-AUDIT-171 | Parquet/ORC codec parity | 3 | ISSUE | P1 | Agent | The pair compares Parquet Zstd with ORC Zlib. It is useful as a configured-system comparison, not an isolated format-layout comparison. |
| DFL-AUDIT-172 | Parquet/ORC execution parity | 3 | ISSUE | P1 | Agent | Parquet uses column/filter pushdown while ORC reads the table and applies Arrow operations afterward; reader implementation and format effects are confounded. |
| DFL-AUDIT-174 | Claim-result value verification | 4 | ISSUE | P1 | Agent | Vortex stress and TsFile query comparisons primarily assert returned row counts, not value/schema hashes, so equal counts can conceal wrong records. |

## Statistical inference

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-043 | Estimand definition | 5 | ISSUE | P3 | Agent | Metrics exist, but target population and warm/fresh estimands are not formally stated. |
| DFL-AUDIT-044 | p50 calculation | 8 | REGRESSION_GUARD | - | Agent | Deterministic and tested. |
| DFL-AUDIT-045 | p95 calculation | 7 | MONITOR | - | Agent | Deterministic; only 30 within-process samples per process. |
| DFL-AUDIT-046 | IQR/min/max reporting | 7 | MONITOR | - | Agent | Useful descriptive spread is retained. |
| DFL-AUDIT-047 | Fair-lane uncertainty | 3 | ISSUE | P2 | Agent | Rankings use point summaries without confidence intervals/effect thresholds. |
| DFL-AUDIT-048 | Process as inferential unit | 7 | MONITOR | - | Agent | Process p50/p95 samples are retained, though headline warm tables pool iterations. |
| DFL-AUDIT-049 | Bootstrap implementation | 4 | ISSUE | P2 | Agent | Basic 2,000-sample percentile bootstrap over ten processes. |
| DFL-AUDIT-050 | Bootstrap validation | 3 | ISSUE | P2 | Agent | No coverage simulation, BCa, studentization or Monte Carlo error analysis. |
| DFL-AUDIT-051 | Paired inference | 4 | ISSUE | P2 | Agent | Independent resampling misses a possible temporal-block pairing design. |
| DFL-AUDIT-052 | Equivalence margin justification | 4 | ISSUE | P2 | Agent | +/-2/5/10% thresholds are explicit but not tied to user impact or noise. |
| DFL-AUDIT-053 | Size uncertainty | 2 | ISSUE | P1 | Agent | Storage uses degenerate exact intervals despite documented writer nondeterminism. |
| DFL-AUDIT-054 | Multiple-comparison control | 2 | ISSUE | P1 | Agent | No FWER/FDR/simultaneous intervals across metrics, operations and pairs. |
| DFL-AUDIT-055 | Primary endpoint declaration | 3 | ISSUE | P2 | Agent | No preregistered primary metric; any meaningful difference dominates pair verdict. |
| DFL-AUDIT-056 | Power/sample-size analysis | 2 | ISSUE | P2 | Agent | No power or precision analysis supports ten fresh processes. |
| DFL-AUDIT-057 | Sensitivity analysis | 3 | ISSUE | P2 | Agent | No log-ratio, alternative robust summary or margin sensitivity output. |
| DFL-AUDIT-058 | Two-run reproducibility | 5 | ISSUE | P3 | Agent | Claimed and summarized, but second-run raw evidence is not tracked for recalculation. |

## Format, tokenizer, and native coverage

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-059 | Native byte accounting | 8 | REGRESSION_GUARD | - | Agent | Exact artifact/logical bytes are separate from transport compression. |
| DFL-AUDIT-060 | External zstd accounting | 7 | MONITOR | - | Agent | Consistent level-3 transport size; compression/decompression time absent. |
| DFL-AUDIT-061 | Directory-format accounting | 8 | REGRESSION_GUARD | - | Agent | Deterministic recursive logical size and tar transport calculation. |
| DFL-AUDIT-062 | Lance data/index/metadata split | 9 | REGRESSION_GUARD | - | Agent | Strong component-level accounting in `formats/lance.py:43-52`. |
| DFL-AUDIT-063 | Writer settings provenance | 7 | MONITOR | - | Agent | Settings recorded; important physical defaults remain implicit. |
| DFL-AUDIT-065 | CSV/TSV comparison | 8 | REGRESSION_GUARD | - | Agent | Same typed source and workload; useful equivalence pair. |
| DFL-AUDIT-066 | Arrow IPC/Feather comparison | 8 | REGRESSION_GUARD | - | Agent | Correctly treated as related variants. |
| DFL-AUDIT-067 | Parquet/ORC comparison | 7 | MONITOR | - | Agent | Useful system comparison; defaults and reader behavior remain confounders. |
| DFL-AUDIT-068 | JSONL/Avro/MessagePack/CBOR | 7 | MONITOR | - | Agent | Good row-serialization breadth and round-trip gate. |
| DFL-AUDIT-069 | SQLite/DuckDB comparison | 7 | MONITOR | - | Agent | Correct lane, but engine/container/database design differences remain large. |
| DFL-AUDIT-070 | Prompt content equivalence | 8 | REGRESSION_GUARD | - | Agent | Shared projection; taxonomy and schema overhead included. |
| DFL-AUDIT-071 | Tokenizer accuracy | 8 | REGRESSION_GUARD | - | Agent | Exact `o200k_base` and `cl100k_base` counts, not estimates. |
| DFL-AUDIT-072 | Tokenizer/model breadth | 5 | ISSUE | P3 | Agent | Only two OpenAI encodings; no chat/tool framing or non-OpenAI tokenizer. |
| DFL-AUDIT-073 | Retrieval prompt comparison | 8 | REGRESSION_GUARD | - | Agent | Common Compact TSV output for 5/10/20 results. |
| DFL-AUDIT-074 | Lance FTS evidence | 6 | MONITOR | - | Agent | Index size and query metrics exist; substring truth is a limited relevance target. |
| DFL-AUDIT-075 | Vortex claim evidence | 6 | MONITOR | - | Agent | Claim-specific work exists; broader scan superiority is not established. |
| DFL-AUDIT-076 | TsFile evidence | 6 | MONITOR | - | Agent | Correctly `ADAPTED`; optional wheel still skipped in ordinary CI. |
| DFL-AUDIT-077 | FastLanes/Nimble/AnyBlox negative evidence | 8 | REGRESSION_GUARD | - | Agent | Failure conditions are retained without overclaiming upstream defects. |
| DFL-AUDIT-078 | Native fuzz depth | 5 | ISSUE | P3 | Agent | Pinned targets and artifacts are good; 900 seconds is validation-scale, not maturity evidence. |
| DFL-AUDIT-173 | Compact-TSV semantic legend cost | 3 | ISSUE | P1 | Agent | Taxonomy bytes are counted, but the abbreviated `m,r,l,s,k,t,d` header has no counted mapping to full semantic field names; object JSONL is self-describing and array JSONL counts its full schema. |

## Dataset provenance and licensing

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-079 | Dataset identity/hashes | 9 | REGRESSION_GUARD | - | Agent | Immutable IDs, source SHA and canonical hash are consistently recorded. |
| DFL-AUDIT-080 | Data Card quality | 5 | ISSUE | P3 | Agent | Stars is strong; five newer cards are brief source notes. |
| DFL-AUDIT-081 | Raw-source retention | 3 | ISSUE | P2 | Agent | Essential raw responses/pages/transformation provenance are missing for several datasets. |
| DFL-AUDIT-082 | Regeneration reproducibility | 4 | ISSUE | P2 | Agent | Frozen bytes reproduce; several derivations cannot be reconstructed from official source. |
| DFL-AUDIT-083 | Licensing precision | 5 | ISSUE | P3 | Agent | UCI/GeoNames are clear; NYC/OWID/Stars obligations remain qualified. |
| DFL-AUDIT-084 | Snapshot immutability | 8 | REGRESSION_GUARD | - | Agent | Release assets have compressed/decompressed hashes. |
| DFL-AUDIT-095 | NYC snapshot consistency | 2 | ISSUE | P1 | Agent | Mutable endpoint + offset pagination + no raw pages; manifest mentions keyset but code does not. |
| DFL-AUDIT-096 | GeoNames normalization fidelity | 5 | ISSUE | P3 | Agent | Strict field count; claimed sort is not visible in normalizer. |
| DFL-AUDIT-097 | Stars representativeness | 4 | ISSUE | P2 | Agent | Single Apple-heavy user sample with heuristic labels. |

## Dataset and workload external validity

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-085 | Domain diversity | 6 | MONITOR | - | Agent | Six domains and varied row counts improve on Stars alone. |
| DFL-AUDIT-086 | Workload-regime diversity | 3 | ISSUE | P2 | Agent | Five datasets repeat essentially the same five-operation template. |
| DFL-AUDIT-087 | Schema width | 2 | ISSUE | P2 | Agent | Maximum tested width is 13; rich sources are projected to 5-8 columns. |
| DFL-AUDIT-088 | Primitive type diversity | 4 | ISSUE | P2 | Agent | Four primitive types only. |
| DFL-AUDIT-089 | Temporal semantics | 3 | ISSUE | P2 | Agent | Dates are mostly strings; no real temporal range/partition workload. |
| DFL-AUDIT-090 | Nested/binary/decimal data | 1 | ISSUE | P2 | Agent | Absent. |
| DFL-AUDIT-091 | NULL semantics realism | 6 | MONITOR | - | Agent | Missing values are exercised, but empty string is not preserved distinctly. |
| DFL-AUDIT-092 | Cardinality/skew statistics | 3 | ISSUE | P2 | Agent | Distinct counts, entropy, quantiles and text-length distributions are not published. |
| DFL-AUDIT-093 | Predicate selectivity spread | 6 | MONITOR | - | Agent | Expected counts span broad to selective predicates. |
| DFL-AUDIT-094 | Predicate-selection methodology | 4 | ISSUE | P2 | Agent | Thresholds are not preregistered or justified. |
| DFL-AUDIT-098 | Six-dataset external validity | 3 | ISSUE | P2 | Agent | Supports conditional flat-table claims only, not general data-format claims. |

## API typing, testing, and maintainability

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-099 | Adapter API size | 7 | MONITOR | - | Agent | Small and comprehensible. |
| DFL-AUDIT-100 | Adapter API typing | 4 | ISSUE | P2 | Agent | Public boundaries rely heavily on nested `dict` and string keys. |
| DFL-AUDIT-101 | State-machine adjacency | 9 | REGRESSION_GUARD | - | Agent | Illegal transitions are explicitly rejected and tested. |
| DFL-AUDIT-103 | Error taxonomy | 6 | MONITOR | - | Agent | Robustness is rich; ordinary profiles collapse broad exceptions into strings. |
| DFL-AUDIT-114 | Test breadth | 8 | REGRESSION_GUARD | - | Agent | Broad unit/adversarial tests across lifecycle, adapters, crashes, paths and reports. |
| DFL-AUDIT-115 | Current test execution | 9 | REGRESSION_GUARD | - | Agent | Fresh Nix run passed; two expected TsFile optional tests skipped. |
| DFL-AUDIT-116 | Optional integration coverage | 6 | MONITOR | - | Agent | TsFile can remain skipped in ordinary CI. |
| DFL-AUDIT-117 | Pyright strict breadth | 4 | ISSUE | P2 | Agent | Strict checking covers only five production modules. |
| DFL-AUDIT-118 | Ruff gate | 7 | MONITOR | - | Agent | Blocking and fast, but deliberately narrow rule set. |
| DFL-AUDIT-119 | `ty` gate | 6 | MONITOR | - | Agent | Useful observation, non-blocking by design. |
| DFL-AUDIT-120 | CI correctness coverage | 8 | REGRESSION_GUARD | - | Agent | Nix, locks, lint, typing, tests, lane smoke and implementation audit. |
| DFL-AUDIT-121 | Coverage/mutation metrics | 4 | ISSUE | P2 | Agent | No coverage threshold or mutation-testing evidence. |
| DFL-AUDIT-122 | Duplication/schema-drift risk | 5 | ISSUE | P3 | Agent | Repeated path/JSON/untyped-dict logic raises change risk. |

## Robustness and sandboxing

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-104 | Crash classification | 8 | REGRESSION_GUARD | - | Agent | Signals and target outcomes are recorded. |
| DFL-AUDIT-105 | Timeout classification | 8 | REGRESSION_GUARD | - | Agent | Explicit timeout and cleanup-incomplete outcomes. |
| DFL-AUDIT-106 | Descendant cleanup | 7 | MONITOR | - | Agent | Strong in robustness; ordinary benchmark worker process groups are weaker. |
| DFL-AUDIT-107 | Filesystem isolation | 4 | ISSUE | P2 | Agent | Worker process can write broadly inside run directory. |
| DFL-AUDIT-108 | Memory/process/file limits | 3 | ISSUE | P2 | Agent | No RLIMIT/cgroup/sandbox resource caps. |
| DFL-AUDIT-109 | Output retention limits | 8 | REGRESSION_GUARD | - | Agent | Concurrent drain, bounded tails and hashes. |
| DFL-AUDIT-110 | Artifact-budget enforcement | 7 | MONITOR | - | Agent | Parent-managed evidence budget is good; arbitrary worker writes can bypass it. |
| DFL-AUDIT-111 | Path traversal protection | 8 | REGRESSION_GUARD | - | Agent | Absolute, traversal and outside-run paths rejected. |
| DFL-AUDIT-112 | Symlink safety | 8 | REGRESSION_GUARD | - | Agent | Release and evidence paths reject symlink escapes. |
| DFL-AUDIT-113 | Release archive safety | 9 | REGRESSION_GUARD | - | Agent | Deterministic streaming tar.zst with path checks. |
| DFL-AUDIT-167 | Robustness exception attribution | 3 | ISSUE | P1 | Agent | A broad target-side `Exception` becomes `REJECTED`; `MUST_REJECT` and `MUST_NOT_CRASH` can therefore pass on a lab `NameError`, `TypeError`, or other implementation defect. |
| DFL-AUDIT-168 | Robustness CI completeness | 3 | ISSUE | P1 | Agent | The gate fails only explicit CORE `FAIL`; an all-`INCOMPLETE` or all-`HARNESS_FAILED` CORE run can remain green, and the fixture omits most boundary families. |

## Release and public evidence

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-123 | Nix pinning | 9 | REGRESSION_GUARD | - | Agent | Python/native/Rust environment is locked for declared systems. |
| DFL-AUDIT-124 | `uv.lock` reproducibility | 9 | REGRESSION_GUARD | - | Agent | Exact Python dependencies and frozen sync. |
| DFL-AUDIT-125 | Environment capture | 8 | REGRESSION_GUARD | - | Agent | Commit, flake hash, platform, hardware, Python and package versions. |
| DFL-AUDIT-126 | Host-result separation | 9 | REGRESSION_GUARD | - | Agent | No machine-spanning ranking. |
| DFL-AUDIT-128 | Machine-readable public evidence | 5 | ISSUE | P3 | Agent | Raw JSON is in release archives, not directly reviewable in repository. |
| DFL-AUDIT-129 | Current tracked report | 4 | ISSUE | P2 | Agent | No tracked v0.2 aggregate/six-dataset report; README points to v0.1. |
| DFL-AUDIT-130 | Release asset checksums | 8 | REGRESSION_GUARD | - | Agent | Assets and SHA-256 sidecars exist and are manifest-linked. |
| DFL-AUDIT-131 | Release tag/code identity | 5 | ISSUE | P3 | Agent | Evidence includes commits after the RC tag target; per-shard provenance mitigates but does not cure discovery. |
| DFL-AUDIT-132 | Package/release version identity | 4 | ISSUE | P2 | Agent | `pyproject.toml` remains `0.1.0` at `v0.2.0-rc1`. |
| DFL-AUDIT-133 | Release body accuracy | 4 | ISSUE | P2 | Agent | Says benchmark assets will be appended after they already exist. |
| DFL-AUDIT-163 | Public aggregate-generator reproducibility | 1 | ISSUE | P1 | Agent | `work/build_revalidation_aggregate.py` and `work/finalize_revalidation.sh` generated the v0.2 aggregate but are ignored by the tracked `work/` rule. The public repository cannot regenerate the published aggregate. |
| DFL-AUDIT-164 | Archive-internal reference closure | 2 | ISSUE | P1 | Agent | Aggregate evidence points to `.data/revalidation-20260719/...`; the archive stores the same files under `revalidation-20260719/claims/...`, so the recorded paths do not resolve after extraction. |
| DFL-AUDIT-165 | Archived artifact completeness | 2 | ISSUE | P1 | Agent | Nested pair manifests reference `artifacts/*.parquet`, `*.orc`, databases, and other encoded outputs, but the aggregate archive carries only nested manifest/results/report files. |
| DFL-AUDIT-166 | Package validation depth | 3 | ISSUE | P1 | Agent | The packager validates top-level result references, but aggregate evidence lives under `datasets[].evidence[]`; therefore broken nested paths and missing nested artifacts pass packaging. |

## Security and repository governance

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-169 | Runtime dependency security | 2 | ISSUE | P1 | Agent | Live Dependabot reports two High alerts and one Medium alert for pinned `cbor2`/`msgpack`; green PR #223 exists but is unmerged. |
| DFL-AUDIT-170 | Protected-main governance | 3 | ISSUE | P2 | Agent | GitHub reports `main` as unprotected, so required CI/review and force-push prevention are policy rather than enforced repository state. |

## Documentation, localization, and installation

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-134 | English README | 8 | REGRESSION_GUARD | - | Agent | Strong methodology and quick-start documentation. |
| DFL-AUDIT-135 | Japanese README parity | 4 | ISSUE | P2 | Agent | Still presents three lanes and omits current equivalence model. |
| DFL-AUDIT-136 | Research log candor | 8 | REGRESSION_GUARD | - | Agent | Corrections, failures and unsupported paths are documented. |
| DFL-AUDIT-137 | Data notice/ethics | 8 | REGRESSION_GUARD | - | Agent | Third-party rights and prohibited inference are acknowledged. |
| DFL-AUDIT-138 | Issue/review hygiene | 6 | MONITOR | - | Agent | Policies exist and one open bug is visible; full review-thread closure not re-audited. |
| DFL-AUDIT-140 | Supported-platform clarity | 6 | MONITOR | - | Agent | Nix systems imply support; no explicit supported/unsupported platform table. |
| DFL-AUDIT-150 | Installation friction | 5 | ISSUE | P3 | Mixed | Nix + uv is reproducible but heavy for a judge. |

## Product, UX, and impact

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-139 | GitHub Pages/no-build path | 1 | ISSUE | P0 | Mixed | Pages endpoint returns 404; no hosted current-result explorer. |
| DFL-AUDIT-141 | Problem framing | 8 | REGRESSION_GUARD | - | Agent | “Do not compare incomparable formats” is strong and memorable. |
| DFL-AUDIT-142 | Idea quality | 8 | REGRESSION_GUARD | - | Agent | Evidence-first, lane-local, negative-result lab is distinctive. |
| DFL-AUDIT-143 | Novelty evidence | 6 | MONITOR | - | Agent | Distinct combination; no comparison against existing benchmark products. |
| DFL-AUDIT-144 | Target-user clarity | 5 | ISSUE | P3 | Mixed | Data engineers/researchers are inferable, not directly framed. |
| DFL-AUDIT-145 | User-pain evidence | 4 | ISSUE | P2 | Human | No interviews, incidents, adoption or quantified decision cost. |
| DFL-AUDIT-146 | Decision usefulness | 7 | MONITOR | - | Agent | Selection guide is useful to informed engineers. |
| DFL-AUDIT-147 | Product coherence | 6 | MONITOR | - | Agent | Coherent research toolkit, but framework/report/guide identity competes. |
| DFL-AUDIT-148 | Three-minute demoability | 2 | ISSUE | P0 | Mixed | No single demo command, hosted explorer or visual result path. |
| DFL-AUDIT-149 | Visual communication | 1 | ISSUE | P2 | Mixed | No dashboard, chart, screenshot or tracked visual asset. |
| DFL-AUDIT-151 | Judge no-build test path | 3 | ISSUE | P0 | Mixed | Old Markdown is readable; latest results require release archive inspection. |
| DFL-AUDIT-156 | Category fit | 6 | MONITOR | - | Agent | Strong Developer Tools fit; weak model-centric fit without usage proof. |
| DFL-AUDIT-157 | Potential impact argument | 5 | ISSUE | P3 | Mixed | Credible need, no traction or measurable outcome. |
| DFL-AUDIT-158 | Technological Implementation | 8 | REGRESSION_GUARD | - | Agent | Non-trivial code, contracts, tests and evidence machinery. |
| DFL-AUDIT-159 | Design | 3 | ISSUE | P2 | Mixed | Runnable CLI, not a complete judge-facing product experience. |
| DFL-AUDIT-160 | Quality of Idea | 8 | REGRESSION_GUARD | - | Agent | Strongest official criterion after implementation. |

## Codex and GPT-5.6 narrative

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-152 | Codex usage evidence | 3 | ISSUE | P2 | Human | Commit/branch hints exist; README does not explain concrete Codex contributions. |
| DFL-AUDIT-153 | GPT-5.6 usage evidence | 1 | ISSUE | P2 | Human | No repository proof; tokenizer use is not GPT-5.6 use. |
| DFL-AUDIT-154 | Devpost factual accuracy | 2 | ISSUE | P0 | Human | Current text overstates Lance meaning search, “bug rate,” and Rust non-use. |
| DFL-AUDIT-155 | Devpost prose quality | 2 | ISSUE | P0 | Human | Candid but meandering and self-undermining for judges. |

## Human submission actions

| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| DFL-AUDIT-161 | Video readiness | 1 | ISSUE | P0 | Human | Live Devpost project has an empty video URL. |
| DFL-AUDIT-162 | Submission readiness | 1 | ISSUE | P0 | Human | Live state is `submission_draft`, `submitted_at` is null. |
