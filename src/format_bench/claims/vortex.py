from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Callable

import pyarrow as pa
import pyarrow.parquet as pq
import vortex
import vortex.expr as ve

from format_bench.runner import stats_ms


ROW_GROUP_SIZE = 4096
PROJECTION = ["full_name", "repo_stars"]


def _measure(function: Callable[[], int], warmups: int, iterations: int) -> dict:
    for _ in range(warmups):
        function()
    samples, result = [], 0
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = function()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return {"timing": stats_ms(samples), "result": result}


def _parquet_random_take(path: Path, indices: list[int]) -> int:
    parquet = pq.ParquetFile(path)
    groups = sorted({index // ROW_GROUP_SIZE for index in indices})
    table = parquet.read_row_groups(groups, columns=PROJECTION)
    offsets, offset = {}, 0
    for group in groups:
        offsets[group] = offset
        offset += parquet.metadata.row_group(group).num_rows
    local = [offsets[index // ROW_GROUP_SIZE] + index % ROW_GROUP_SIZE for index in indices]
    return table.take(pa.array(local, type=pa.int64())).num_rows


def _write_compact(table: pa.Table, path: Path) -> None:
    batches = table.to_batches(max_chunksize=ROW_GROUP_SIZE)
    reader = pa.RecordBatchReader.from_batches(table.schema, batches)
    vortex.io.VortexWriteOptions.compact().write(reader, str(path))


def _vortex_scan(
    path: Path,
    *,
    expr=None,
    indices=None,
) -> int:
    source = vortex.open(str(path))
    return (
        source.scan(PROJECTION, expr=expr, indices=indices)
        .read_all()
        .to_arrow_table()
        .num_rows
    )


def _variant(
    name: str, table: pa.Table, directory: Path, warmups: int, iterations: int, seed: int
) -> dict:
    parquet_path, vortex_path = directory / f"{name}.parquet", directory / f"{name}.vortex"
    started = time.perf_counter_ns()
    pq.write_table(
        table, parquet_path, compression="zstd", use_dictionary=True, row_group_size=ROW_GROUP_SIZE
    )
    parquet_write_ms = (time.perf_counter_ns() - started) / 1_000_000
    started = time.perf_counter_ns()
    _write_compact(table, vortex_path)
    vortex_write_ms = (time.perf_counter_ns() - started) / 1_000_000
    sample_size = min(1000, table.num_rows)
    indices = sorted(random.Random(seed).sample(range(table.num_rows), sample_size))
    vortex_indices = vortex.array(pa.array(indices, type=pa.uint64()))
    operations = {
        "full_projection": (
            lambda: pq.read_table(parquet_path, columns=PROJECTION).num_rows,
            lambda: _vortex_scan(vortex_path),
        ),
        "filter_popular": (
            lambda: pq.read_table(
                parquet_path, columns=PROJECTION, filters=[("repo_stars", ">", 100000)]
            ).num_rows,
            lambda: _vortex_scan(
                vortex_path, expr=ve.column("repo_stars") > 100000
            ),
        ),
        "filter_none": (
            lambda: pq.read_table(
                parquet_path, columns=PROJECTION, filters=[("repo_stars", ">", 99_999_999)]
            ).num_rows,
            lambda: _vortex_scan(
                vortex_path, expr=ve.column("repo_stars") > 99_999_999
            ),
        ),
        "random_1000": (
            lambda: _parquet_random_take(parquet_path, indices),
            lambda: _vortex_scan(vortex_path, indices=vortex_indices),
        ),
    }
    measured = {}
    for operation, (parquet_fn, vortex_fn) in operations.items():
        parquet_result = _measure(parquet_fn, warmups, iterations)
        vortex_result = _measure(vortex_fn, warmups, iterations)
        if parquet_result["result"] != vortex_result["result"]:
            raise ValueError(f"stress result mismatch for {name}/{operation}")
        measured[operation] = {"parquet": parquet_result, "vortex": vortex_result}
    return {
        "rows": table.num_rows,
        "row_group_or_batch_rows": ROW_GROUP_SIZE,
        "parquet": {"bytes": parquet_path.stat().st_size, "write_ms": round(parquet_write_ms, 3)},
        "vortex": {"bytes": vortex_path.stat().st_size, "write_ms": round(vortex_write_ms, 3)},
        "operations": measured,
    }


def run_vortex_stress(
    base: pa.Table,
    directory: Path,
    *,
    rows: int = 466_200,
    warmups: int = 5,
    iterations: int = 30,
    seed: int = 20260703,
) -> dict:
    if rows % base.num_rows:
        raise ValueError("stress rows must be a multiple of the base table")
    directory.mkdir(parents=True, exist_ok=True)
    expanded = pa.concat_tables([base] * (rows // base.num_rows)).append_column(
        "benchmark_row_id", pa.array(range(rows), type=pa.int64())
    )
    sorted_table = expanded.sort_by([("repo_stars", "ascending"), ("benchmark_row_id", "ascending")])
    permutation = list(range(rows))
    random.Random(seed).shuffle(permutation)
    unsorted = expanded.take(pa.array(permutation, type=pa.int64()))
    return {
        "contract": "same rows; synthetic benchmark_row_id; claim lane only",
        "sorted": _variant("sorted", sorted_table, directory, warmups, iterations, seed),
        "unsorted": _variant("unsorted", unsorted, directory, warmups, iterations, seed),
    }
