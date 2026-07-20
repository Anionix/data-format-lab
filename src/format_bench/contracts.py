from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict


_SUPPORTED_ARROW_TYPES = frozenset({"string", "float64", "int64", "bool"})


class NormalizedColumn(TypedDict):
    name: str
    arrow_type: str
    nullable: bool


def normalized_columns(value: object) -> list[NormalizedColumn]:
    if not isinstance(value, list) or not value:
        raise ValueError("manifest columns must be a non-empty list")
    names: set[str] = set()
    normalized: list[NormalizedColumn] = []
    for index, column in enumerate(value):
        path = f"manifest columns[{index}]"
        if not isinstance(column, Mapping):
            raise ValueError(f"{path} must be an object")
        if not all(isinstance(key, str) and key for key in column):
            raise ValueError(f"{path} keys must be non-empty strings")
        name = column.get("name")
        arrow_type = column.get("arrow_type")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path}.name must be a non-empty string")
        if name in names:
            raise ValueError(f"duplicate manifest column: {name}")
        if not isinstance(arrow_type, str) or arrow_type not in _SUPPORTED_ARROW_TYPES:
            raise ValueError(f"unsupported arrow type for column {name}")
        nullable = column.get("nullable", True)
        if not isinstance(nullable, bool):
            raise ValueError(f"{path}.nullable must be a boolean")
        names.add(name)
        normalized.append(
            NormalizedColumn(name=name, arrow_type=arrow_type, nullable=nullable)
        )
    return normalized


def normalized_workload_entry(
    operation: object, payload: object
) -> tuple[str, dict[str, object]]:
    if not isinstance(operation, str) or not operation.strip():
        raise ValueError("workload names must be non-empty strings")
    if not isinstance(payload, Mapping) or not all(
        isinstance(key, str) for key in payload
    ):
        raise ValueError(f"workload {operation} must be an object with string keys")
    return operation, {str(key): item for key, item in payload.items()}
