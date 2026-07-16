# Arrow IPC Incremental Fair Evidence

This is an incremental fair-lane result for the Arrow IPC file container. It
does not replace the v0.1.0 platform reports or establish a cross-language
interoperability matrix.

| Field | Value |
| --- | --- |
| Dataset | `github-stars-2026-07-03` |
| Rows / columns | 2,331 / 13 |
| Source commit | `97c49d3f329589f506ec887940737799c49fd2ec` |
| Flake lock SHA-256 | `1d8b3b85a0f5f144f6076ca7d4de031d1b2c7b50bc62c1bd12d43dd0141ad54c` |
| Platform | macOS ARM64, Python 3.12.13 |
| PyArrow | 23.0.1 |
| Protocol | 10 fresh processes, 5 warmups, 30 measurements; OS cache retained |

## Conformance

The artifact used the `arrow-ipc-file` container with no compression. The
round trip passed with canonical hash
`1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39` and the
expected counts: 119 `AI / LLM` rows, 15 rows above 100,000 stars, and one
exact match.

| Native bytes | External zstd bytes | Write p50 ms |
| ---: | ---: | ---: |
| 672,234 | 190,263 | 2.993 |

## Fair Operations

| Operation | Warm p50 ms | Warm p95 ms | IQR ms | Rows |
| --- | ---: | ---: | ---: | ---: |
| `exact_match` | 0.139 | 0.239 | 0.028 | 1 |
| `filter_ai_llm` | 0.148 | 0.254 | 0.020 | 119 |
| `filter_repo_stars_gt_100000` | 0.135 | 0.200 | 0.018 | 15 |
| `head_10` | 0.111 | 0.149 | 0.021 | 10 |
| `project_two` | 0.108 | 0.150 | 0.014 | 2,331 |
| `read_all` | 0.104 | 0.135 | 0.020 | 2,331 |

Arrow IPC is now a `FULL_COMPARABLE` fair format. These values describe this
dataset and host; they do not measure Arrow IPC consumer interoperability,
append semantics, or a universal format score.
