from typing import Literal, NotRequired, TypeAlias, TypeGuard, TypedDict


ComparisonOperator: TypeAlias = Literal["eq", "gt", "gte", "lt", "lte"]
WorkloadScalar: TypeAlias = str | int | float | bool
_COMPARISON_OPERATORS = frozenset({"eq", "gt", "gte", "lt", "lte"})


def is_comparison_operator(value: object) -> TypeGuard[ComparisonOperator]:
    return isinstance(value, str) and value in _COMPARISON_OPERATORS


class ReadAllWorkload(TypedDict):
    kind: Literal["read_all"]
    expected_rows: NotRequired[int]


class ProjectionWorkload(TypedDict):
    kind: Literal["projection"]
    columns: list[str]
    expected_rows: NotRequired[int]


class FilterWorkload(TypedDict):
    kind: Literal["filter"]
    column: str
    operator: ComparisonOperator
    value: WorkloadScalar
    expected_rows: NotRequired[int]


class HeadWorkload(TypedDict):
    kind: Literal["head"]
    limit: int
    expected_rows: NotRequired[int]


WorkloadDeclaration: TypeAlias = (
    ReadAllWorkload | ProjectionWorkload | FilterWorkload | HeadWorkload
)
WorkloadDeclarations: TypeAlias = dict[str, WorkloadDeclaration]
