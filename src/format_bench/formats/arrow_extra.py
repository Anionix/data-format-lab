from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.feather as feather
import pyarrow.orc as orc

from format_bench.canonical import arrow_schema, verify_table
from format_bench.fair import Operation, apply_arrow, columns_for
from format_bench.model import Comparability, Lane

from .base import Artifact, FormatDescription, write_artifact


class FeatherV2Adapter:
    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="feather_v2",
            lane=Lane.EQUIVALENCE,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".feather",
            settings={"version": 2, "compression": "uncompressed"},
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        return write_artifact(
            path,
            lambda: feather.write_feather(
                table, path, version=2, compression="uncompressed"
            ),
        )

    def read(self, path: Path, manifest: dict) -> pa.Table:
        return feather.read_table(path).select(arrow_schema(manifest).names)

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return verify_table(self.read(path, manifest), manifest)

    def scan(self, path: Path, manifest: dict, operation: Operation) -> pa.Table:
        return apply_arrow(self.read(path, manifest), operation, manifest)


class OrcAdapter:
    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="orc_zlib",
            lane=Lane.EQUIVALENCE,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".orc",
            settings={
                "compression": "zlib",
                "compression_strategy": "speed",
                "dictionary_key_size_threshold": 0.0,
            },
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        return write_artifact(
            path,
            lambda: orc.write_table(
                table,
                path,
                compression="zlib",
                compression_strategy="speed",
                dictionary_key_size_threshold=0.0,
            ),
        )

    def read(self, path: Path, manifest: dict) -> pa.Table:
        return orc.read_table(path).select(arrow_schema(manifest).names)

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return verify_table(self.read(path, manifest), manifest)

    def scan(self, path: Path, manifest: dict, operation: Operation) -> pa.Table:
        table = orc.read_table(path, columns=columns_for(operation, manifest))
        return apply_arrow(table, operation, manifest)
