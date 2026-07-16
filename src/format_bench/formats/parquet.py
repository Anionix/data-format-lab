from __future__ import annotations

from pathlib import Path
from typing import Literal

import pyarrow as pa
import pyarrow.parquet as pq

from format_bench.canonical import arrow_schema, verify_table
from format_bench.fair import FairOperation, arrow_filter, columns_for, limit_for
from format_bench.model import Comparability, Lane

from .base import Artifact, FormatDescription, write_artifact

ParquetCompression = Literal["snappy", "gzip", "zstd"]


class ParquetAdapter:
    def __init__(
        self,
        compression_level: int | None = None,
        *,
        compression: ParquetCompression = "zstd",
    ) -> None:
        if compression not in {"snappy", "gzip", "zstd"}:
            raise ValueError(f"unsupported Parquet compression: {compression}")
        self.compression_level = compression_level
        self.compression = compression

    def describe(self) -> FormatDescription:
        level = self.compression_level
        if self.compression == "snappy":
            name = "parquet_snappy"
        elif self.compression == "gzip":
            name = "parquet_gzip"
        else:
            name = "parquet_zstd19" if level == 19 else "parquet_default"
        return FormatDescription(
            name=name,
            lane=Lane.FAIR,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".parquet",
            settings={
                "compression": self.compression,
                "level": level if level is not None else "library-default",
                "dictionary": True,
            },
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        def write() -> None:
            pq.write_table(
                table,
                path,
                compression=self.compression,
                compression_level=self.compression_level,
                use_dictionary=True,
            )

        return write_artifact(path, write)

    def read(self, path: Path, manifest: dict) -> pa.Table:
        schema = arrow_schema(manifest)
        return pq.read_table(path, schema=schema).select(schema.names)

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return verify_table(self.read(path, manifest), manifest)

    def scan(self, path: Path, manifest: dict, operation: FairOperation) -> pa.Table:
        table = pq.read_table(
            path,
            columns=columns_for(operation),
            filters=arrow_filter(operation),
        )
        limit = limit_for(operation, manifest["rows"])
        return table.slice(0, limit) if limit is not None else table
