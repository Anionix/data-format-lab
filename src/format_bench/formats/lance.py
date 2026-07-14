from __future__ import annotations

import io
import shutil
import tarfile
import time
from pathlib import Path

import lance
import pyarrow as pa
import zstandard as zstd

from format_bench.canonical import arrow_schema, verify_table
from format_bench.fair import FairOperation, columns_for, lance_filter, limit_for
from format_bench.model import Comparability, Lane
from format_bench.runner import stats_ms

from .base import Artifact, FormatDescription


def _logical_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _transport_size(path: Path) -> int:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for item in sorted(path.rglob("*")):
            if not item.is_file():
                continue
            data = item.read_bytes()
            info = tarfile.TarInfo(str(item.relative_to(path)))
            info.size = len(data)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(data))
    return len(zstd.ZstdCompressor(level=3).compress(buffer.getvalue()))


def lance_components(path: Path) -> dict[str, int]:
    logical = _logical_size(path)
    data = _logical_size(path / "data")
    index = _logical_size(path / "_indices")
    return {
        "data_body_bytes": data,
        "index_bytes": index,
        "metadata_bytes": logical - data - index,
        "logical_directory_bytes": logical,
    }


def _write_lance(table: pa.Table, path: Path) -> Artifact:
    if path.exists():
        shutil.rmtree(path)
    started = time.perf_counter_ns()
    lance.write_dataset(table, path, mode="overwrite", data_storage_version="stable")
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    return Artifact(path, _logical_size(path), _transport_size(path), round(elapsed_ms, 3))


class LanceAdapter:
    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="lance_base",
            lane=Lane.FAIR,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".lance",
            settings={"index": None, "data_storage_version": "stable"},
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        return _write_lance(table, path)

    def read(self, path: Path, manifest: dict) -> pa.Table:
        schema = arrow_schema(manifest)
        return lance.dataset(path).to_table(columns=schema.names).cast(schema)

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return verify_table(self.read(path, manifest), manifest)

    def scan(self, path: Path, manifest: dict, operation: FairOperation) -> pa.Table:
        return lance.dataset(path).to_table(
            columns=columns_for(operation),
            filter=lance_filter(operation),
            limit=limit_for(operation, manifest["rows"]),
        )


def _search_table(table: pa.Table) -> pa.Table:
    rows = table.to_pylist()
    text = [
        " ".join(str(row.get(name) or "") for name in ("full_name", "description", "topics", "matched_terms"))
        for row in rows
    ]
    return table.append_column("search_text", pa.array(text, pa.string()))


def build_fts(table: pa.Table, path: Path) -> dict:
    artifact = _write_lance(_search_table(table), path)
    before = lance_components(path)
    dataset = lance.dataset(path)
    started = time.perf_counter_ns()
    dataset.create_scalar_index("search_text", "INVERTED", replace=True)
    index_build_ms = (time.perf_counter_ns() - started) / 1_000_000
    components = lance_components(path)
    return {
        "artifact": Artifact(
            path,
            components["logical_directory_bytes"],
            _transport_size(path),
            artifact.prepare_write_ms,
        ),
        "data_bytes_before_index": before["logical_directory_bytes"],
        "index_build_ms": round(index_build_ms, 3),
        **components,
    }


def query_fts(path: Path, table: pa.Table, query: str, *, warmups: int = 5, iterations: int = 30) -> dict:
    dataset = lance.dataset(path)

    def invoke() -> list[str]:
        result = dataset.to_table(columns=["full_name"], full_text_query=query, limit=20)
        return result["full_name"].to_pylist()

    for _ in range(warmups):
        invoke()
    samples, names = [], []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        names = invoke()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    corpus = {
        row["full_name"]: " ".join(
            str(row.get(name) or "") for name in ("full_name", "description", "topics", "matched_terms")
        ).casefold()
        for row in table.to_pylist()
    }
    truth = {name for name, text in corpus.items() if query.casefold() in text}
    hits = [name for name in names if name in truth]
    return {
        "timing": stats_ms(samples),
        "returned": len(names),
        "ground_truth_substring_rows": len(truth),
        "precision_at_20": round(len(hits) / len(names), 4) if names else None,
        "recall_at_20": round(len(hits) / len(truth), 4) if truth else None,
        "top_results": names[:10],
    }
