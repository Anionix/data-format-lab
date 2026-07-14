# Data Format Lab: fair report

Dataset: `github-stars-2026-07-03`  
Run: `github-stars-2026-07-03-20260714T015142717351Z`  
No result in this report is comparable across lanes or hardware runs.

## Environment

| Field | Value |
| --- | --- |
| Git commit | c09ac84c98d3a9a2452c13f78c3459b580bd152c |
| Flake lock SHA-256 | 5349aa3b52f8c844a7115a25f5b1a2bbd6a7b37847d763a5b5e2c6153357034b |
| Platform | Linux-6.17.0-1018-azure-x86_64-with-glibc2.42 |
| Machine | x86_64 |
| Python | 3.12.13 |

## Format Evidence

| Format | Comparability | State | Native bytes | zstd bytes | Write ms | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| csv | FULL_COMPARABLE | BENCHMARKED | 658439 | 157177 | 0.996 | N/A |
| object_jsonl | FULL_COMPARABLE | BENCHMARKED | 1049957 | 170955 | 22.205 | N/A |
| parquet_default | FULL_COMPARABLE | BENCHMARKED | 200031 | 200046 | 3.403 | N/A |
| parquet_zstd19 | FULL_COMPARABLE | BENCHMARKED | 176713 | 175386 | 84.363 | N/A |
| lance_base | FULL_COMPARABLE | BENCHMARKED | 314300 | 204289 | 11.167 | N/A |
| vortex_default | FULL_COMPARABLE | BENCHMARKED | 286416 | 201833 | 46.331 | N/A |
| vortex_compact | FULL_COMPARABLE | BENCHMARKED | 183576 | 172045 | 45.715 | N/A |
| tsfile | ADAPTED | UNSUPPORTED | N/A | N/A | N/A | No module named 'tsfile' |

## Storage Ordering

| Order | Format | Native bytes |
| --- | --- | --- |
| 1 | parquet_zstd19 | 176713 |
| 2 | vortex_compact | 183576 |
| 3 | parquet_default | 200031 |
| 4 | vortex_default | 286416 |
| 5 | lance_base | 314300 |
| 6 | csv | 658439 |
| 7 | object_jsonl | 1049957 |

## Fair Operations

| Format | Operation | Fresh p50 ms | Warm p50 ms | Warm p95 ms | IQR ms | Rows | RSS bytes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| csv | exact_match | 3.264 | 1.351 | 1.457 | 0.168 | 1 | 288206848 |
| csv | filter_ai_llm | 3.289 | 1.39 | 1.606 | 0.159 | 119 | 288206848 |
| csv | filter_repo_stars_gt_100000 | 3.463 | 1.356 | 1.582 | 0.153 | 15 | 288206848 |
| csv | head_10 | 2.943 | 1.256 | 1.354 | 0.184 | 10 | 288206848 |
| csv | project_two | 3.123 | 1.243 | 1.481 | 0.213 | 2331 | 288206848 |
| csv | read_all | 3.175 | 1.26 | 1.358 | 0.158 | 2331 | 288206848 |
| lance_base | exact_match | 4.884 | 1.914 | 2.122 | 0.082 | 1 | 285822976 |
| lance_base | filter_ai_llm | 4.918 | 1.887 | 1.973 | 0.073 | 119 | 285822976 |
| lance_base | filter_repo_stars_gt_100000 | 5.408 | 2.033 | 2.123 | 0.07 | 15 | 288206848 |
| lance_base | head_10 | 3.986 | 1.287 | 1.407 | 0.075 | 10 | 288206848 |
| lance_base | project_two | 3.534 | 1.129 | 1.196 | 0.053 | 2331 | 288206848 |
| lance_base | read_all | 4.713 | 2.072 | 2.628 | 0.436 | 2331 | 287420416 |
| object_jsonl | exact_match | 4.974 | 3.116 | 3.402 | 0.177 | 1 | 285822976 |
| object_jsonl | filter_ai_llm | 4.961 | 3.147 | 3.414 | 0.162 | 119 | 285822976 |
| object_jsonl | filter_repo_stars_gt_100000 | 5.025 | 3.174 | 3.687 | 0.284 | 15 | 288206848 |
| object_jsonl | head_10 | 5.003 | 3.015 | 3.268 | 0.148 | 10 | 288206848 |
| object_jsonl | project_two | 4.858 | 3.008 | 3.273 | 0.16 | 2331 | 288337920 |
| object_jsonl | read_all | 4.706 | 2.996 | 3.266 | 0.157 | 2331 | 288206848 |
| parquet_default | exact_match | 3.701 | 1.257 | 1.471 | 0.057 | 1 | 288206848 |
| parquet_default | filter_ai_llm | 3.81 | 1.263 | 1.514 | 0.055 | 119 | 285822976 |
| parquet_default | filter_repo_stars_gt_100000 | 3.824 | 1.26 | 1.505 | 0.121 | 15 | 288206848 |
| parquet_default | head_10 | 3.66 | 1.162 | 1.395 | 0.043 | 10 | 288206848 |
| parquet_default | project_two | 2.025 | 0.623 | 0.723 | 0.061 | 2331 | 288206848 |
| parquet_default | read_all | 3.517 | 1.139 | 1.366 | 0.051 | 2331 | 285822976 |
| parquet_zstd19 | exact_match | 3.563 | 1.29 | 1.507 | 0.063 | 1 | 288206848 |
| parquet_zstd19 | filter_ai_llm | 4.117 | 1.3 | 1.535 | 0.113 | 119 | 288206848 |
| parquet_zstd19 | filter_repo_stars_gt_100000 | 3.841 | 1.313 | 1.561 | 0.134 | 15 | 288206848 |
| parquet_zstd19 | head_10 | 3.512 | 1.197 | 1.406 | 0.124 | 10 | 288206848 |
| parquet_zstd19 | project_two | 2.053 | 0.635 | 0.802 | 0.093 | 2331 | 288206848 |
| parquet_zstd19 | read_all | 3.748 | 1.165 | 1.382 | 0.066 | 2331 | 288206848 |
| vortex_compact | exact_match | 4.022 | 1.734 | 1.975 | 0.055 | 1 | 288206848 |
| vortex_compact | filter_ai_llm | 3.921 | 1.754 | 1.984 | 0.068 | 119 | 288206848 |
| vortex_compact | filter_repo_stars_gt_100000 | 3.864 | 1.672 | 1.718 | 0.031 | 15 | 288206848 |
| vortex_compact | head_10 | 3.052 | 1.348 | 1.526 | 0.053 | 10 | 285822976 |
| vortex_compact | project_two | 1.682 | 0.415 | 0.502 | 0.031 | 2331 | 288206848 |
| vortex_compact | read_all | 3.139 | 1.363 | 1.533 | 0.147 | 2331 | 286294016 |
| vortex_default | exact_match | 3.191 | 1.186 | 1.253 | 0.031 | 1 | 285822976 |
| vortex_default | filter_ai_llm | 3.145 | 1.235 | 1.388 | 0.057 | 119 | 285822976 |
| vortex_default | filter_repo_stars_gt_100000 | 3.129 | 1.137 | 1.338 | 0.036 | 15 | 288337920 |
| vortex_default | head_10 | 2.441 | 0.853 | 0.968 | 0.077 | 10 | 285822976 |
| vortex_default | project_two | 1.778 | 0.361 | 0.397 | 0.023 | 2331 | 285822976 |
| vortex_default | read_all | 2.661 | 0.963 | 1.007 | 0.038 | 2331 | 288206848 |
