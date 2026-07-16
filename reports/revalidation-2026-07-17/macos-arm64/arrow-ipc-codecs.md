# Data Format Lab: fair report

Dataset: `github-stars-2026-07-03`<br>
Run: `arrow-ipc-codecs-provenance-85ac7de`<br>
No result in this report is comparable across lanes or hardware runs.

## Environment

### Encoding

| Field | Value |
| --- | --- |
| Git commit | 85ac7ded30d7fad473de138a6846abf90a278e56 |
| Flake lock SHA-256 | 1d8b3b85a0f5f144f6076ca7d4de031d1b2c7b50bc62c1bd12d43dd0141ad54c |
| Platform | macOS-27.0-arm64-arm-64bit |
| Machine | arm64 |
| Hardware model | Mac14,7 |
| Python | 3.12.13 |
| Packages | {"pyarrow":"23.0.1","pylance":"8.0.0","tiktoken":"0.12.0","vortex-data":"0.76.0","zstandard":"0.25.0"} |

### Measurement

| Field | Value |
| --- | --- |
| Git commit | 85ac7ded30d7fad473de138a6846abf90a278e56 |
| Flake lock SHA-256 | 1d8b3b85a0f5f144f6076ca7d4de031d1b2c7b50bc62c1bd12d43dd0141ad54c |
| Platform | macOS-27.0-arm64-arm-64bit |
| Machine | arm64 |
| Hardware model | Mac14,7 |
| Python | 3.12.13 |
| Packages | {"pyarrow":"23.0.1","pylance":"8.0.0","tiktoken":"0.12.0","vortex-data":"0.76.0","zstandard":"0.25.0"} |

## Reproducibility

| Field | Value |
| --- | --- |
| Input SHA-256 | 39cc70109d9dddf947257584e15f2f9a6bc97dcdf0a7bf939c26cccbcda0e22e |
| Canonical hash | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 |
| Rows / columns | 2331 / 13 |
| Expected counts | {"full_name_anomalyco_opencode":1,"group_ai_llm":119,"repo_stars_gt_100000":15,"rows":2331} |
| PyArrow | 23.0.1 |
| Packages | {"pyarrow":"23.0.1","pylance":"8.0.0","tiktoken":"0.12.0","vortex-data":"0.76.0","zstandard":"0.25.0"} |
| Protocol | 10 fresh processes; 5 warmups; 30 measurements |
| Seed | 20260703 |
| OS cache purged | False |

### Writer Settings

| Format | Settings |
| --- | --- |
| arrow_ipc | {"compression":"none","container":"arrow-ipc-file"} |
| arrow_ipc_lz4 | {"compression":"lz4","container":"arrow-ipc-file"} |
| arrow_ipc_zstd | {"compression":"zstd","container":"arrow-ipc-file"} |

## Evidence Digests

| File | SHA-256 |
| --- | --- |
| Manifest SHA-256 | 13899f29945117060bcbf8536887f021b8a671e23add7e52e40efa0a85b6c326 |
| Results SHA-256 | 3bc38fcdefbdf6af126e7c8e564aa60cb69e6b3a9d6636448ddb3dfcf5da358b |
| Input manifest SHA-256 | 9c684dac968596d25a95e4731514fa742c81d0a7c01eeb2666c6790473261b8f |
| Input source SHA-256 | 39cc70109d9dddf947257584e15f2f9a6bc97dcdf0a7bf939c26cccbcda0e22e |

Format settings in the Writer Settings table are the writer settings used for each artifact.
The `format-bench package` command includes these raw JSON files and referenced artifacts; it writes the archive SHA-256 to the adjacent `.sha256` file.

## Durable Evidence

| File | URL |
| --- | --- |
| Raw archive | https://github.com/Anionix/data-format-lab/releases/download/v0.1.0/data-format-lab-fair-macos-arm64-arrow-ipc-codecs-provenance-85ac7de.tar.zst |
| SHA-256 checksum | https://github.com/Anionix/data-format-lab/releases/download/v0.1.0/data-format-lab-fair-macos-arm64-arrow-ipc-codecs-provenance-85ac7de.tar.zst.sha256 |

