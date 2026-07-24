from typing import Literal, NotRequired, TypedDict


class AdapterColumn(TypedDict):
    name: str
    arrow_type: str
    nullable: NotRequired[bool]


class AdapterManifest(TypedDict):
    rows: int
    columns: list[AdapterColumn]
    canonical_hash: str
    expected_counts: dict[str, int]
    workloads: NotRequired[dict[str, object]]


class VerificationResult(TypedDict):
    canonical_hash: str
    counts: dict[str, int]
    passed: Literal[True]
