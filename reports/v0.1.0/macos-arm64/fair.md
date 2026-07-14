# Data Format Lab: fair report

Dataset: `github-stars-2026-07-03`  
Run: `v0.1.0-final-macos-arm64-fair-1`
No result in this report is comparable across lanes or hardware runs.

## Environment

| Field | Value |
| --- | --- |
| Git commit | 3f514315269efb910b1c873c23c9e59790d2622b |
| Flake lock SHA-256 | 5349aa3b52f8c844a7115a25f5b1a2bbd6a7b37847d763a5b5e2c6153357034b |
| Platform | macOS-27.0-arm64-arm-64bit |
| Machine | arm64 |
| Python | 3.12.13 |

## Format Evidence

| Format | Comparability | State | Native bytes | zstd bytes | Write ms | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| csv | FULL_COMPARABLE | REPORTED | 658439 | 157177 | 5.866 | N/A |
| object_jsonl | FULL_COMPARABLE | REPORTED | 1049957 | 170955 | 22.604 | N/A |
| parquet_default | FULL_COMPARABLE | REPORTED | 200031 | 200046 | 13.851 | N/A |
| parquet_zstd19 | FULL_COMPARABLE | REPORTED | 176713 | 175386 | 80.257 | N/A |
| lance_base | FULL_COMPARABLE | REPORTED | 315515 | 204348 | 89.915 | N/A |
| vortex_default | FULL_COMPARABLE | REPORTED | 286328 | 201690 | 104.27 | N/A |
| vortex_compact | FULL_COMPARABLE | REPORTED | 183576 | 172045 | 45.229 | N/A |
| tsfile | ADAPTED | UNSUPPORTED | N/A | N/A | N/A | No module named 'tsfile' |

## Storage Ordering

| Order | Format | Native bytes |
| --- | --- | --- |
| 1 | parquet_zstd19 | 176713 |
| 2 | vortex_compact | 183576 |
| 3 | parquet_default | 200031 |
| 4 | vortex_default | 286328 |
| 5 | lance_base | 315515 |
| 6 | csv | 658439 |
| 7 | object_jsonl | 1049957 |

## Fair Operations

| Format | Operation | Fresh p50 ms | Warm p50 ms | Warm p95 ms | IQR ms | Rows | Result hash | RSS bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| csv | exact_match | 2.585 | 1.721 | 2.216 | 0.156 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 134078464 |
| csv | filter_ai_llm | 2.501 | 1.717 | 1.962 | 0.116 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 134176768 |
| csv | filter_repo_stars_gt_100000 | 2.435 | 1.675 | 1.835 | 0.108 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 134430720 |
| csv | head_10 | 2.318 | 1.672 | 3.718 | 0.15 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 133783552 |
| csv | project_two | 2.355 | 1.646 | 3.183 | 0.245 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 133988352 |
| csv | read_all | 2.46 | 1.73 | 1.955 | 0.182 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 133693440 |
| lance_base | exact_match | 4.164 | 1.278 | 1.471 | 0.132 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 138895360 |
| lance_base | filter_ai_llm | 4.307 | 1.297 | 1.51 | 0.135 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 138805248 |
| lance_base | filter_repo_stars_gt_100000 | 4.627 | 1.47 | 2.058 | 0.164 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 139354112 |
| lance_base | head_10 | 3.379 | 0.891 | 1.379 | 0.135 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 134307840 |
| lance_base | project_two | 3.215 | 0.803 | 0.937 | 0.081 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 135102464 |
| lance_base | read_all | 3.847 | 1.429 | 1.75 | 0.139 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 135143424 |
| object_jsonl | exact_match | 4.232 | 3.634 | 3.963 | 0.291 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 139116544 |
| object_jsonl | filter_ai_llm | 4.392 | 3.561 | 3.935 | 0.3 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 138895360 |
| object_jsonl | filter_repo_stars_gt_100000 | 4.515 | 3.963 | 4.561 | 0.431 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 137633792 |
| object_jsonl | head_10 | 4.157 | 3.539 | 3.891 | 0.222 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 137863168 |
| object_jsonl | project_two | 4.129 | 3.51 | 3.907 | 0.28 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 138076160 |
| object_jsonl | read_all | 4.177 | 3.537 | 3.867 | 0.236 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 137560064 |
| parquet_default | exact_match | 2.127 | 0.927 | 1.119 | 0.084 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 138469376 |
| parquet_default | filter_ai_llm | 2.19 | 0.911 | 1.088 | 0.102 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 144908288 |
| parquet_default | filter_repo_stars_gt_100000 | 2.231 | 0.933 | 1.201 | 0.119 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 143097856 |
| parquet_default | head_10 | 1.934 | 0.826 | 1.545 | 0.089 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 135938048 |
| parquet_default | project_two | 1.412 | 0.557 | 0.633 | 0.047 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 122773504 |
| parquet_default | read_all | 1.891 | 0.82 | 0.944 | 0.083 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 142303232 |
| parquet_zstd19 | exact_match | 2.134 | 0.964 | 1.417 | 0.088 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 142655488 |
| parquet_zstd19 | filter_ai_llm | 2.185 | 0.98 | 1.857 | 0.175 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 142712832 |
| parquet_zstd19 | filter_repo_stars_gt_100000 | 2.173 | 0.958 | 1.26 | 0.122 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 143384576 |
| parquet_zstd19 | head_10 | 2.211 | 0.906 | 1.157 | 0.102 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 141524992 |
| parquet_zstd19 | project_two | 1.456 | 0.569 | 1.125 | 0.066 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 122937344 |
| parquet_zstd19 | read_all | 2.035 | 0.883 | 1.24 | 0.115 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 140443648 |
| vortex_compact | exact_match | 3.343 | 1.232 | 1.351 | 0.083 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 127344640 |
| vortex_compact | filter_ai_llm | 3.361 | 1.28 | 1.393 | 0.101 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 127631360 |
| vortex_compact | filter_repo_stars_gt_100000 | 3.421 | 1.234 | 1.356 | 0.096 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 127246336 |
| vortex_compact | head_10 | 2.866 | 1.07 | 1.159 | 0.076 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 125919232 |
| vortex_compact | project_two | 1.916 | 0.374 | 0.461 | 0.041 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 124649472 |
| vortex_compact | read_all | 3.147 | 1.281 | 1.398 | 0.099 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 126787584 |
| vortex_default | exact_match | 2.887 | 0.763 | 0.89 | 0.081 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 127533056 |
| vortex_default | filter_ai_llm | 3.079 | 0.763 | 0.868 | 0.085 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 127639552 |
| vortex_default | filter_repo_stars_gt_100000 | 2.83 | 0.725 | 0.826 | 0.067 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 127254528 |
| vortex_default | head_10 | 2.365 | 0.616 | 0.687 | 0.044 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 126091264 |
| vortex_default | project_two | 1.83 | 0.307 | 0.356 | 0.032 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 124665856 |
| vortex_default | read_all | 2.718 | 0.933 | 1.029 | 0.061 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 126754816 |