## Format Evidence

| Format | Comparability | State | Native bytes | zstd bytes | Write ms | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| arrow_ipc | FULL_COMPARABLE | REPORTED | 672234 | 190263 | 5.813 | N/A |
| arrow_ipc_lz4 | FULL_COMPARABLE | REPORTED | 327066 | 247469 | 5.564 | N/A |
| arrow_ipc_zstd | FULL_COMPARABLE | REPORTED | 215482 | 215497 | 3.6 | N/A |

## Storage Ordering

| Order | Format | Native bytes |
| --- | --- | --- |
| 1 | arrow_ipc_zstd | 215482 |
| 2 | arrow_ipc_lz4 | 327066 |
| 3 | arrow_ipc | 672234 |

## Fair Operations

| Format | Operation | Fresh p50 ms | Warm p50 ms | Warm p95 ms | IQR ms | Rows | Result hash | RSS bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arrow_ipc | exact_match | 0.857 | 0.189 | 0.487 | 0.137 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 118415360 |
| arrow_ipc | filter_ai_llm | 0.895 | 0.196 | 0.66 | 0.157 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 118554624 |
| arrow_ipc | filter_repo_stars_gt_100000 | 0.648 | 0.156 | 0.23 | 0.025 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 118398976 |
| arrow_ipc | head_10 | 0.527 | 0.139 | 0.88 | 0.153 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 117817344 |
| arrow_ipc | project_two | 0.566 | 0.128 | 0.635 | 0.16 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 117751808 |
| arrow_ipc | read_all | 0.422 | 0.126 | 0.338 | 0.08 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 117760000 |
| arrow_ipc_lz4 | exact_match | 1.279 | 0.456 | 1.509 | 0.173 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 122118144 |
| arrow_ipc_lz4 | filter_ai_llm | 1.494 | 0.532 | 1.487 | 0.232 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 123994112 |
| arrow_ipc_lz4 | filter_repo_stars_gt_100000 | 1.554 | 0.586 | 2.204 | 0.404 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 122306560 |
| arrow_ipc_lz4 | head_10 | 1.013 | 0.379 | 2.109 | 0.236 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 121757696 |
| arrow_ipc_lz4 | project_two | 0.86 | 0.352 | 0.61 | 0.096 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 121511936 |
| arrow_ipc_lz4 | read_all | 1.036 | 0.469 | 4.56 | 0.429 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 122781696 |
| arrow_ipc_zstd | exact_match | 1.275 | 0.504 | 1.001 | 0.101 | 1 | 1aba24aac9a62bb5ccded0f99efba921728e30dc56072ecd5426b367e0b41e74 | 121929728 |
| arrow_ipc_zstd | filter_ai_llm | 1.14 | 0.516 | 0.672 | 0.073 | 119 | 140b166c52a0834c6f114bb8be54af20a4c10531b4a18519545b6453626ed0e8 | 123387904 |
| arrow_ipc_zstd | filter_repo_stars_gt_100000 | 1.429 | 0.637 | 1.561 | 0.26 | 15 | 1f425fafdd5303ea391ac7bc4ba6fac841f4af8df5abb2af953fb3c49e67d342 | 121921536 |
| arrow_ipc_zstd | head_10 | 1.379 | 0.825 | 2.864 | 0.424 | 10 | 4858284487a564997722eb80b383746b88f711001c0e1b5d5b3697d90f132cc6 | 121634816 |
| arrow_ipc_zstd | project_two | 1.044 | 0.568 | 1.351 | 0.235 | 2331 | 9ada00394fcaceead74006de46518c4ae43809bc386cff1880144eb7e5f12ca4 | 121503744 |
| arrow_ipc_zstd | read_all | 1.071 | 0.589 | 2.345 | 0.259 | 2331 | 1bf35022cce6d752f7959907b6a60d4024123e045a270f4aa286acbefbe4ca39 | 121667584 |
