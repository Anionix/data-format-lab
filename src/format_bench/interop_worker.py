from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from time import perf_counter_ns

import pyarrow as pa
import pyarrow.ipc as ipc

from .canonical import verify_table


def _schema(table: pa.Table) -> list[dict[str, object]]:
    return [
        {"name": field.name, "type": str(field.type), "nullable": field.nullable}
        for field in table.schema
    ]


def _null_positions(table: pa.Table) -> dict[str, list[int]]:
    return {
        name: [index for index, value in enumerate(table[name].to_pylist()) if value is None]
        for name in table.column_names
    }


def consume(path: Path, manifest: dict) -> dict:
    with pa.memory_map(str(path), "r") as source:
        table = ipc.open_file(source).read_all()
    verification = verify_table(table, manifest)

    started = perf_counter_ns()
    with pa.memory_map(str(path), "r") as source:
        ipc.open_file(source).read_all()
    decoded_ms = (perf_counter_ns() - started) / 1_000_000
    return {
        "status": "PASS",
        "roundtrip_verified": True,
        "consumer": "format_bench.interop_worker",
        "python": platform.python_version(),
        "pyarrow": pa.__version__,
        "decode_ms": round(decoded_ms, 3),
        "rows": table.num_rows,
        "schema": _schema(table),
        "null_positions": _null_positions(table),
        "canonical_hash": verification["canonical_hash"],
        "expected_counts": verification["counts"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = consume(
            args.artifact,
            json.loads(args.manifest.read_text(encoding="utf-8")),
        )
    except Exception as error:
        result = {
            "status": "FAILED",
            "error_type": type(error).__name__,
            "error": str(error)[-500:],
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
