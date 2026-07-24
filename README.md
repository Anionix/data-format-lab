# Data Format Lab

Reproducible, evidence-first tests for data formats, database claims, and LLM-facing representations.

[日本語](README.ja.md) | [Format selection guide](docs/format-selection.md) | [Research log](docs/research-log.md) | [Data notice](DATA_NOTICE.md)

Data Format Lab asks narrower questions than "which format is best?" It verifies equal-data storage behavior, format-native performance claims, and prompt token cost under separate contracts. Failed builds and unsupported formats remain part of the public record.

The first case study is a frozen, 2,331-row snapshot of public GitHub Stars metadata. The lab is designed for additional datasets and workloads; it is not a Stars-specific converter.

The equivalence expansion also carries small, non-rankable contract fixtures for UCI Online Retail II, UCI Bank Marketing, NYC 311, OWID Energy, and GeoNames cities500. Their manifests record official acquisition URLs, observed source hashes, schema/null rules, and normalization decisions; mutable full snapshots remain Release assets rather than Git files.

## Benchmark lanes

| Lane | Question | Current examples |
| --- | --- | --- |
| `fair` | What happens when every format stores the same typed Arrow table and returns the same rows? | CSV, object JSONL, Arrow IPC, Parquet, Lance, Vortex, adapted TsFile |
| `claims` | Does a format's stated strength appear under a workload suited to that claim? | Lance FTS, Vortex scans, adapted TsFile time ranges, experimental FastLanes evidence |
| `prompt` | How many exact model tokens represent the same seven projected fields? | Compact TSV, object JSONL, array JSONL |
| `equivalence` | Do formats that look equivalent in general remain equivalent for this data and workload? | CSV vs TSV, Arrow IPC vs Feather, Parquet vs ORC, JSONL vs row serializers |
| `engine_container` | How do SQL engines compare while operating on their own database files? | SQLite, DuckDB |

Results never rank across lanes or hardware runs. Only `FULL_COMPARABLE` evidence can enter an ordering inside its own lane. DuckDB is treated as a query engine, not as a file format.

The equivalence lane compares only named pairs. Its preregistered primary endpoint is `storage/native_bytes`: an interval inside ±2% is `PRACTICALLY_EQUIVALENT`, an interval wholly outside that boundary is `MEANINGFUL_DIFFERENCE`, and an interval crossing it is `INCONCLUSIVE`. p50 and p95 ratio intervals use ±5% and ±10% as descriptive secondary evidence and cannot change the primary verdict. Missing or failed primary evidence is `NOT_APPLICABLE`; `INCONCLUSIVE` and `NOT_APPLICABLE` do not rank. IQR and maximum RSS also remain descriptive. The pair is not a claim that all workloads or datasets behave the same way.

Arrow IPC codec variants (`none`, `lz4`, and `zstd`) remain in the `fair` lane and share the same Arrow schema, round-trip gate, and query-result contract. They are codec variants, not separate formats or a cross-lane score.

Parquet codec variants (`snappy`, `gzip`, `zstd`, and the existing `zstd-19` high-compression setting) follow the same fair-lane rule and preserve the canonical table contract.

## Evidence contract

Every measured format follows one lifecycle:

```text
DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED
```

An active observation can terminate as `UNSUPPORTED` or `FAILED`. Terminal failures stay visible and do not rank. A round trip must preserve 13 Arrow columns, NULLs, values, expected query counts, and the canonical hash before timing starts.

The four comparability states are:

- `FULL_COMPARABLE`: eligible within the declared lane.
- `ADAPTED`: useful evidence that required a workload or schema adaptation.
- `PARTIAL`: only part of the contract could be exercised.
- `UNAVAILABLE`: no reproducible reader/writer path was available.

## Reproduce

Nix pins Python 3.12, Rust `nightly-2026-07-15` with `rust-src`, `cargo-fuzz`, and the native C/C++ tools. `uv.lock` pins the Python environment.

```bash
nix develop
uv sync --frozen
uv run --frozen format-bench run --profile prompt --dataset github-stars-2026-07-03 --fixture
uv run --frozen format-bench run --profile equivalence --dataset github-stars-2026-07-03 --fixture --pair csv-tsv
```

The repository-level `ty` configuration is authoritative for source roots and intentional optional imports. Reproduce its pinned observation lane with:

```bash
nix develop --command uv sync --frozen --reinstall-package format-bench
nix develop --command ty version
nix develop --command uv run --frozen ty check
```

The fixture command is a non-rankable smoke test. For the full published dataset:

```bash
uv run --frozen format-bench dataset fetch github-stars-2026-07-03
uv run --frozen format-bench prepare --dataset github-stars-2026-07-03 --run-dir runs/fair-local
uv run --frozen format-bench verify --run-dir runs/fair-local
uv run --frozen format-bench run --profile fair --dataset github-stars-2026-07-03 --run-dir runs/fair-local
uv run --frozen format-bench report --run-dir runs/fair-local
```

