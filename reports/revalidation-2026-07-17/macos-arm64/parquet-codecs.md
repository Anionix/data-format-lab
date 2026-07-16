# Data Format Lab: fair report

Dataset: `github-stars-2026-07-03`  
Run: `data-format-lab-parquet-codecs-clean-1784236998`  
No result in this report is comparable across lanes or hardware runs.

## Environment

| Field | Value |
| --- | --- |
| Git commit | 85ac7ded30d7fad473de138a6846abf90a278e56 |
| Flake lock SHA-256 | 1d8b3b85a0f5f144f6076ca7d4de031d1b2c7b50bc62c1bd12d43dd0141ad54c |
| Platform | macOS-27.0-arm64-arm-64bit |
| Machine | arm64 |
| Hardware model | Mac14,7 |
| Python | 3.12.13 |

## Dataset Contract

| Field | Value |
| --- | --- |
| Rows | 2331 |
| Columns | 13 |
| Schema | group:string?, category:string?, micro_category:string?, classification_score:float64?, matched_terms:string?, full_name:string?, html_url:string?, language:string?, repo_stars:int64?, fork:bool?, archived:bool?, topics:string?, description:string? |
| Source SHA-256 | 39cc70109d9dddf947257584e15f2f9a6bc97dcdf0a7bf939c26cccbcda0e22e |
| Canonical hash | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 |
| Expected counts | {"full_name_anomalyco_opencode": 1, "group_ai_llm": 119, "repo_stars_gt_100000": 15, "rows": 2331} |

## Measurement Protocol

| Setting | Value |
| --- | --- |
| fresh_processes | 10 |
| iterations | 30 |
| os_cache_purged | False |
| seed | 20260703 |
| timeout_seconds | 120 |
| warmups | 5 |

## Package Versions

| Package | Version |
| --- | --- |
| pandas | N/A |
| pyarrow | 23.0.1 |
| pyfastlanes | N/A |
| pylance | 8.0.0 |
| pytz | N/A |
| tiktoken | 0.12.0 |
| tsfile | N/A |
| tzdata | N/A |
| vortex-data | 0.76.0 |
| zstandard | 0.25.0 |

## Evidence Digests

| File | SHA-256 |
| --- | --- |
| Manifest SHA-256 | f53c731b9221cf2db2a1a5e931bea332071ceb134dfa7f9ebb7fe87003a6ebd4 |
| Results SHA-256 | 989f8819e6a4a36481171fbbe64c7d88fb58417b170143ebef40714e68279165 |
| Input manifest SHA-256 | 9c684dac968596d25a95e4731514fa742c81d0a7c01eeb2666c6790473261b8f |
| Input source SHA-256 | 39cc70109d9dddf947257584e15f2f9a6bc97dcdf0a7bf939c26cccbcda0e22e |

Format settings in the Format Evidence table are the writer settings used for each artifact.
The `format-bench package` command includes these raw JSON files and referenced artifacts; it writes the archive SHA-256 to the adjacent `.sha256` file.

## Durable Evidence

| File | URL |
| --- | --- |
| Raw archive | https://github.com/Anionix/data-format-lab/releases/download/v0.1.0/data-format-lab-fair-macos-arm64-data-format-lab-parquet-codecs-clean-1784236998.tar.zst |
| SHA-256 checksum | https://github.com/Anionix/data-format-lab/releases/download/v0.1.0/data-format-lab-fair-macos-arm64-data-format-lab-parquet-codecs-clean-1784236998.tar.zst.sha256 |

## Format Evidence

| Format | Comparability | State | Native bytes | zstd bytes | Write ms | Settings | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| parquet_default | FULL_COMPARABLE | REPORTED | 200031 | 200046 | 22.347 | {"compression":"zstd","dictionary":true,"level":"library-default"} | N/A |
| parquet_zstd19 | FULL_COMPARABLE | REPORTED | 176713 | 175386 | 135.448 | {"compression":"zstd","dictionary":true,"level":19} | N/A |
| parquet_snappy | FULL_COMPARABLE | REPORTED | 269320 | 228397 | 4.788 | {"compression":"snappy","dictionary":true,"level":"library-default"} | N/A |
| parquet_gzip | FULL_COMPARABLE | REPORTED | 187083 | 185873 | 57.07 | {"compression":"gzip","dictionary":true,"level":"library-default"} | N/A |

## Storage Ordering

| Order | Format | Native bytes |
| --- | --- | --- |
| 1 | parquet_zstd19 | 176713 |
| 2 | parquet_gzip | 187083 |
| 3 | parquet_default | 200031 |
| 4 | parquet_snappy | 269320 |

## Fair Operations

| Format | Operation | Fresh p50 ms | Warm p50 ms | Warm p95 ms | IQR ms | Rows | Result hash | RSS bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| parquet_default | exact_match | 3.066 | 1.795 | 5.752 | 1.082 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 142532608 |
| parquet_default | filter_ai_llm | 3.636 | 1.494 | 4.011 | 0.802 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 142647296 |
| parquet_default | filter_repo_stars_gt_100000 | 2.386 | 0.972 | 1.793 | 0.256 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 144187392 |
| parquet_default | head_10 | 2.73 | 1.223 | 2.806 | 0.52 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 141303808 |
| parquet_default | project_two | 1.782 | 0.676 | 3.365 | 0.495 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 123379712 |
| parquet_default | read_all | 2.01 | 0.916 | 1.12 | 0.112 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 137273344 |
| parquet_gzip | exact_match | 2.965 | 1.684 | 2.429 | 0.274 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 143089664 |
| parquet_gzip | filter_ai_llm | 3.149 | 1.737 | 4.713 | 0.418 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 144326656 |
| parquet_gzip | filter_repo_stars_gt_100000 | 2.849 | 1.525 | 1.964 | 0.202 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 143515648 |
| parquet_gzip | head_10 | 3.545 | 1.916 | 4.292 | 0.717 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 141705216 |
| parquet_gzip | project_two | 2.263 | 1.094 | 2.055 | 0.44 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 123125760 |
| parquet_gzip | read_all | 2.697 | 1.873 | 4.837 | 0.704 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 141295616 |
| parquet_snappy | exact_match | 2.174 | 0.839 | 2.479 | 0.235 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 141238272 |
| parquet_snappy | filter_ai_llm | 2.049 | 0.775 | 1.757 | 0.196 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 143745024 |
| parquet_snappy | filter_repo_stars_gt_100000 | 2.692 | 1.467 | 3.825 | 0.772 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 144072704 |
| parquet_snappy | head_10 | 2.335 | 0.99 | 2.416 | 0.496 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 136167424 |
| parquet_snappy | project_two | 1.414 | 0.459 | 0.795 | 0.068 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 122994688 |
| parquet_snappy | read_all | 2.543 | 1.101 | 5.125 | 0.583 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 138838016 |
| parquet_zstd19 | exact_match | 2.588 | 1.15 | 3.864 | 0.593 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 139051008 |
| parquet_zstd19 | filter_ai_llm | 3.243 | 1.626 | 4.687 | 0.951 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 140320768 |
| parquet_zstd19 | filter_repo_stars_gt_100000 | 2.933 | 1.631 | 4.942 | 0.814 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 143695872 |
| parquet_zstd19 | head_10 | 4.006 | 1.865 | 5.55 | 0.94 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 142311424 |
| parquet_zstd19 | project_two | 2.089 | 0.846 | 1.75 | 0.359 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 123215872 |
| parquet_zstd19 | read_all | 2.845 | 1.389 | 3.044 | 0.487 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 140337152 |
