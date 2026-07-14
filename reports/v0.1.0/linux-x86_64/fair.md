# Data Format Lab: fair report

Dataset: `github-stars-2026-07-03`  
Run: `github-stars-2026-07-03-20260714T050312520433Z`
No result in this report is comparable across lanes or hardware runs.

## Environment

| Field | Value |
| --- | --- |
| Git commit | 3f514315269efb910b1c873c23c9e59790d2622b |
| Flake lock SHA-256 | 5349aa3b52f8c844a7115a25f5b1a2bbd6a7b37847d763a5b5e2c6153357034b |
| Platform | Linux-6.17.0-1018-azure-x86_64-with-glibc2.42 |
| Machine | x86_64 |
| Python | 3.12.13 |

## Format Evidence

| Format | Comparability | State | Native bytes | zstd bytes | Write ms | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| csv | FULL_COMPARABLE | REPORTED | 658439 | 157177 | 1.352 | N/A |
| object_jsonl | FULL_COMPARABLE | REPORTED | 1049957 | 170955 | 37.904 | N/A |
| parquet_default | FULL_COMPARABLE | REPORTED | 200031 | 200046 | 4.31 | N/A |
| parquet_zstd19 | FULL_COMPARABLE | REPORTED | 176713 | 175386 | 123.072 | N/A |
| lance_base | FULL_COMPARABLE | REPORTED | 315004 | 202447 | 12.361 | N/A |
| vortex_default | FULL_COMPARABLE | REPORTED | 286416 | 201833 | 64.367 | N/A |
| vortex_compact | FULL_COMPARABLE | REPORTED | 183576 | 172045 | 64.215 | N/A |
| tsfile | ADAPTED | UNSUPPORTED | N/A | N/A | N/A | No module named 'tsfile' |

## Storage Ordering

| Order | Format | Native bytes |
| --- | --- | --- |
| 1 | parquet_zstd19 | 176713 |
| 2 | vortex_compact | 183576 |
| 3 | parquet_default | 200031 |
| 4 | vortex_default | 286416 |
| 5 | lance_base | 315004 |
| 6 | csv | 658439 |
| 7 | object_jsonl | 1049957 |

## Fair Operations

| Format | Operation | Fresh p50 ms | Warm p50 ms | Warm p95 ms | IQR ms | Rows | Result hash | RSS bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| csv | exact_match | 3.016 | 1.635 | 1.687 | 0.031 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 291803136 |
| csv | filter_ai_llm | 3.058 | 1.655 | 1.754 | 0.031 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 291803136 |
| csv | filter_repo_stars_gt_100000 | 3.125 | 1.646 | 1.794 | 0.043 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 291803136 |
| csv | head_10 | 2.984 | 1.554 | 1.649 | 0.045 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 291803136 |
| csv | project_two | 2.907 | 1.536 | 1.635 | 0.036 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 291803136 |
| csv | read_all | 2.918 | 1.536 | 1.588 | 0.029 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 291803136 |
| lance_base | exact_match | 5.613 | 2.18 | 2.28 | 0.077 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 291803136 |
| lance_base | filter_ai_llm | 5.577 | 2.144 | 2.271 | 0.09 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 291803136 |
| lance_base | filter_repo_stars_gt_100000 | 6.117 | 2.304 | 2.437 | 0.104 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 291803136 |
| lance_base | head_10 | 4.405 | 1.487 | 1.594 | 0.067 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 291803136 |
| lance_base | project_two | 3.912 | 1.317 | 1.372 | 0.043 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 291803136 |
| lance_base | read_all | 5.533 | 2.425 | 2.846 | 0.599 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 291803136 |
| object_jsonl | exact_match | 6.303 | 5.009 | 5.15 | 0.1 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 288227328 |
| object_jsonl | filter_ai_llm | 6.298 | 5.021 | 5.262 | 0.101 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 291803136 |
| object_jsonl | filter_repo_stars_gt_100000 | 6.217 | 4.994 | 5.147 | 0.093 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 291803136 |
| object_jsonl | head_10 | 6.179 | 4.904 | 5.112 | 0.095 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 291803136 |
| object_jsonl | project_two | 6.258 | 4.903 | 5.124 | 0.102 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 291803136 |
| object_jsonl | read_all | 6.043 | 4.914 | 5.109 | 0.121 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 291803136 |
| parquet_default | exact_match | 3.355 | 1.506 | 1.593 | 0.055 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 291803136 |
| parquet_default | filter_ai_llm | 3.629 | 1.551 | 1.708 | 0.075 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 288227328 |
| parquet_default | filter_repo_stars_gt_100000 | 3.454 | 1.513 | 1.617 | 0.059 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 291803136 |
| parquet_default | head_10 | 3.273 | 1.411 | 1.499 | 0.062 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 291803136 |
| parquet_default | project_two | 1.926 | 0.795 | 0.852 | 0.03 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 291803136 |
| parquet_default | read_all | 3.368 | 1.403 | 1.535 | 0.07 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 288227328 |
| parquet_zstd19 | exact_match | 3.415 | 1.578 | 1.662 | 0.08 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 291803136 |
| parquet_zstd19 | filter_ai_llm | 3.512 | 1.592 | 1.696 | 0.066 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 291803136 |
| parquet_zstd19 | filter_repo_stars_gt_100000 | 3.483 | 1.565 | 1.657 | 0.042 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 291803136 |
| parquet_zstd19 | head_10 | 3.388 | 1.464 | 1.562 | 0.063 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 291803136 |
| parquet_zstd19 | project_two | 1.902 | 0.807 | 0.856 | 0.034 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 291803136 |
| parquet_zstd19 | read_all | 3.27 | 1.449 | 1.538 | 0.066 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 291803136 |
| vortex_compact | exact_match | 4.908 | 2.308 | 2.398 | 0.053 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 291803136 |
| vortex_compact | filter_ai_llm | 5.007 | 2.315 | 2.4 | 0.05 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 291803136 |
| vortex_compact | filter_repo_stars_gt_100000 | 4.755 | 2.23 | 2.332 | 0.041 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 291803136 |
| vortex_compact | head_10 | 4.098 | 1.866 | 1.947 | 0.049 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 291278848 |
| vortex_compact | project_two | 2.499 | 0.654 | 0.683 | 0.022 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 291803136 |
| vortex_compact | read_all | 4.724 | 1.991 | 2.08 | 0.052 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 291803136 |
| vortex_default | exact_match | 3.992 | 1.528 | 1.617 | 0.047 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 291803136 |
| vortex_default | filter_ai_llm | 4.116 | 1.596 | 1.654 | 0.034 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 291803136 |
| vortex_default | filter_repo_stars_gt_100000 | 3.972 | 1.481 | 1.558 | 0.049 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 291803136 |
| vortex_default | head_10 | 3.307 | 1.196 | 1.246 | 0.036 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 288227328 |
| vortex_default | project_two | 2.475 | 0.604 | 0.64 | 0.027 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 290885632 |
| vortex_default | read_all | 4.309 | 1.523 | 1.612 | 0.047 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 291803136 |