The native robustness suite records pinned Arrow, Vortex, and FastLanes targets. Arrow requires a checkout at the recorded source commit plus binaries in `native/arrow/build`; Vortex and FastLanes require a checkout whose `HEAD` matches the recorded source commit. FastLanes is recorded as project-seeded rather than coverage-guided. Lance, object JSONL, and TsFile have no confirmed official native target and are retained as `UNSUPPORTED` evidence. Missing binaries or mismatched source checkouts never become a silent pass. Select targets with repeated `--target` options and set the run budget with `--duration-seconds` and `--artifact-budget-mib`.

Robustness reports also aggregate each target's case denominator, pass/fail outcomes, crash and timeout counts, incomplete reasons, duration p50, and artifact/source identities. These are reliability evidence, not a cross-lane score.

```bash
uv run --frozen format-bench run --profile robustness --suite native --dataset github-stars-2026-07-03 \
  --target vortex-file-io --target vortex-compress-roundtrip --duration-seconds 900
```

The manual [`Native robustness Linux x86_64`](.github/workflows/benchmark-native.yml) workflow runs one target per matrix job, caps retained evidence at 1 GiB, and uploads raw evidence plus a package for 14 days. Linux artifacts are named separately from macOS runs; a native crash or harness failure is uploaded before the job reports failure.

See the [native robustness publication notes](docs/native-robustness.md) for the dispatch command and evidence review checklist.

Run `claims` and `prompt` in separate run directories. Omitting `--run-dir` makes `run` prepare and verify a new timestamped directory automatically.

The default fair protocol uses 10 fresh processes per format and operation. Each process performs 5 warmups and 30 measured iterations. Reports include fresh-open and warm p50/p95, IQR, maximum RSS, exact result counts, and normalized result hashes. OS caches are not purged.

## Published evidence

The [strict audit registry](docs/audits/2026-07-19/report.md) records the immutable 174-item review, live GitHub synchronization, Project readback, and [issue map](docs/audits/2026-07-19/issue-map.json). Original scores are preserved; follow-up bugs remain separate Issues.

Release assets are the distribution boundary for the frozen dataset, raw results, checksums, and binary artifacts. Git contains only schemas, manifests, a small fixture, generated Markdown summaries, and code.

Start with the [`v0.1.0` evidence summary](reports/v0.1.0/README.md), then open the platform report or raw Release asset for the measurement details.

macOS ARM and Linux x86_64 are separate runs. Their values must not be combined into a machine ranking. Direct corpus token counts apply only to text; binary formats report `N/A`. Lance data, index, metadata, logical directory size, and external zstd transport size are recorded separately.

The Stars Data Card documents the Apple-heavy source bias, the fact that classifications are not ground truth, and missing historical raw API/classifier provenance. See [`datasets/github-stars-2026-07-03/DATA_CARD.md`](datasets/github-stars-2026-07-03/DATA_CARD.md).

## Repository map

- `src/format_bench/`: CLI, lifecycle, adapters, runners, and reports.
- `datasets/`: immutable dataset contracts and test fixtures.
- `research/formats/`: reproducible negative evidence for unfinished formats.
- `docs/adr/`: architectural decisions.
- `docs/specs/`: executable benchmark and evidence contracts.
- `docs/research-log.md`: reconstructed question and correction history.
- `runs/`: ignored local evidence directories.

## Contributing

Start with an issue that states the claim, primary source, workload, expected result, and comparability class. New storage adapters implement `describe`, `encode`, `read`, `verify_roundtrip`, and the fair scan contract when applicable. Never add a speed result that failed round-trip or answer-set verification.

This repository uses small, non-stacked PRs from current `main`. Generated locks and release artifacts are isolated from human-authored changes. See [`AGENTS.md`](AGENTS.md) for the repository workflow.

## Sources and license

The initial exploration was prompted by [a Japanese overview of emerging formats](https://zenn.dev/mrasu/articles/47dfb30436ebf3). Claim tests use primary project sources for [Apache Parquet](https://parquet.apache.org/), [Lance](https://github.com/lance-format/lance), [Vortex](https://github.com/vortex-data/vortex), [Apache TsFile](https://github.com/apache/tsfile), [FastLanes](https://github.com/cwida/FastLanes), [Nimble](https://github.com/facebookincubator/nimble), and [AnyBlox](https://github.com/AnyBlox/vldb-2025).

Code and original documentation are Apache-2.0. Public GitHub-hosted metadata is not relicensed; see [`DATA_NOTICE.md`](DATA_NOTICE.md).
