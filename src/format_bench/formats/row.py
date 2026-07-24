from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa

from format_bench.adapter_contract import AdapterManifest
from format_bench.canonical import arrow_schema, verify_table
from format_bench.datasets import normalized_columns
from format_bench.fair import Operation, apply_arrow, workload_for
from format_bench.model import Comparability, Lane, WorkloadKind

from .base import Artifact, FormatDescription, VerificationResult, write_artifact


def _arrow_type_name(data_type: pa.DataType) -> str:
    if pa.types.is_string(data_type):
        return "string"
    if pa.types.is_float64(data_type):
        return "float64"
    if pa.types.is_int64(data_type):
        return "int64"
    if pa.types.is_boolean(data_type):
        return "bool"
    raise ValueError(f"unsupported row serialization Arrow type: {data_type}")


def _columns(schema: pa.Schema) -> list[dict[str, object]]:
    return [
        {
            "name": field.name,
            "arrow_type": _arrow_type_name(field.type),
            "nullable": field.nullable,
        }
        for field in schema
    ]


def _rows_payload(table: pa.Table) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "columns": _columns(table.schema),
        "rows": table.to_pylist(),
    }


def _table_from_payload(payload: Any, manifest: AdapterManifest) -> pa.Table:
    if not isinstance(payload, dict) or payload.get("schema_version") != "1":
        raise ValueError("serialized row payload has an unsupported schema")
    rows = payload.get("rows")
    columns = payload.get("columns")
    if not isinstance(rows, list) or columns != normalized_columns(
        manifest.get("columns")
    ):
        raise ValueError("serialized row payload schema mismatch")
    schema = arrow_schema(manifest)
    expected_names = {field.name for field in schema}
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("serialized row payload contains a non-object row")
    if any(set(row) != expected_names for row in rows):
        raise ValueError("serialized row payload contains missing or extra columns")
    arrays = [[row[field.name] for row in rows] for field in schema]
    return pa.Table.from_arrays(arrays, schema=schema)


def _avro_schema(schema: pa.Schema) -> dict[str, Any]:
    types = {
        "string": "string",
        "float64": "double",
        "int64": "long",
        "bool": "boolean",
    }
    fields = []
    for field in schema:
        field_type = types[_arrow_type_name(field.type)]
        fields.append(
            {"name": field.name, "type": ["null", field_type], "default": None}
        )
    return {"type": "record", "name": "FormatBenchRow", "fields": fields}


class AvroAdapter:
    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="avro_ocf",
            lane=Lane.EQUIVALENCE,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".avro",
            settings={"container": "object-container-file", "codec": "null"},
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        def write() -> None:
            from fastavro import writer

            with path.open("wb") as handle:
                writer(handle, _avro_schema(table.schema), table.to_pylist())

        return write_artifact(path, write)

    def read(self, path: Path, manifest: AdapterManifest) -> pa.Table:
        from fastavro import reader

        with path.open("rb") as handle:
            rows = list(reader(handle))
        payload = {
            "schema_version": "1",
            "columns": normalized_columns(manifest.get("columns")),
            "rows": rows,
        }
        return _table_from_payload(payload, manifest)

    def verify_roundtrip(
        self, path: Path, manifest: AdapterManifest
    ) -> VerificationResult:
        return verify_table(self.read(path, manifest), manifest)

    def scan(
        self, path: Path, manifest: AdapterManifest, operation: Operation
    ) -> pa.Table:
        spec = workload_for(operation, manifest)
        columns = (
            list(spec.columns)
            if spec.kind is WorkloadKind.PROJECTION
            else [column["name"] for column in manifest["columns"]]
        )
        rows: list[dict[str, Any]] = []
        with path.open("rb") as handle:
            from fastavro import reader

            for row in reader(handle):
                if not isinstance(row, dict):
                    raise ValueError("serialized row payload contains a non-object row")
                if spec.kind is WorkloadKind.FILTER:
                    value = row.get(spec.column or "")
                    if value is None:
                        continue
                    matches = {
                        "eq": value == spec.value,
                        "gt": value > spec.value,
                        "gte": value >= spec.value,
                        "lt": value < spec.value,
                        "lte": value <= spec.value,
                    }[spec.operator or "eq"]
                    if not matches:
                        continue
                rows.append({column: row[column] for column in columns})
                if spec.kind is WorkloadKind.HEAD and len(rows) >= spec.limit:
                    break
        if spec.kind is WorkloadKind.PROJECTION:
            schema = arrow_schema(manifest)
            return pa.Table.from_pylist(
                rows, schema=pa.schema([schema.field(column) for column in columns])
            )
        payload = {
            "schema_version": "1",
            "columns": normalized_columns(manifest.get("columns")),
            "rows": rows,
        }
        return _table_from_payload(payload, manifest)


class BinaryRowAdapter:
    def __init__(self, name: str, extension: str) -> None:
        self.name = name
        self.extension = extension

    def describe(self) -> FormatDescription:
        return FormatDescription(
            name=self.name,
            lane=Lane.EQUIVALENCE,
            comparability=Comparability.FULL_COMPARABLE,
            extension=self.extension,
            settings={"shape": "schema-envelope-with-row-list"},
        )

    def _encode(self, payload: dict[str, Any]) -> bytes:
        raise NotImplementedError

    def _decode(self, data: bytes) -> Any:
        raise NotImplementedError

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        def write() -> None:
            path.write_bytes(self._encode(_rows_payload(table)))

        return write_artifact(path, write)

    def read(self, path: Path, manifest: AdapterManifest) -> pa.Table:
        return _table_from_payload(self._decode(path.read_bytes()), manifest)

    def verify_roundtrip(
        self, path: Path, manifest: AdapterManifest
    ) -> VerificationResult:
        return verify_table(self.read(path, manifest), manifest)

    def scan(
        self, path: Path, manifest: AdapterManifest, operation: Operation
    ) -> pa.Table:
        return apply_arrow(self.read(path, manifest), operation, manifest)


class MessagePackAdapter(BinaryRowAdapter):
    def __init__(self) -> None:
        super().__init__("msgpack_rows", ".msgpack")

    def _encode(self, payload: dict[str, Any]) -> bytes:
        import msgpack

        return msgpack.packb(payload, use_bin_type=True)

    def _decode(self, data: bytes) -> Any:
        import msgpack

        return msgpack.unpackb(data, raw=False)


class CborAdapter(BinaryRowAdapter):
    def __init__(self) -> None:
        super().__init__("cbor_rows", ".cbor")

    def _encode(self, payload: dict[str, Any]) -> bytes:
        import cbor2

        return cbor2.dumps(payload)

    def _decode(self, data: bytes) -> Any:
        import cbor2

        return cbor2.loads(data)
