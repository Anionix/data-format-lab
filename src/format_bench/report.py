from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .model import Comparability, ExecutionState, RobustnessVerdict, transition
from .robustness.summary import summarize_cases


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_file(run_dir: Path, value: object) -> Path | None:
    if not isinstance(value, str):
        return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"report path is unsafe: {value}")
    return run_dir / relative


def _provenance(run_dir: Path, manifest: dict, results: dict) -> list[str]:
    input_info = manifest.get("input", {})
    input_manifest_path = _run_file(
        run_dir, input_info.get("manifest") if isinstance(input_info, dict) else None
    )
    source_path = _run_file(
        run_dir, input_info.get("source") if isinstance(input_info, dict) else None
    )
    dataset = {}
    if input_manifest_path is not None and input_manifest_path.is_file():
        dataset = json.loads(input_manifest_path.read_text(encoding="utf-8"))
    columns = dataset.get("columns", [])
    schema = ", ".join(
        f"{item.get('name')}:{item.get('arrow_type')}"
        f"{'?' if item.get('nullable', True) else '!'}"
        for item in columns
        if isinstance(item, dict)
    )
    dataset_rows = [
        ["Rows", dataset.get("rows", "N/A")],
        ["Columns", len(columns) if isinstance(columns, list) else "N/A"],
        ["Schema", schema or "N/A"],
        ["Source SHA-256", dataset.get("source_sha256", "N/A")],
        ["Canonical hash", dataset.get("canonical_hash", "N/A")],
        [
            "Expected counts",
            json.dumps(dataset.get("expected_counts", {}), sort_keys=True),
        ],
    ]
    measurement = results.get("measurement", {})
    measurement_rows = [
        [key, measurement[key]] for key in sorted(measurement)
    ]
    packages = results.get("environment", {}).get("packages", {})
    package_rows = [[key, packages[key]] for key in sorted(packages)]
    digest_rows = [
        ["Manifest SHA-256", _sha256(run_dir / "manifest.json")],
        ["Results SHA-256", _sha256(run_dir / "results.json")],
    ]
    if input_manifest_path is not None and input_manifest_path.is_file():
        digest_rows.append(["Input manifest SHA-256", _sha256(input_manifest_path)])
    if source_path is not None and source_path.is_file():
        digest_rows.append(["Input source SHA-256", _sha256(source_path)])
    lines = [
        "## Dataset Contract",
        "",
        *_table(["Field", "Value"], dataset_rows),
        "",
        "## Measurement Protocol",
        "",
        *_table(["Setting", "Value"], measurement_rows),
        "",
        "## Package Versions",
        "",
        *_table(["Package", "Version"], package_rows),
        "",
        "## Evidence Digests",
        "",
        *_table(["File", "SHA-256"], digest_rows),
        "",
        "Format settings in the Format Evidence table are the writer settings used for each artifact.",
        "The `format-bench package` command includes these raw JSON files and referenced artifacts; it writes the archive SHA-256 to the adjacent `.sha256` file.",
    ]
    release = results.get("release", {})
    if isinstance(release, dict) and isinstance(release.get("archive_url"), str):
        lines.extend(
            [
                "",
                "## Durable Evidence",
                "",
                *_table(
                    ["File", "URL"],
                    [
                        ["Raw archive", release["archive_url"]],
                        ["SHA-256 checksum", release.get("checksum_url", "N/A")],
                    ],
                ),
            ]
        )
    return lines


