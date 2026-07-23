from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".data" / "revalidation-20260719"
PAIRS = (
    "csv-tsv",
    "arrow-feather",
    "parquet-orc",
    "jsonl-avro",
    "jsonl-msgpack-cbor",
    "sqlite-duckdb",
)
DATASETS = (
    "github-stars-2026-07-03",
    "uci-online-retail-ii",
    "uci-bank-marketing",
    "nyc-311-2010-2019",
    "owid-energy",
    "geonames-cities500",
)
COMPLETE_PAIR_VERDICTS = {
    "PRACTICALLY_EQUIVALENT",
    "MEANINGFUL_DIFFERENCE",
    "INCONCLUSIVE",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def source_identity(dataset_id: str) -> dict:
    manifest = load(ROOT / "datasets" / dataset_id / "manifest.json")
    return {
        "dataset_manifest": {
            "path": f"datasets/{dataset_id}/manifest.json",
            "sha256": sha256(ROOT / "datasets" / dataset_id / "manifest.json"),
        },
        "source": {
            "rows": manifest.get("rows"),
            "columns": len(manifest.get("columns", [])),
            "source_sha256": manifest.get("source_sha256"),
            "canonical_hash": manifest.get("canonical_hash"),
            "compressed_asset": manifest.get("asset"),
        },
    }


def pilot_contract(dataset_id: str) -> dict:
    name = {
        "github-stars-2026-07-03": "github",
        "uci-online-retail-ii": "retail",
        "uci-bank-marketing": "bank",
        "nyc-311-2010-2019": "nyc",
        "owid-energy": "owid",
        "geonames-cities500": "geonames",
    }[dataset_id]
    records = []
    for attempt in (1, 2):
        path = OUTPUT / "pilot-contract" / name / f"attempt-{attempt}.json"
        if path.is_file():
            records.append(
                {
                    "path": path.relative_to(OUTPUT).as_posix(),
                    "sha256": sha256(path),
                    "evidence": load(path),
                }
            )
    return {"attempts": records, "complete": len(records) == 2}


def candidates(dataset_id: str, pair: str) -> list[Path]:
    if dataset_id == "github-stars-2026-07-03":
        return [ROOT / "runs" / "full-20260718-github-parallel-4"]
    if dataset_id == "uci-bank-marketing":
        return [ROOT / "runs" / "full-20260718-bank-parallel-8"]
    if dataset_id == "owid-energy":
        return [ROOT / "runs" / "full-20260718-owid-parallel-4"]
    if dataset_id == "nyc-311-2010-2019":
        return [ROOT / "runs" / "full-20260719-nyc-shards" / pair]
    if dataset_id == "geonames-cities500" and pair in {
        "jsonl-avro",
        "jsonl-msgpack-cbor",
    }:
        # The JSON pairs share object_jsonl. Reuse the completed matrix run so
        # the shared reference format is measured once.
        matrix = (
            ROOT / "runs" / "full-20260718-geonames-current-shards-v3" / "jsonl-avro"
        )
        return [matrix]
    if dataset_id == "geonames-cities500":
        return [ROOT / "runs" / "full-20260718-geonames-current-shards-v3" / pair]
    if dataset_id == "uci-online-retail-ii":
        # The two JSON pairs share object_jsonl. Prefer one matrix run so the
        # shared reference format is measured once and reused for both pairs.
        if pair in {"jsonl-avro", "jsonl-msgpack-cbor"}:
            matrix = (
                ROOT / "runs" / "full-20260718-retail-current-shards" / "jsonl-avro"
            )
            return [matrix]
        current = ROOT / "runs" / "full-20260718-retail-current-shards" / pair
        legacy = {
            "csv-tsv": ROOT / "runs" / "full-20260718-retail-final-4-20260718",
            "arrow-feather": ROOT
            / "runs"
            / "full-20260718-retail-final-4-20260718-shards"
            / pair,
            "parquet-orc": ROOT
            / "runs"
            / "full-20260718-retail-final-4-20260718-shards"
            / pair,
            "sqlite-duckdb": ROOT
            / "runs"
            / "full-20260718-retail-final-4-20260718-shards"
            / pair,
        }
        return [current, legacy.get(pair, current)]
    return []


def pair_record(results: dict, pair: str) -> dict | None:
    record = results.get("equivalence", {}).get("pairs", {}).get(pair)
    return record if isinstance(record, dict) else None


def pair_measurement_complete(results: dict, pair: str) -> bool:
    record = pair_record(results, pair)
    return (
        results.get("status") == "MEASURED"
        and record is not None
        and record.get("verdict") in COMPLETE_PAIR_VERDICTS
    )


def choose_run(dataset_id: str, pair: str) -> tuple[Path | None, str | None]:
    fallback: tuple[Path | None, str | None] = (None, "no measured run found")
    for path in candidates(dataset_id, pair):
        manifest_path = path / "manifest.json"
        results_path = path / "results.json"
        if not manifest_path.is_file() or not results_path.is_file():
            continue
        results = load(results_path)
        record = pair_record(results, pair)
        if pair_measurement_complete(results, pair):
            return path, None
        reason = (record or {}).get(
            "failure_reason",
            f"pair is not a complete measurement: {(record or {}).get('verdict')}",
        )
        if fallback[0] is None:
            fallback = (path, str(reason))
    return fallback


def evidence(dataset_id: str, pair: str) -> dict:
    path, selection_reason = choose_run(dataset_id, pair)
    if path is None:
        return {
            "pair": pair,
            "state": "INCOMPLETE",
            "verdict": "NOT_APPLICABLE",
            "failure_reason": selection_reason,
            "source": None,
        }
    manifest_path = path / "manifest.json"
    results_path = path / "results.json"
    manifest = load(manifest_path)
    results = load(results_path)
    pair_record = results.get("equivalence", {}).get("pairs", {}).get(pair)
    complete = pair_measurement_complete(results, pair)
    raw_dir = OUTPUT / "claims" / dataset_id / pair
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name in ("manifest.json", "results.json", "report.md"):
        source = path / name
        if source.is_file():
            shutil.copy2(source, raw_dir / name)
    source_record = {
        "run_path": relative(path),
        "manifest_path": relative(raw_dir / "manifest.json"),
        "results_path": relative(raw_dir / "results.json"),
        "manifest_sha256": sha256(manifest_path),
        "results_sha256": sha256(results_path),
        "encoding_commit": manifest.get("environment", {}).get("git_commit"),
        "measurement_commit": results.get("environment", {}).get("git_commit"),
        "measurement": results.get("measurement"),
    }
    return {
        "pair": pair,
        "state": "COMPLETE" if complete else "INCOMPLETE",
        "comparability": pair_record.get("comparability")
        if isinstance(pair_record, dict)
        else None,
        "verdict": pair_record.get("verdict", "NOT_APPLICABLE")
        if isinstance(pair_record, dict)
        else "NOT_APPLICABLE",
        "failure_reason": None if complete else selection_reason,
        "pair_record": pair_record,
        "jobs": {
            key: value
            for key, value in results.get("results", {}).items()
            if key.split("/", 1)[0]
            in {
                "csv",
                "tsv",
                "arrow_ipc",
                "feather_v2",
                "parquet_default",
                "orc_zlib",
                "object_jsonl",
                "avro_ocf",
                "msgpack_rows",
                "cbor_rows",
                "sqlite_db",
                "duckdb_db",
            }
        },
        "source": source_record,
    }


def reset_generated_output() -> None:
    if OUTPUT.exists() and (OUTPUT.is_symlink() or not OUTPUT.is_dir()):
        raise ValueError(f"aggregate output is not a directory: {OUTPUT}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT.iterdir():
        if path.name == "pilot-contract":
            if path.is_symlink() or not path.is_dir():
                raise ValueError(f"pilot contract input is not a directory: {path}")
            continue
        if path.is_symlink():
            raise ValueError(f"generated output contains a symlink: {path}")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def main() -> None:
    reset_generated_output()
    aggregate_id = "v0.2.0-rc1-revalidation-20260719"
    aggregate_dataset_id = "revalidation-20260719"
    dataset_records = []
    result_records = []
    for dataset_id in DATASETS:
        identity = source_identity(dataset_id)
        pilot = pilot_contract(dataset_id)
        runs = []
        evidence_records = []
        for pair in PAIRS:
            record = evidence(dataset_id, pair)
            evidence_records.append(record)
            if record["source"] is not None:
                runs.append(record["source"])
        dataset_records.append(
            {
                "dataset_id": dataset_id,
                **identity,
                "pilot_contract": pilot,
                "runs": runs,
            }
        )
        complete = sum(record["state"] == "COMPLETE" for record in evidence_records)
        result_records.append(
            {
                "dataset_id": dataset_id,
                "state": "COMPLETE" if complete == len(PAIRS) else "PARTIAL",
                "complete_pairs": complete,
                "required_pairs": len(PAIRS),
                "pilot_contract": pilot,
                "evidence": evidence_records,
            }
        )
    aggregate_input = {
        "schema_version": "aggregate-input-1",
        "aggregate_id": aggregate_id,
        "dataset_id": aggregate_dataset_id,
        "datasets": [
            {
                "dataset_id": item["dataset_id"],
                "dataset_manifest": item["dataset_manifest"],
                "source": item["source"],
            }
            for item in dataset_records
        ],
    }
    aggregate_manifest = {
        "schema_version": "aggregate-1",
        "aggregate_id": aggregate_id,
        "dataset_id": aggregate_dataset_id,
        # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED
        # -> BENCHMARKED -> REPORTED. Incomplete inputs remain explicit below.
        "state": "REPORTED",
        "lane": "equivalence",
        "datasets": dataset_records,
        "notes": [
            "Evidence is selected per dataset and pair; source run provenance is never inferred from pair name.",
            "PARTIAL or INCOMPLETE evidence is not rankable.",
        ],
    }
    aggregate_results = {
        "schema_version": "aggregate-1",
        "aggregate_id": aggregate_manifest["aggregate_id"],
        "dataset_id": aggregate_dataset_id,
        "profile": "equivalence",
        "run_id": aggregate_dataset_id,
        "state": "REPORTED",
        "completion_state": "COMPLETE"
        if all(item["state"] == "COMPLETE" for item in result_records)
        else "PARTIAL",
        "datasets": result_records,
    }
    input_path = OUTPUT / "input" / "manifest.json"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(json.dumps(aggregate_input, indent=2, sort_keys=True) + "\n")
    (OUTPUT / "manifest.json").write_text(
        json.dumps(aggregate_manifest, indent=2, sort_keys=True) + "\n"
    )
    (OUTPUT / "results.json").write_text(
        json.dumps(aggregate_results, indent=2, sort_keys=True) + "\n"
    )
    rows = [
        "# Data Format Lab Equivalence Revalidation",
        "",
        f"Aggregate: `{aggregate_manifest['aggregate_id']}`",
        f"Publication state: **{aggregate_results['state']}**; measurement completion: **{aggregate_results['completion_state']}**",
        "",
        "Incomplete evidence is retained and is not rankable.",
        "",
        "## Dataset Summary",
        "",
        "| Dataset | Rows | Columns | Complete pairs | State |",
        "|---|---:|---:|---:|---|",
    ]
    for record in result_records:
        identity = next(
            item
            for item in dataset_records
            if item["dataset_id"] == record["dataset_id"]
        )
        rows.append(
            f"| {record['dataset_id']} | {identity['source']['rows']} | {identity['source']['columns']} | {record['complete_pairs']}/{record['required_pairs']} | {record['state']} |"
        )
    rows += [
        "",
        "## Pair Evidence",
        "",
        "| Dataset | Pair | State | Verdict | Source run | Failure |",
        "|---|---|---|---|---|---|",
    ]
    for record in result_records:
        for item in record["evidence"]:
            source = item.get("source") or {}
            failure = (item.get("failure_reason") or "").replace("|", "\\|")
            rows.append(
                f"| {record['dataset_id']} | {item['pair']} | {item['state']} | {item['verdict']} | {source.get('run_path', 'N/A')} | {failure} |"
            )
    rows += [
        "",
        "## Provenance",
        "",
        "Every evidence row stores manifest/results SHA-256 and encoding/measurement commits in `results.json`.",
        "",
    ]
    (OUTPUT / "report.md").write_text("\n".join(rows))
    checksum_lines = []
    for path in sorted(OUTPUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            checksum_lines.append(
                f"{sha256(path)}  {path.relative_to(OUTPUT).as_posix()}"
            )
    (OUTPUT / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n")


if __name__ == "__main__":
    main()
