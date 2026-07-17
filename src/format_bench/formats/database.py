from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pyarrow as pa

from format_bench.canonical import arrow_schema, verify_table
from format_bench.fair import FairOperation, columns_for, workload_for
from format_bench.model import Comparability, Lane, WorkloadKind

from .base import Artifact, FormatDescription, write_artifact


_ROW_ID = "__format_bench_row_id"


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sql_type(field: pa.Field) -> str:
    if pa.types.is_boolean(field.type):
        return "BOOLEAN"
    if pa.types.is_integer(field.type):
        return "BIGINT"
    if pa.types.is_floating(field.type):
        return "DOUBLE"
    return "VARCHAR"


def _create_statement(schema: pa.Schema) -> str:
    fields = ", ".join(f"{_quote(field.name)} {_sql_type(field)}" for field in schema)
    return f"CREATE TABLE data ({fields}, {_quote(_ROW_ID)} BIGINT NOT NULL)"


def _rows(table: pa.Table) -> list[tuple[Any, ...]]:
    return [
        tuple(row[field.name] for field in table.schema) + (index,)
        for index, row in enumerate(table.to_pylist())
    ]


def _table_from_rows(
    rows: list[tuple[Any, ...]], manifest: dict, columns: list[str] | None = None
) -> pa.Table:
    full_schema = arrow_schema(manifest)
    schema = (
        full_schema
        if columns is None
        else pa.schema([full_schema.field(name) for name in columns])
    )
    if any(len(row) != len(schema) for row in rows):
        raise ValueError("database row does not match the declared schema width")
    arrays = []
    for index, field in enumerate(schema):
        values = [row[index] for row in rows]
        if pa.types.is_boolean(field.type):
            values = [None if value is None else bool(value) for value in values]
        arrays.append(values)
    return pa.Table.from_arrays(arrays, schema=schema)


def _query_parts(
    manifest: dict, operation: FairOperation
) -> tuple[str, list[Any], list[str]]:
    schema_names = set(arrow_schema(manifest).names)
    spec = workload_for(operation, manifest)
    columns = columns_for(operation, manifest) or list(arrow_schema(manifest).names)
    if any(name not in schema_names for name in columns):
        raise ValueError(f"workload {operation} projects an unknown column")
    projection = ", ".join(_quote(name) for name in columns)
    query = f"SELECT {projection} FROM data"
    parameters: list[Any] = []
    if spec.kind is WorkloadKind.FILTER:
        assert spec.column is not None
        assert spec.operator is not None
        if spec.column not in schema_names:
            raise ValueError(f"workload {operation} filters an unknown column")
        operator = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[spec.operator]
        query += f" WHERE {_quote(spec.column)} {operator} ?"
        parameters.append(spec.value)
    if spec.kind is WorkloadKind.HEAD:
        query += f" ORDER BY {_quote(_ROW_ID)} LIMIT ?"
        parameters.append(spec.limit)
    return query, parameters, columns


class SqliteAdapter:
    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="sqlite_db",
            lane=Lane.ENGINE_CONTAINER,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".sqlite3",
            settings={"engine": "sqlite3", "table": "data", "row_id": _ROW_ID},
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        def write() -> None:
            connection = sqlite3.connect(path)
            try:
                connection.execute(_create_statement(table.schema))
                placeholders = ",".join("?" for _ in range(len(table.schema) + 1))
                connection.executemany(
                    f"INSERT INTO data VALUES ({placeholders})", _rows(table)
                )
                connection.commit()
                connection.execute("VACUUM")
            finally:
                connection.close()

        return write_artifact(path, write)

    def _connect(self, path: Path):
        return sqlite3.connect(path)

    def _fetch(
        self, path: Path, query: str, parameters: list[Any], read_only: bool = True
    ) -> list[tuple[Any, ...]]:
        connection = self._connect(path)
        try:
            return connection.execute(query, parameters).fetchall()
        finally:
            connection.close()

    def read(self, path: Path, manifest: dict) -> pa.Table:
        columns = ", ".join(_quote(name) for name in arrow_schema(manifest).names)
        rows = self._fetch(path, f"SELECT {columns} FROM data ORDER BY {_quote(_ROW_ID)}", [])
        return _table_from_rows(rows, manifest)

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return verify_table(self.read(path, manifest), manifest)

    def scan(self, path: Path, manifest: dict, operation: FairOperation) -> pa.Table:
        query, parameters, columns = _query_parts(manifest, operation)
        return _table_from_rows(self._fetch(path, query, parameters), manifest, columns)


class DuckDbAdapter(SqliteAdapter):
    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="duckdb_db",
            lane=Lane.ENGINE_CONTAINER,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".duckdb",
            settings={"engine": "duckdb", "table": "data", "row_id": _ROW_ID},
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        def write() -> None:
            import duckdb

            connection = duckdb.connect(str(path))
            try:
                connection.register("_format_bench_input", table)
                columns = ", ".join(_quote(field.name) for field in table.schema)
                connection.execute(
                    f"CREATE TABLE data AS SELECT {columns}, "
                    f"row_number() OVER () - 1 AS {_quote(_ROW_ID)} "
                    "FROM _format_bench_input"
                )
            finally:
                connection.unregister("_format_bench_input")
                connection.close()

        return write_artifact(path, write)

    def _connect(self, path: Path):
        import duckdb

        return duckdb.connect(str(path), read_only=True)
