# Equivalence Expansion Task Map

This map is the handoff record for the v0.2 equivalence expansion. Code PRs remain serial because the registry, contract, and report are shared. Dataset investigation and independent runs can proceed in parallel.

## Completed Locally

| Task | Evidence |
| --- | --- |
| `T-CONTRACT` | `Lane.EQUIVALENCE`, `Lane.ENGINE_CONTAINER`, declared `WorkloadSpec`, lifecycle gate |
| `T-DEPENDENCIES` | pinned `cbor2`, `duckdb`, `fastavro`, `msgpack` in `pyproject.toml` and `uv.lock` |
| `T-ADAPTER-TEXT-ARROW` | TSV, Feather v2, ORC adapters and round-trip tests |
| `T-ADAPTER-ROW` | Avro OCF, MessagePack, CBOR adapters and strict envelope checks |
| `T-ENGINE` | SQLite and DuckDB adapters with deterministic row ordering |
| `T-RUNNER-REPORT` | pair registry, independent bootstrap intervals, CLI, JSON evidence, Markdown report |
| `T-DESIGN-AUDIT` | PASS/FAIL implementation audit without a maturity score |
| `T-DATASET-CONTRACT` | manifest validation, dataset-declared workloads, five acquisition manifests and fixtures |

## Parallel Research Inputs

- `T-DATA-UCI`: UCI Online Retail II and Bank Marketing source/member hashes, variant selection, and licensing notes.
- `T-DATA-NYC-OWID`: Socrata query/pagination contract and OWID source/codebook provenance.
- `T-DATA-GEONAMES`: `cities500.zip` member contract, strict 19-field parsing, and sorting policy.
- `T-AUDIT`: Stars-specific assumptions, SQL result validation, path containment, and failed-worker state were converted into tests or tracked follow-ups.
- `T-PR-MAP`: the earlier equivalence work was reconstructed into contract, adapter, runner, audit, and dataset slices.

## Remaining Before Public v0.2 Candidate

1. Add source-specific normalizers and immutable Release assets for full UCI, NYC, OWID, and GeoNames snapshots. Git keeps only manifests and fixtures.
2. Run pilot and full measurements in independent dataset run directories: two fresh processes for pilots; 10 fresh processes, 5 warmups, and 30 measurements for publication.
3. Add report/checksum/package assertions for the six datasets and six registered pairs.
4. Create non-stacked PRs from the latest `origin/main`, merge in dependency order, and perform post-merge review-thread closeout.

The current local branch is not a publication claim until these remaining evidence and GitHub steps are complete. Failed or unavailable formats remain valid terminal evidence and are not ranked.
