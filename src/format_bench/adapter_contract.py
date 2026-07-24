from typing import Literal, NotRequired, TypedDict

from .contracts import NormalizedColumn


class AdapterManifest(TypedDict):
    rows: int
    columns: list[NormalizedColumn]
    canonical_hash: str
    expected_counts: dict[str, int]
    workloads: NotRequired[dict[str, object]]


class VerificationResult(TypedDict):
    canonical_hash: str
    counts: dict[str, int]
    passed: Literal[True]
