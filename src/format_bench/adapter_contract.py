from typing import Literal, NotRequired, TypeAlias, TypedDict

from .contracts import NormalizedColumn
from .workload_contract import WorkloadDeclarations


class AdapterColumn(TypedDict):
    name: str
    arrow_type: str
    nullable: NotRequired[bool]


AdapterColumns: TypeAlias = list[AdapterColumn] | list[NormalizedColumn]


class AdapterManifest(TypedDict):
    rows: int
    columns: AdapterColumns
    canonical_hash: str
    expected_counts: dict[str, int]
    workloads: NotRequired[WorkloadDeclarations]


class VerificationResult(TypedDict):
    canonical_hash: str
    counts: dict[str, int]
    passed: Literal[True]
