# Native Robustness Publication

The manual Linux workflow is the publication path for official native fuzz evidence. It runs one target per matrix job on `ubuntu-24.04`, keeps the Linux x86_64 run separate from macOS ARM observations, and uploads the run directory for 14 days. Dispatch durations are validated to `1..3300` seconds; the 90-minute job timeout leaves setup and evidence-publication margin.

Dispatch it from the repository's Actions tab, or with:

```bash
gh workflow run benchmark-native.yml \
  -f release_id=353517336 -f duration_seconds=900
```

The workflow downloads the fixed `github-stars-2026-07-03` Release asset and verifies both its compressed and decompressed SHA-256 values. It checks out the pinned Arrow, Vortex, or FastLanes source only for jobs that need it. Lance, object JSONL, and TsFile are included as explicit `UNSUPPORTED` evidence jobs because no confirmed official native target exists.

Each available target receives a 900-second default budget and a 1 GiB evidence budget. Vortex cargo-fuzz targets are compiled before the timed run so compilation does not consume the fuzzing interval. A target crash or harness failure still uploads `manifest.json`, `results.json`, `report.md` when available, stdout, stderr, and native artifacts. The report keeps `coverage-guided` and `project-seeded` harnesses visibly separate.

Before publication, inspect the uploaded `results.json` and `report.md`, record the workflow run ID, commit, source commits, hardware, and observed outcomes, then attach the evidence to the corresponding Release. Do not combine this Linux run with macOS ARM values or rank unlike native harnesses.
