from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa

from format_bench.canonical import arrow_schema, verify_table
from format_bench.fair import FairOperation, apply_arrow
from format_bench.model import Comparability, Lane

from .base import Artifact, FormatDescription, write_artifact


TABLE_NAME = "stars"
TAG_COLUMNS = {"group", "full_name"}


def _types(manifest: dict) -> dict[str, Any]:
    from tsfile import TSDataType

    mapping = {
        "string": TSDataType.STRING,
        "float64": TSDataType.DOUBLE,
        "int64": TSDataType.INT64,
        "bool": TSDataType.BOOLEAN,
    }
    return {column["name"]: mapping[column["arrow_type"]] for column in manifest["columns"]}


class TsFileAdapter:
    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="tsfile",
            lane=Lane.FAIR,
            comparability=Comparability.ADAPTED,
            extension=".tsfile",
            settings={
                "synthetic_timestamp": "row_index",
                "tags": sorted(TAG_COLUMNS),
                "python_install": "tsfile==2.3.1 --no-deps",
            },
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        from tsfile import ColumnCategory, ColumnSchema, TableSchema, Tablet, TsFileTableWriter

        manifest = {
            "columns": [
                {"name": field.name, "arrow_type": _arrow_name(field.type)} for field in table.schema
            ]
        }
        types = _types(manifest)
        names = table.column_names
        schema = TableSchema(
            TABLE_NAME,
            columns=[
                ColumnSchema(
                    name,
                    types[name],
                    ColumnCategory.TAG if name in TAG_COLUMNS else ColumnCategory.FIELD,
                )
                for name in names
            ],
        )

        def write() -> None:
            rows = table.to_pylist()
            tablet = Tablet(names, [types[name] for name in names], len(rows))
            for index, row in enumerate(rows):
                tablet.add_timestamp(index, index)
                for name in names:
                    if row[name] is not None:
                        tablet.add_value_by_name(name, index, row[name])
            with TsFileTableWriter(str(path), schema) as writer:
                writer.write_table(tablet)

        return write_artifact(path, write)

    def read(self, path: Path, manifest: dict) -> pa.Table:
        from tsfile import TsFileReader

        names = [column["name"] for column in manifest["columns"]]
        rows = []
        with TsFileReader(str(path)) as reader:
            with reader.query_table(TABLE_NAME, names, 0, 2**63 - 1) as result:
                while result.next():
                    rows.append(
                        {
                            name: _normalize(name, result.get_value_by_name(name))
                            for name in names
                        }
                    )
        return pa.Table.from_pylist(rows, schema=arrow_schema(manifest))

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return verify_table(self.read(path, manifest), manifest)

    def scan(self, path: Path, manifest: dict, operation: FairOperation) -> pa.Table:
        return apply_arrow(self.read(path, manifest), operation, manifest)


def _arrow_name(data_type: pa.DataType) -> str:
    if pa.types.is_string(data_type):
        return "string"
    if pa.types.is_float64(data_type):
        return "float64"
    if pa.types.is_int64(data_type):
        return "int64"
    if pa.types.is_boolean(data_type):
        return "bool"
    raise TypeError(f"unsupported TsFile Arrow type: {data_type}")


def _normalize(name: str, value: Any) -> Any:
    if value is None:
        return None
    if name in {"classification_score"}:
        return float(value)
    if name in {"repo_stars"}:
        return int(value)
    if name in {"fork", "archived"}:
        return bool(value)
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
