# Data Format Lab: prompt report

Dataset: `github-stars-2026-07-03`  
Run: `v0.1.0-macos-arm64-prompt-1`  
No result in this report is comparable across lanes or hardware runs.

## Environment

| Field | Value |
| --- | --- |
| Git commit | 85e22e1e99898e5683c8b6a7c6acc6aeea8ed234 |
| Flake lock SHA-256 | 5349aa3b52f8c844a7115a25f5b1a2bbd6a7b37847d763a5b5e2c6153357034b |
| Platform | macOS-27.0-arm64-arm-64bit |
| Machine | arm64 |
| Python | 3.12.13 |

## Prompt Corpus

| Format | Payload bytes | Taxonomy bytes | Total bytes | o200k | cl100k |
| --- | --- | --- | --- | --- | --- |
| array_jsonl | 384808 | 5889 | 390697 | 105866 | 103745 |
| compact_tsv | 339226 | 5889 | 345115 | 93377 | 92756 |
| object_jsonl | 592267 | 5889 | 598156 | 148736 | 145070 |

## Retrieval Payload

| Requested | Rows | Bytes | o200k | cl100k |
| --- | --- | --- | --- | --- |
| 5 | 5 | 1217 | 372 | 369 |
| 10 | 10 | 2580 | 722 | 719 |
| 20 | 20 | 5090 | 1372 | 1371 |

Direct token counts for binary formats are N/A.
