# Data Format Lab: claims report

Dataset: `github-stars-2026-07-03`  
Run: `v0.1.0-macos-arm64-claims-tsfile-1`  
No result in this report is comparable across lanes or hardware runs.

## Environment

| Field | Value |
| --- | --- |
| Git commit | 6561a60b595e881df73744a321084ef86b3d0ea5 |
| Flake lock SHA-256 | 5349aa3b52f8c844a7115a25f5b1a2bbd6a7b37847d763a5b5e2c6153357034b |
| Platform | macOS-27.0-arm64-arm-64bit |
| Machine | arm64 |
| Python | 3.12.13 |

## Claim Evidence

Claims use workload-specific contracts and are not a universal format ranking.

| Claim | Comparability | State | Failure or last result |
| --- | --- | --- | --- |
| lance_fts | FULL_COMPARABLE | BENCHMARKED | N/A |
| anyblox | PARTIAL | FAILED | vendored Vortex code required unversioned nightly Rust features; stable Rust failed with E0554/E0599 |
| fastlanes | PARTIAL | FAILED | process exited -11 |
| nimble | UNAVAILABLE | UNSUPPORTED | CMake generation could not resolve protobuf::libprotobuf and fmt::fmt in sibling Nimble directories |
| tsfile_time_series | FULL_COMPARABLE | BENCHMARKED | N/A |
| vortex_stress | FULL_COMPARABLE | BENCHMARKED | N/A |
