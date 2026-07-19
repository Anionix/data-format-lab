from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.json as pajson

from format_bench.canonical import arrow_schema, read_csv, verify_table
from format_bench.fair import Operation, apply_arrow, workload_for
from format_bench.model import Comparability, Lane, WorkloadKind

from .base import Artifact, FormatDescription, write_artifact


class CsvAdapter:
    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="csv",
            lane=Lane.FAIR,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".csv",
            settings={"encoding": "utf-8", "typed": False},
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        return write_artifact(path, lambda: pacsv.write_csv(table, path))

    def read(self, path: Path, manifest: dict) -> pa.Table:
        return read_csv(path, manifest)

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return verify_table(self.read(path, manifest), manifest)

    def scan(self, path: Path, manifest: dict, operation: Operation) -> pa.Table:
        return apply_arrow(self.read(path, manifest), operation, manifest)


class TsvAdapter:
    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="tsv",
            lane=Lane.EQUIVALENCE,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".tsv",
            settings={"encoding": "utf-8", "delimiter": "\\t", "typed": False},
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        options = pacsv.WriteOptions(delimiter="\t")
        return write_artifact(
            path, lambda: pacsv.write_csv(table, path, write_options=options)
        )

    def read(self, path: Path, manifest: dict) -> pa.Table:
        schema = arrow_schema(manifest)
        options = pacsv.ConvertOptions(
            column_types={field.name: field.type for field in schema},
            null_values=[""],
            strings_can_be_null=True,
        )
        return pacsv.read_csv(
            path,
            parse_options=pacsv.ParseOptions(delimiter="\t"),
            convert_options=options,
        ).select(schema.names)

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return verify_table(self.read(path, manifest), manifest)

    def scan(self, path: Path, manifest: dict, operation: Operation) -> pa.Table:
        return apply_arrow(self.read(path, manifest), operation, manifest)


class ObjectJsonlAdapter:
    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="object_jsonl",
            lane=Lane.FAIR,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".jsonl",
            settings={"encoding": "utf-8", "shape": "object-per-line"},
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        def write() -> None:
            with path.open("w", encoding="utf-8") as handle:
                for row in table.to_pylist():
                    handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

        return write_artifact(path, write)

    def read(self, path: Path, manifest: dict) -> pa.Table:
        options = pajson.ParseOptions(explicit_schema=arrow_schema(manifest))
        return pajson.read_json(path, parse_options=options).select(arrow_schema(manifest).names)

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return verify_table(self.read(path, manifest), manifest)

    def scan(self, path: Path, manifest: dict, operation: Operation) -> pa.Table:
        spec = workload_for(operation, manifest)
        if spec.kind is WorkloadKind.READ_ALL:
            return self.read(path, manifest)
        schema = arrow_schema(manifest)
        batches: list[pa.Table] = []
        row_limit = spec.limit if spec.kind is WorkloadKind.HEAD else None
        reader = pajson.open_json(
            path,
            parse_options=pajson.ParseOptions(explicit_schema=schema),
        )
        rows_seen = 0
        for batch in reader:
            current = pa.Table.from_batches([batch]).select(schema.names)
            selected = apply_arrow(current, operation, manifest)
            if row_limit is not None:
                remaining = row_limit - rows_seen
                selected = selected.slice(0, remaining)
            if selected.num_rows:
                batches.append(selected)
                rows_seen += selected.num_rows
            if row_limit is not None and rows_seen >= row_limit:
                break
        if not batches:
            empty = pa.Table.from_arrays(
                [pa.array([], type=field.type) for field in schema], schema=schema
            )
            return empty.select(
                list(spec.columns) if spec.kind is WorkloadKind.PROJECTION else schema.names
            )
        return pa.concat_tables(batches, promote_options="default")
