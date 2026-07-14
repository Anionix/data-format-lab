# Data Format Lab: fair report

Dataset: `github-stars-2026-07-03`  
Run: `v0.1.0-macos-arm64-fair-1`  
No result in this report is comparable across lanes or hardware runs.

## Environment

| Field | Value |
| --- | --- |
| Git commit | 85e22e1e99898e5683c8b6a7c6acc6aeea8ed234 |
| Flake lock SHA-256 | 5349aa3b52f8c844a7115a25f5b1a2bbd6a7b37847d763a5b5e2c6153357034b |
| Platform | macOS-27.0-arm64-arm-64bit |
| Machine | arm64 |
| Python | 3.12.13 |

## Format Evidence

| Format | Comparability | State | Native bytes | zstd bytes | Write ms | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| csv | FULL_COMPARABLE | BENCHMARKED | 658439 | 157177 | 5.116 | N/A |
| object_jsonl | FULL_COMPARABLE | BENCHMARKED | 1049957 | 170955 | 23.054 | N/A |
| parquet_default | FULL_COMPARABLE | BENCHMARKED | 200031 | 200046 | 16.627 | N/A |
| parquet_zstd19 | FULL_COMPARABLE | BENCHMARKED | 176713 | 175386 | 79.039 | N/A |
| lance_base | FULL_COMPARABLE | BENCHMARKED | 314428 | 202683 | 75.873 | N/A |
| vortex_default | FULL_COMPARABLE | BENCHMARKED | 286328 | 201690 | 122.666 | N/A |
| vortex_compact | FULL_COMPARABLE | BENCHMARKED | 183576 | 172045 | 44.425 | N/A |
| tsfile | ADAPTED | UNSUPPORTED | N/A | N/A | N/A | No module named 'tsfile' |

## Storage Ordering

| Order | Format | Native bytes |
| --- | --- | --- |
| 1 | parquet_zstd19 | 176713 |
| 2 | vortex_compact | 183576 |
| 3 | parquet_default | 200031 |
| 4 | vortex_default | 286328 |
| 5 | lance_base | 314428 |
| 6 | csv | 658439 |
| 7 | object_jsonl | 1049957 |

## Fair Operations

| Format | Operation | Fresh p50 ms | Warm p50 ms | Warm p95 ms | IQR ms | Rows | RSS bytes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| csv | exact_match | 2.36 | 1.677 | 1.844 | 0.13 | 1 | 134004736 |
| csv | filter_ai_llm | 2.411 | 1.687 | 1.818 | 0.116 | 119 | 134971392 |
| csv | filter_repo_stars_gt_100000 | 2.446 | 1.678 | 1.85 | 0.147 | 15 | 135159808 |
| csv | head_10 | 2.259 | 1.634 | 1.8 | 0.108 | 10 | 134217728 |
| csv | project_two | 2.196 | 1.609 | 1.751 | 0.098 | 2331 | 133365760 |
| csv | read_all | 2.225 | 1.648 | 1.794 | 0.111 | 2331 | 133758976 |
| lance_base | exact_match | 3.851 | 1.294 | 1.44 | 0.119 | 1 | 138903552 |
| lance_base | filter_ai_llm | 3.874 | 1.257 | 1.475 | 0.117 | 119 | 139010048 |
| lance_base | filter_repo_stars_gt_100000 | 4.201 | 1.384 | 1.507 | 0.102 | 15 | 139313152 |
| lance_base | head_10 | 3.156 | 0.884 | 1.023 | 0.099 | 10 | 134356992 |
| lance_base | project_two | 2.904 | 0.833 | 0.95 | 0.111 | 2331 | 135069696 |
| lance_base | read_all | 3.695 | 1.429 | 1.58 | 0.108 | 2331 | 135192576 |
| object_jsonl | exact_match | 4.054 | 3.572 | 3.894 | 0.309 | 1 | 138608640 |
| object_jsonl | filter_ai_llm | 4.205 | 3.532 | 3.894 | 0.253 | 119 | 139313152 |
| object_jsonl | filter_repo_stars_gt_100000 | 4.111 | 3.568 | 3.921 | 0.33 | 15 | 138567680 |
| object_jsonl | head_10 | 3.914 | 3.489 | 3.848 | 0.312 | 10 | 138158080 |
| object_jsonl | project_two | 3.973 | 3.52 | 3.838 | 0.254 | 2331 | 137994240 |
| object_jsonl | read_all | 3.954 | 3.459 | 3.811 | 0.306 | 2331 | 138133504 |
| parquet_default | exact_match | 1.944 | 0.873 | 0.964 | 0.081 | 1 | 138764288 |
| parquet_default | filter_ai_llm | 1.925 | 0.861 | 0.979 | 0.071 | 119 | 136617984 |
| parquet_default | filter_repo_stars_gt_100000 | 1.997 | 0.876 | 0.992 | 0.067 | 15 | 144121856 |
| parquet_default | head_10 | 1.781 | 0.802 | 0.885 | 0.075 | 10 | 141926400 |
| parquet_default | project_two | 1.364 | 0.555 | 0.624 | 0.066 | 2331 | 122494976 |
| parquet_default | read_all | 1.755 | 0.786 | 0.891 | 0.063 | 2331 | 141271040 |
| parquet_zstd19 | exact_match | 2.014 | 0.92 | 1.042 | 0.074 | 1 | 139771904 |
| parquet_zstd19 | filter_ai_llm | 2.0 | 0.892 | 1.021 | 0.085 | 119 | 139362304 |
| parquet_zstd19 | filter_repo_stars_gt_100000 | 1.986 | 0.926 | 1.069 | 0.102 | 15 | 143114240 |
| parquet_zstd19 | head_10 | 1.865 | 0.83 | 0.928 | 0.057 | 10 | 140730368 |
| parquet_zstd19 | project_two | 1.323 | 0.553 | 0.624 | 0.059 | 2331 | 122757120 |
| parquet_zstd19 | read_all | 1.811 | 0.838 | 0.93 | 0.065 | 2331 | 140648448 |
| vortex_compact | exact_match | 2.755 | 1.155 | 1.247 | 0.057 | 1 | 126451712 |
| vortex_compact | filter_ai_llm | 2.807 | 1.154 | 1.263 | 0.074 | 119 | 126541824 |
| vortex_compact | filter_repo_stars_gt_100000 | 2.73 | 1.124 | 1.215 | 0.068 | 15 | 126320640 |
| vortex_compact | head_10 | 2.199 | 0.964 | 1.029 | 0.057 | 10 | 124862464 |
| vortex_compact | project_two | 1.277 | 0.296 | 0.347 | 0.03 | 2331 | 123469824 |
| vortex_compact | read_all | 2.174 | 0.955 | 1.034 | 0.049 | 2331 | 124977152 |
| vortex_default | exact_match | 2.259 | 0.668 | 0.729 | 0.052 | 1 | 126664704 |
| vortex_default | filter_ai_llm | 2.36 | 0.694 | 0.766 | 0.053 | 119 | 126648320 |
| vortex_default | filter_repo_stars_gt_100000 | 2.21 | 0.643 | 0.734 | 0.073 | 15 | 126328832 |
| vortex_default | head_10 | 1.79 | 0.524 | 0.586 | 0.044 | 10 | 124928000 |
| vortex_default | project_two | 1.287 | 0.247 | 0.299 | 0.037 | 2331 | 123715584 |
| vortex_default | read_all | 1.853 | 0.602 | 0.663 | 0.045 | 2331 | 124936192 |
