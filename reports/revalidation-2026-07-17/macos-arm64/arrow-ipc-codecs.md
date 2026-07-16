# Data Format Lab: fair report

Dataset: `github-stars-2026-07-03`  
Run: `data-format-lab-arrow-ipc-codecs-1784235449`  
No result in this report is comparable across lanes or hardware runs.

## Environment

| Field | Value |
| --- | --- |
| Git commit | 949417edf235e350d5c054331101ad89a7a8993a |
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
| Manifest SHA-256 | 27f436ccf01ab1def18ad1f59bf1ec96414e2fbf0c4ba057f402ce506eda54f8 |
| Results SHA-256 | 334b888b2a4ff1994cc4b3081362528109cc162ee225795740eac981ea4144c9 |
| Input manifest SHA-256 | 9c684dac968596d25a95e4731514fa742c81d0a7c01eeb2666c6790473261b8f |
| Input source SHA-256 | 39cc70109d9dddf947257584e15f2f9a6bc97dcdf0a7bf939c26cccbcda0e22e |

Format settings in the Format Evidence table are the writer settings used for each artifact.
The `format-bench package` command includes these raw JSON files and referenced artifacts; it writes the archive SHA-256 to the adjacent `.sha256` file.

## Durable Evidence

| File | URL |
| --- | --- |
| Raw archive | https://github.com/Anionix/data-format-lab/releases/download/v0.1.0/data-format-lab-fair-macos-arm64-data-format-lab-arrow-ipc-codecs-1784235449.tar.zst |
| SHA-256 checksum | https://github.com/Anionix/data-format-lab/releases/download/v0.1.0/data-format-lab-fair-macos-arm64-data-format-lab-arrow-ipc-codecs-1784235449.tar.zst.sha256 |

## Format Evidence

| Format | Comparability | State | Native bytes | zstd bytes | Write ms | Settings | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| arrow_ipc | FULL_COMPARABLE | REPORTED | 672234 | 190263 | 3.035 | {"compression":"none","container":"arrow-ipc-file"} | N/A |
| arrow_ipc_lz4 | FULL_COMPARABLE | REPORTED | 327066 | 247469 | 2.549 | {"compression":"lz4","container":"arrow-ipc-file"} | N/A |
| arrow_ipc_zstd | FULL_COMPARABLE | REPORTED | 215482 | 215497 | 2.496 | {"compression":"zstd","container":"arrow-ipc-file"} | N/A |

## Storage Ordering

| Order | Format | Native bytes |
| --- | --- | --- |
| 1 | arrow_ipc_zstd | 215482 |
| 2 | arrow_ipc_lz4 | 327066 |
| 3 | arrow_ipc | 672234 |

## Fair Operations

| Format | Operation | Fresh p50 ms | Warm p50 ms | Warm p95 ms | IQR ms | Rows | Result hash | RSS bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arrow_ipc | exact_match | 0.648 | 0.162 | 0.376 | 0.031 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 118726656 |
| arrow_ipc | filter_ai_llm | 0.68 | 0.167 | 0.285 | 0.033 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 118898688 |
| arrow_ipc | filter_repo_stars_gt_100000 | 0.708 | 0.154 | 0.247 | 0.027 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 118841344 |
| arrow_ipc | head_10 | 0.439 | 0.107 | 0.213 | 0.034 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 118038528 |
| arrow_ipc | project_two | 0.469 | 0.111 | 0.184 | 0.018 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 118038528 |
| arrow_ipc | read_all | 0.576 | 0.13 | 0.801 | 0.117 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 118054912 |
| arrow_ipc_lz4 | exact_match | 1.09 | 0.327 | 1.63 | 0.1 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 122855424 |
| arrow_ipc_lz4 | filter_ai_llm | 1.054 | 0.356 | 0.786 | 0.095 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 124370944 |
| arrow_ipc_lz4 | filter_repo_stars_gt_100000 | 0.984 | 0.315 | 0.612 | 0.073 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 122929152 |
| arrow_ipc_lz4 | head_10 | 0.793 | 0.287 | 0.58 | 0.115 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 122249216 |
| arrow_ipc_lz4 | project_two | 1.038 | 0.363 | 1.407 | 0.366 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 122503168 |
| arrow_ipc_lz4 | read_all | 0.799 | 0.285 | 1.155 | 0.121 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 122617856 |
| arrow_ipc_zstd | exact_match | 1.264 | 0.489 | 1.269 | 0.182 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 110477312 |
| arrow_ipc_zstd | filter_ai_llm | 1.16 | 0.467 | 1.55 | 0.12 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 124157952 |
| arrow_ipc_zstd | filter_repo_stars_gt_100000 | 1.107 | 0.448 | 0.723 | 0.074 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 122650624 |
| arrow_ipc_zstd | head_10 | 0.942 | 0.393 | 0.54 | 0.05 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 122290176 |
| arrow_ipc_zstd | project_two | 0.918 | 0.416 | 1.491 | 0.131 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 122994688 |
| arrow_ipc_zstd | read_all | 0.909 | 0.391 | 0.537 | 0.05 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 123412480 |
