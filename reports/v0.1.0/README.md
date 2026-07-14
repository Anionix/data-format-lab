# v0.1.0 Evidence Summary

This release tests the frozen `github-stars-2026-07-03` dataset: 2,331 rows,
13 typed columns, source SHA-256
`39cc70109d9dddf947257584e15f2f9a6bc97dcdf0a7bf939c26cccbcda0e22e`,
and canonical hash
`1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39`.
It does not name a universal winner.

Raw `manifest.json`, `results.json`, generated reports, and checksums are in the
[`v0.1.0` Release](https://github.com/Anionix/data-format-lab/releases/tag/v0.1.0).
Generated platform reports are under [`macos-arm64`](macos-arm64/) and
[`linux-x86_64`](linux-x86_64/). Never rank values across those platforms.

## Fair storage

All ranked formats returned 2,331 rows, 119 AI/LLM rows, 15 repositories above
100,000 stars, one exact match, and the canonical hash.

### macOS ARM run 1

| Rank | Format | Native bytes | Warm read-all p50 ms |
| ---: | --- | ---: | ---: |
| 1 | Parquet zstd-19 | 176,713 | 0.838 |
| 2 | Vortex compact | 183,576 | 0.955 |
| 3 | Parquet default | 200,031 | 0.786 |
| 4 | Vortex default | 286,328 | 0.602 |
| 5 | Lance base | 314,428 | 1.429 |
| 6 | CSV | 658,439 | 1.648 |
| 7 | object JSONL | 1,049,957 | 3.459 |

### Linux x86_64 run 1

| Rank | Format | Native bytes | Warm read-all p50 ms |
| ---: | --- | ---: | ---: |
| 1 | Parquet zstd-19 | 176,713 | 1.165 |
| 2 | Vortex compact | 183,576 | 1.363 |
| 3 | Parquet default | 200,031 | 1.139 |
| 4 | Vortex default | 286,416 | 0.963 |
| 5 | Lance base | 314,300 | 2.072 |
| 6 | CSV | 658,439 | 1.260 |
| 7 | object JSONL | 1,049,957 | 2.996 |

Native size and read latency answer different questions. zstd-19 produced the
smallest artifact here but had a substantially higher write cost than default
Parquet. Vortex default had the lowest warm read-all p50 in both platform runs.

## Claim workloads

These results are comparable only inside each workload and platform.

| Platform | Claim | Result from run 1 |
| --- | --- | --- |
| macOS ARM | Lance FTS | 944,129 logical bytes; 418,696 index bytes; `agent` p50 0.579 ms |
| macOS ARM | Vortex sorted full projection | Parquet 5.637 ms; Vortex 2.357 ms |
| macOS ARM | Vortex unsorted random 1,000 | Parquet 20.886 ms; Vortex 2.148 ms |
| macOS ARM | TsFile time range | Parquet 2.324 ms; TsFile 2.034 ms; 1,000 rows each |
| Linux x86_64 | Lance FTS | 944,578 logical bytes; 418,696 index bytes; `agent` p50 1.566 ms |
| Linux x86_64 | Vortex sorted full projection | Parquet 14.072 ms; Vortex 4.283 ms |
| Linux x86_64 | Vortex unsorted random 1,000 | Parquet 25.169 ms; Vortex 3.973 ms |
| Linux x86_64 | TsFile time range | Parquet 4.129 ms; TsFile 2.767 ms; 1,000 rows each |

The TsFile claim used 1,000,000 time-series rows. TsFile was 313,744 bytes and
Parquet was 5,777,023 bytes in every run, but TsFile writes were much slower:
5.75 s versus 0.48 s on macOS run 1 and 10.10 s versus 0.74 s on Linux run 1.

The Vortex stress artifacts were deterministic. Sorted Parquet/Vortex sizes
were 2,761,465/2,026,488 bytes; unsorted sizes were
24,925,948/6,343,112 bytes. This supports the tested scan claim, not a general
database-performance claim.

## Prompt tokens

The taxonomy dictionary is included once in every total.

| Representation | Total bytes | `o200k_base` | `cl100k_base` |
| --- | ---: | ---: | ---: |
| Compact TSV | 345,115 | 93,377 | 92,756 |
| array JSONL | 390,697 | 105,866 | 103,745 |
| object JSONL | 598,156 | 148,736 | 145,070 |

Both runs on both platforms produced identical prompt metrics. Binary formats
remain `N/A` for direct corpus token counts. Retrieval outputs are normalized
to the same Compact TSV before token measurement.

## Reproducibility

- Both platforms produced identical result counts and normalized hashes for all
  42 fair operations. Non-Lance fair artifact sizes were identical between runs.
- macOS fair warm p50 changed by 1.43% at the median and 5.76% at the maximum.
  Linux changed by 25.15% at the median and 64.35% at the maximum, so timings
  are observations rather than stable constants.
- Lance base changed from 314,428 to 314,683 bytes on macOS and from 314,300 to
  315,516 bytes on Linux. Indexed logical size also changed, while the FTS index
  stayed exactly 418,696 bytes.
- An earlier exploratory run observed a 704-byte Lance delta. Its raw artifact
  was not retained, so it is a research-log concern rather than release evidence.
- Vortex stress sizes, TsFile/Parquet time-series sizes and result counts, and
  all prompt metrics were identical between run 1 and run 2.

## Incomplete formats

FastLanes is `PARTIAL/FAILED`, Nimble is `UNAVAILABLE/UNSUPPORTED`, and AnyBlox
is `PARTIAL/FAILED` at the pinned attempts. Their exact commits, failures, and
retry conditions remain in [`research/formats`](../../research/formats/); they
do not enter rankings.
