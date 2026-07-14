from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.json as pajson

from format_bench.canonical import arrow_schema, read_csv, verify_table
from format_bench.fair import FairOperation, apply_arrow
from format_bench.model import Comparability, Lane

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

    def scan(self, path: Path, manifest: dict, operation: FairOperation) -> pa.Table:
        return apply_arrow(self.read(path, manifest), operation)


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

    def scan(self, path: Path, manifest: dict, operation: FairOperation) -> pa.Table:
        return apply_arrow(self.read(path, manifest), operation)
