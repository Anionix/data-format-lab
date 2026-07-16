from __future__ import annotations

import argparse
import json
from pathlib import Path


MIXED_COLUMNS = (
    {"name": "group", "type": "string", "nullability": "NULL"},
    {"name": "category", "type": "string", "nullability": "NULL"},
    {"name": "micro_category", "type": "string", "nullability": "NULL"},
    {"name": "classification_score", "type": "double", "nullability": "NULL"},
    {"name": "matched_terms", "type": "string", "nullability": "NULL"},
    {"name": "full_name", "type": "string", "nullability": "NULL"},
    {"name": "html_url", "type": "string", "nullability": "NULL"},
    {"name": "language", "type": "string", "nullability": "NULL"},
    {"name": "repo_stars", "type": "bigint", "nullability": "NULL"},
    {"name": "fork", "type": "boolean", "nullability": "NULL"},
    {"name": "archived", "type": "boolean", "nullability": "NULL"},
    {"name": "topics", "type": "string", "nullability": "NULL"},
    {"name": "description", "type": "string", "nullability": "NULL"},
)


def _input(directory: Path, case: str, rows: int) -> tuple[Path, Path, bytes]:
    directory.mkdir(parents=True, exist_ok=True)
    if case == "numeric":
        columns = [
            {"name": f"col{index}", "type": "integer", "nullability": "NULL"}
            for index in range(8)
        ]
        lines = ("|".join(str(row + index) for index in range(8)) for row in range(rows))
    elif case == "string":
        columns = [{"name": "value", "type": "string", "nullability": "NULL"}]
        lines = (f"value-{row}" for row in range(rows))
    elif case == "comma":
        columns = [
            {"name": f"col{index}", "type": "integer", "nullability": "NULL"}
            for index in range(8)
        ]
        lines = (",".join(str(row + index) for index in range(8)) for row in range(rows))
    elif case == "mixed":
        columns = list(MIXED_COLUMNS)
        lines = (
            "|".join(
                (
                    "AI / LLM" if row % 2 == 0 else "Databases",
                    f"category-{row % 3}",
                    f"micro-{row % 5}",
                    f"{(row % 100) / 100:.2f}",
                    f"term-{row % 7};term-{(row + 1) % 7}",
                    f"owner/repo-{row}",
                    f"https://github.com/owner/repo-{row}",
                    "Python" if row % 2 == 0 else "Rust",
                    str(row * 17),
                    "true" if row % 2 == 0 else "false",
                    "false" if row % 11 else "true",
                    f"topic-{row % 4};topic-{(row + 1) % 4}",
                    f"Repository description {row}",
                )
            )
            for row in range(rows)
        )
    else:
        raise ValueError(f"unknown FastLanes case: {case}")
    schema = directory / "schema.json"
    csv_path = directory / "data.csv"
    schema.write_text(json.dumps({"columns": columns}, sort_keys=True), encoding="utf-8")
    data = ("\n".join(lines) + "\n").encode("utf-8")
    csv_path.write_bytes(data)
    return schema, csv_path, data


def run(case: str, rows: int, output: Path) -> dict:
    import pyfastlanes

    _, csv_path, source = _input(output / "input", case, rows)
    fls_path = output / "data.fls"
    decoded_path = output / "decoded.csv"
    pyfastlanes.connect().read_csv(str(csv_path.parent)).to_fls(str(fls_path))
    pyfastlanes.connect().read_fls(str(fls_path)).to_csv(str(decoded_path))
    decoded = decoded_path.read_bytes()
    if decoded != source:
        raise ValueError(f"decoded bytes differ: {len(source)} != {len(decoded)}")
    return {
        "outcome": "ROUNDTRIP_EQUAL",
        "source_bytes": len(source),
        "artifact_bytes": fls_path.stat().st_size,
        "decoded_bytes": len(decoded),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("numeric", "string", "mixed", "comma"), required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.case, args.rows, args.output)
    except Exception as error:
        result = {"status": "FAILED", "error_type": type(error).__name__, "error": str(error)[-500:]}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
