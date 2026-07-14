from __future__ import annotations

import json
from pathlib import Path

from .model import Comparability, ExecutionState


def _cell(value: object) -> str:
    if value is None:
        return "N/A"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[object]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    output.extend("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows)
    return output


def _environment(results: dict) -> list[str]:
    environment = results["environment"]
    rows = [
        ["Git commit", environment["git_commit"]],
        ["Flake lock SHA-256", environment["flake_lock_sha256"]],
        ["Platform", environment["platform"]],
        ["Machine", environment["machine"]],
        ["Python", environment["python"]],
    ]
    return ["## Environment", "", *_table(["Field", "Value"], rows)]


def _fair(manifest: dict, results: dict) -> list[str]:
    formats = manifest["formats"]
    rows = [
        [
            item["format"],
            item["comparability"],
            item["state"],
            item.get("native_bytes"),
            item.get("transport_zstd_bytes"),
            item.get("prepare_write_ms"),
            item.get("failure_reason"),
        ]
        for item in formats
    ]
    output = [
        "## Format Evidence",
        "",
        *_table(
            ["Format", "Comparability", "State", "Native bytes", "zstd bytes", "Write ms", "Failure"],
            rows,
        ),
    ]
    eligible = [
        item
        for item in formats
        if item["comparability"] == Comparability.FULL_COMPARABLE
        and item["state"] == ExecutionState.BENCHMARKED
    ]
    output.extend(["", "## Storage Ordering", ""])
    if not manifest["rankable"]:
        output.append("Disabled: this run used the non-rankable test fixture.")
    else:
        ordered = sorted(eligible, key=lambda item: (item["native_bytes"], item["format"]))
        output.extend(
            _table(
                ["Order", "Format", "Native bytes"],
                [[index, item["format"], item["native_bytes"]] for index, item in enumerate(ordered, 1)],
            )
        )
    eligible_names = {item["format"] for item in eligible}
    timings = []
    for job_id, evidence in sorted(results["results"].items()):
        name, operation = job_id.split("/", 1)
        if name not in eligible_names or evidence["status"] != "MEASURED":
            continue
        timings.append(
            [
                name,
                operation,
                evidence["fresh_process"]["p50_ms"],
                evidence["warm"]["p50_ms"],
                evidence["warm"]["p95_ms"],
                evidence["warm"]["iqr_ms"],
                evidence["result"],
                evidence["max_rss_bytes_p50"],
            ]
        )
    output.extend(
        [
            "",
            "## Fair Operations",
            "",
            *_table(
                ["Format", "Operation", "Fresh p50 ms", "Warm p50 ms", "Warm p95 ms", "IQR ms", "Rows", "RSS bytes"],
                timings,
            ),
        ]
    )
    return output


def _claims(results: dict) -> list[str]:
    rows = []
    for name, item in sorted(results["results"].items()):
        if name == "negative_research":
            for research_name, record in sorted(item.items()):
                rows.append(
                    [research_name, record["comparability"], record["state"], record["attempts"][-1]["result"]]
                )
        else:
            rows.append([name, item["comparability"], item["state"], item.get("failure_reason")])
    return [
        "## Claim Evidence",
        "",
        "Claims use workload-specific contracts and are not a universal format ranking.",
        "",
        *_table(["Claim", "Comparability", "State", "Failure or last result"], rows),
    ]


def _prompt(results: dict) -> list[str]:
    metrics = results["results"]["prompt_v1"]["metrics"]
    corpus = [
        [
            name,
            item["payload_bytes"],
            item["taxonomy_bytes"],
            item["total_bytes"],
            item["tokens"]["o200k_base"],
            item["tokens"]["cl100k_base"],
        ]
        for name, item in metrics["corpus"].items()
    ]
    retrieval = [
        [
            count,
            item["rows"],
            item["bytes"],
            item["tokens"]["o200k_base"],
            item["tokens"]["cl100k_base"],
        ]
        for count, item in sorted(
            metrics["retrieval_to_compact_tsv"].items(), key=lambda pair: int(pair[0])
        )
    ]
    return [
        "## Prompt Corpus",
        "",
        *_table(["Format", "Payload bytes", "Taxonomy bytes", "Total bytes", "o200k", "cl100k"], corpus),
        "",
        "## Retrieval Payload",
        "",
        *_table(["Requested", "Rows", "Bytes", "o200k", "cl100k"], retrieval),
        "",
        "Direct token counts for binary formats are N/A.",
    ]


def render_report(run_dir: Path) -> Path:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    if manifest["state"] != ExecutionState.BENCHMARKED or results["state"] != ExecutionState.BENCHMARKED:
        raise ValueError("report requires benchmarked manifest and results")
    if manifest["dataset_id"] != results["dataset_id"]:
        raise ValueError("manifest and results dataset mismatch")
    profile = results["profile"]
    sections = {
        "fair": lambda: _fair(manifest, results),
        "claims": lambda: _claims(results),
        "prompt": lambda: _prompt(results),
    }
    lines = [
        f"# Data Format Lab: {profile} report",
        "",
        f"Dataset: `{results['dataset_id']}`  ",
        f"Run: `{results['run_id']}`  ",
        "No result in this report is comparable across lanes or hardware runs.",
        "",
        *_environment(results),
        "",
        *sections[profile](),
        "",
    ]
    path = run_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