def _environment(results: dict) -> list[str]:
    environment = results["environment"]
    rows = [
        ["Git commit", environment["git_commit"]],
        ["Flake lock SHA-256", environment["flake_lock_sha256"]],
        ["Platform", environment["platform"]],
        ["Machine", environment["machine"]],
        ["Hardware model", environment.get("hardware_model", "N/A")],
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
            json.dumps(item.get("settings", {}), sort_keys=True, separators=(",", ":")),
            item.get("failure_reason"),
        ]
        for item in formats
    ]
    output = [
        "## Format Evidence",
        "",
        *_table(
            [
                "Format",
                "Comparability",
                "State",
                "Native bytes",
                "zstd bytes",
                "Write ms",
                "Settings",
                "Failure",
            ],
            rows,
        ),
    ]
    eligible = [
        item
        for item in formats
        if item["comparability"] == Comparability.FULL_COMPARABLE
        and item["state"]
        in {ExecutionState.BENCHMARKED, ExecutionState.REPORTED}
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
                evidence["evidence"]["normalized_hash"],
                evidence["max_rss_bytes_p50"],
            ]
        )
    output.extend(
        [
            "",
            "## Fair Operations",
            "",
            *_table(
                [
                    "Format",
                    "Operation",
                    "Fresh p50 ms",
                    "Warm p50 ms",
                    "Warm p95 ms",
                    "IQR ms",
                    "Rows",
                    "Result hash",
                    "RSS bytes",
                ],
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
                summary = record.get("claim_summary")
                if summary is None:
                    attempts = record.get("attempts", [])
                    summary = (
                        attempts[-1].get("result")
                        if attempts and isinstance(attempts[-1], dict)
                        else None
                    )
                summary = summary or "no claim summary recorded"
                rows.append(
                    [
                        research_name,
                        "RESEARCH_RECORD",
                        record["comparability"],
                        record["state"],
                        summary,
                    ]
                )
        else:
            evidence = item.get("evidence", {})
            rows.append(
                [
                    name,
                    item.get("target_tier", "CORE"),
                    item["comparability"],
                    item["state"],
                    item.get("failure_reason") or evidence.get("summary"),
                ]
            )
    return [
        "## Claim Evidence",
        "",
        "Claims use workload-specific contracts and are not a universal format ranking.",
        "",
        *_table(
            ["Claim", "Tier", "Comparability", "State", "Failure or claim result"],
            rows,
        ),
    ]


def _prompt(results: dict) -> list[str]:
    metrics = results["results"]["prompt_v1"]["metrics"]
    corpus = [
        [
            name,
            item["payload_bytes"],
            item["taxonomy_bytes"],
            item.get("schema_bytes", 0),
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
        *_table(
            [
                "Format",
                "Payload bytes",
                "Taxonomy bytes",
                "Schema bytes",
                "Total bytes",
                "o200k",
                "cl100k",
            ],
            corpus,
        ),
        "",
        "## Retrieval Payload",
        "",
        *_table(["Requested", "Rows", "Bytes", "o200k", "cl100k"], retrieval),
        "",
        "Direct token counts for binary formats are N/A.",
    ]


def _robustness(results: dict) -> list[str]:
    evidence = results["results"]["robustness_v1"]
    config = evidence["config"]
    config_rows = [
        ["Seed", config["seed"]],
        ["Generated cases", config["generated_cases"]],
        ["Mutations per target", config["mutations_per_target"]],
        ["Case timeout seconds", config["case_timeout_seconds"]],
        ["Artifact budget MiB", config["artifact_budget_mib"]],
    ]
    summary_rows = [
        [verdict, evidence["summary"].get(verdict.value, 0)]
        for verdict in RobustnessVerdict
    ]
    def case_engine(item: dict) -> object:
        engine = item.get("engine")
        if isinstance(engine, str):
            return engine
        details = item.get("details")
        if isinstance(details, dict) and isinstance(details.get("engine"), str):
            return details["engine"]
        return "common"

    case_rows = [
        [
            item["target"],
            item["tier"],
            case_engine(item),
            item["case_id"],
            item["expectation"],
            item["observed"],
            item["verdict"],
        ]
        for item in evidence["cases"]
    ]
    target_summary = evidence.get("target_summary")
    if not isinstance(target_summary, dict) or not target_summary:
        target_summary = summarize_cases(evidence["cases"])
        evidence["target_summary"] = target_summary
    target_rows = [
        [
            target,
            item["tier"],
            item["cases"],
            item["applicable"],
            item["pass"],
            item["fail"],
            item["crashed"],
            item["timed_out"],
            item["unsupported"],
            item["harness_failed"],
            item["budget_exhausted"],
            item["duration_ms_p50"],
        ]
        for target, item in sorted(target_summary.items())
    ]
    identity_rows = [
        [
            target,
            ", ".join(item["artifact_sha256"]) or "N/A",
            ", ".join(item["source_identities"]) or "N/A",
        ]
        for target, item in sorted(target_summary.items())
    ]
    return [
        "## Robustness Evidence",
        "",
        "Robustness observations are non-ranking evidence and do not change other lane ordering.",
        "",
        "### Configuration",
        "",
        *_table(["Setting", "Value"], config_rows),
        "",
        "### Verdict Summary",
        "",
        *_table(["Verdict", "Cases"], summary_rows),
        "",
        "### Target Summary",
        "",
        *_table(
            [
                "Target",
                "Tier",
                "Cases",
                "Applicable",
                "PASS",
                "FAIL",
                "Crashes",
                "Timeouts",
                "Unsupported",
                "Harness failed",
                "Budget exhausted",
                "Duration p50 ms",
            ],
            target_rows,
        ),
        "",
        "### Evidence Identities",
        "",
        *_table(["Target", "Artifact SHA-256", "Source identity"], identity_rows),
        "",
        "### Cases",
        "",
        *_table(
            ["Target", "Tier", "Engine", "Case", "Expectation", "Observed", "Verdict"],
            case_rows,
        ),
    ]


def _report_observations(manifest: dict, results: dict) -> None:
    for entry in manifest.get("formats", []):
        if entry.get("state") == ExecutionState.BENCHMARKED:
            entry["state"] = transition(
                ExecutionState.BENCHMARKED, ExecutionState.REPORTED
            )
    for observation in results.get("results", {}).values():
        if (
            isinstance(observation, dict)
            and observation.get("state") == ExecutionState.BENCHMARKED
        ):
            observation["state"] = transition(
                ExecutionState.BENCHMARKED, ExecutionState.REPORTED
            )


def render_report(run_dir: Path) -> Path:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    reportable = {ExecutionState.BENCHMARKED, ExecutionState.REPORTED}
    if manifest["state"] not in reportable or results["state"] not in reportable:
        raise ValueError("report requires benchmarked or reported manifest and results")
    if manifest["dataset_id"] != results["dataset_id"]:
        raise ValueError("manifest and results dataset mismatch")
    # Project observation transitions into the report; persist only after it exists.
    _report_observations(manifest, results)
    profile = results["profile"]
    sections = {
        "fair": lambda: _fair(manifest, results),
        "claims": lambda: _claims(results),
        "prompt": lambda: _prompt(results),
        "robustness": lambda: _robustness(results),
    }
    section = sections[profile]()
    for payload, json_path in (
        (manifest, run_dir / "manifest.json"),
        (results, run_dir / "results.json"),
    ):
        if payload["state"] == ExecutionState.BENCHMARKED:
            payload["state"] = transition(ExecutionState.BENCHMARKED, ExecutionState.REPORTED)
        json_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    lines = [
        f"# Data Format Lab: {profile} report",
        "",
        f"Dataset: `{results['dataset_id']}`  ",
        f"Run: `{results['run_id']}`  ",
        "No result in this report is comparable across lanes or hardware runs.",
        "",
        *_environment(results),
        "",
        *_provenance(run_dir, manifest, results),
        "",
        *section,
        "",
    ]
    path = run_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    # LLM contract: BENCHMARKED -> REPORTED before durable report output.
    return path
