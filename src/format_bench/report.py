from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from .model import Comparability, ExecutionState, Lane, RobustnessVerdict, transition
from .json_contract import atomic_write_json, strict_json_dumps
from .robustness.summary import summarize_cases


def _cell(value: object) -> str:
    if value is None:
        return "N/A"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _string_values(value: object) -> list[str]:
    if isinstance(value, list):
        strings = [item for item in value if isinstance(item, str)]
        if len(strings) == len(value):
            return strings
    return []


def _table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    output.extend(
        "| " + " | ".join(_cell(value) for value in row) + " |" for row in rows
    )
    return output


def _package_versions(environment: dict) -> str:
    packages = environment.get("packages", {})
    return strict_json_dumps(
        {name: value for name, value in sorted(packages.items()) if value},
        sort_keys=True,
        separators=(",", ":"),
    )


def _contract_phrase(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.replace("_", " ")


def _estimand_target(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    variable = _contract_phrase(value.get("variable"))
    summary = _contract_phrase(value.get("population_summary"))
    if variable is None or summary is None:
        return None
    return f"{variable}; {summary}"


def _environment_rows(environment: dict) -> list[list[object]]:
    rows: list[list[object]] = [
        ["Git commit", environment.get("git_commit")],
        ["Flake lock SHA-256", environment.get("flake_lock_sha256")],
        ["Platform", environment.get("platform")],
        ["Machine", environment.get("machine")],
        ["Hardware model", environment.get("hardware_model", "N/A")],
        ["Python", environment.get("python")],
        ["Packages", _package_versions(environment)],
    ]
    return rows


def _environment(manifest: dict, results: dict) -> list[str]:
    return [
        "## Environment",
        "",
        "### Encoding",
        "",
        *_table(["Field", "Value"], _environment_rows(manifest.get("environment", {}))),
        "",
        "### Measurement",
        "",
        *_table(["Field", "Value"], _environment_rows(results.get("environment", {}))),
    ]


def _input_manifest(run_dir: Path, manifest: dict) -> dict:
    reference = manifest.get("input", {}).get("manifest")
    if not isinstance(reference, str):
        return {}
    path = _input_path(run_dir, reference)
    if path is None:
        return {}
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _input_path(run_dir: Path, reference: str) -> Path | None:
    path = (run_dir / reference).resolve()
    try:
        path.relative_to(run_dir.resolve())
    except ValueError:
        return None
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: dict) -> bytes:
    return (strict_json_dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _provenance(run_dir: Path, manifest: dict, results: dict) -> list[str]:
    input_manifest = _input_manifest(run_dir, manifest)
    input_info = manifest.get("input", {})
    manifest_reference = (
        input_info.get("manifest") if isinstance(input_info, dict) else None
    )
    input_manifest_path = (
        _input_path(run_dir, manifest_reference)
        if isinstance(manifest_reference, str)
        else None
    )
    source_reference = (
        input_info.get("source") if isinstance(input_info, dict) else None
    )
    source_path = (
        _input_path(run_dir, source_reference)
        if isinstance(source_reference, str)
        else None
    )
    actual_source_sha256 = (
        _sha256(source_path)
        if source_path is not None and source_path.is_file()
        else None
    )
    declared_source_sha256 = input_manifest.get("source_sha256")
    if (
        actual_source_sha256 is not None
        and declared_source_sha256 is not None
        and actual_source_sha256 != declared_source_sha256
    ):
        raise ValueError(
            "input source SHA-256 mismatch: "
            f"declared {declared_source_sha256}, actual {actual_source_sha256}"
        )
    environment = results.get("environment", {})
    packages = environment.get("packages", {})
    measurement = results.get("measurement", {})
    columns = input_manifest.get("columns", [])
    rows = input_manifest.get("rows")
    dimensions = f"{rows} / {len(columns)}" if rows is not None else None
    format_settings = [
        [
            entry.get("format"),
            strict_json_dumps(
                entry.get("settings", {}), sort_keys=True, separators=(",", ":")
            ),
        ]
        for entry in manifest.get("formats", [])
    ]
    protocol = None
    if measurement:
        protocol = (
            f"{measurement.get('fresh_processes')} fresh processes; "
            f"{measurement.get('warmups')} warmups; "
            f"{measurement.get('iterations')} measurements; "
            f"timeout {measurement.get('timeout_seconds')}s"
        )
    estimand = measurement.get("estimand", {})
    estimand = estimand if isinstance(estimand, dict) else {}
    population = estimand.get("target_population", {})
    population = population if isinstance(population, dict) else {}
    population_summary = None
    if population:
        population_summary = (
            f"{population.get('dataset_id')}: {population.get('rows')} rows "
            f"({_contract_phrase(population.get('kind'))})"
        )
    targets = estimand.get("targets", {})
    targets = targets if isinstance(targets, dict) else {}
    descriptive = estimand.get("descriptive_outputs", {})
    descriptive = descriptive if isinstance(descriptive, dict) else {}
    rows = [
        ["Input SHA-256", actual_source_sha256 or declared_source_sha256],
        ["Canonical hash", input_manifest.get("canonical_hash")],
        ["Rows / columns", dimensions],
        [
            "Expected counts",
            strict_json_dumps(
                input_manifest.get("expected_counts", {}),
                sort_keys=True,
                separators=(",", ":"),
            ),
        ],
        ["PyArrow", packages.get("pyarrow")],
        ["Packages", _package_versions(environment)],
        ["Protocol", protocol],
        ["Estimand contract", estimand.get("contract_version")],
        ["Target population", population_summary],
        ["Fresh estimand", _estimand_target(targets.get("fresh_p50_ms"))],
        ["Warm estimand", _estimand_target(targets.get("warm_p50_ms"))],
        ["Warm tail estimand", _estimand_target(targets.get("warm_p95_ms"))],
        ["Pooled warm role", _contract_phrase(descriptive.get("warm"))],
        ["Failure strategy", _contract_phrase(estimand.get("failure_strategy"))],
        ["Seed", measurement.get("seed", manifest.get("seed"))],
        ["OS cache purged", measurement.get("os_cache_purged")],
    ]
    digest_rows = [
        ["Manifest SHA-256", _sha256_bytes(_json_bytes(manifest))],
        ["Results SHA-256", _sha256_bytes(_json_bytes(results))],
    ]
    if input_manifest_path is not None and input_manifest_path.is_file():
        digest_rows.append(["Input manifest SHA-256", _sha256(input_manifest_path)])
    if source_path is not None and source_path.is_file():
        digest_rows.append(["Input source SHA-256", _sha256(source_path)])
    evidence = [
        "## Evidence Digests",
        "",
        *_table(["File", "SHA-256"], digest_rows),
        "",
        "Format settings in the Writer Settings table are the writer settings used for each artifact.",
        "The `format-bench package` command includes these raw JSON files and referenced artifacts; it writes the archive SHA-256 to the adjacent `.sha256` file.",
    ]
    release = results.get("release", {})
    if isinstance(release, dict) and isinstance(release.get("archive_url"), str):
        evidence.extend(
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
    return [
        "## Reproducibility",
        "",
        *_table(["Field", "Value"], rows),
        "",
        "### Writer Settings",
        "",
        *_table(["Format", "Settings"], format_settings),
        "",
        *evidence,
    ]


def _fair(manifest: dict, results: dict) -> list[str]:
    formats = [
        item for item in manifest["formats"] if item.get("lane", Lane.FAIR) == Lane.FAIR
    ]
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
            [
                "Format",
                "Comparability",
                "State",
                "Native bytes",
                "zstd bytes",
                "Write ms",
                "Failure",
            ],
            rows,
        ),
    ]
    eligible = [
        item
        for item in formats
        if item["comparability"] == Comparability.FULL_COMPARABLE
        and item["state"] in {ExecutionState.BENCHMARKED, ExecutionState.REPORTED}
    ]
    output.extend(["", "## Storage Ordering", ""])
    if not manifest["rankable"]:
        output.append("Disabled: this run used the non-rankable test fixture.")
    else:
        ordered = sorted(
            eligible, key=lambda item: (item["native_bytes"], item["format"])
        )
        output.extend(
            _table(
                ["Order", "Format", "Native bytes"],
                [
                    [index, item["format"], item["native_bytes"]]
                    for index, item in enumerate(ordered, 1)
                ],
            )
        )
    eligible_names = {item["format"] for item in eligible}
    timings = []
    for job_id, evidence in sorted(results["results"].items()):
        name, operation = job_id.split("/", 1)
        if name not in eligible_names or evidence["status"] != "MEASURED":
            continue
        warm_process = evidence.get("warm_process_estimates", {})
        warm_process = warm_process if isinstance(warm_process, dict) else {}
        timings.append(
            [
                name,
                operation,
                evidence["fresh_process"]["p50_ms"],
                warm_process.get("median_p50_ms"),
                warm_process.get("median_p95_ms"),
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
                    "Warm median-of-p50 ms",
                    "Warm median-of-p95 ms",
                    "Pooled warm p50 ms",
                    "Pooled warm p95 ms",
                    "Pooled warm IQR ms",
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
    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    # Mutation counts are descriptive report evidence only; they never affect ranking or gates.
    mutation_rows = []
    for target, item in sorted(target_summary.items()):
        mutation = item.get("artifact_mutation", {})
        mutation_rows.append(
            [
                target,
                mutation.get("denominator", 0),
                mutation.get("completed", 0),
                mutation.get("failures", 0),
                mutation.get("crashes", 0),
                mutation.get("timeouts", 0),
                mutation.get("unsupported", 0),
                mutation.get("incomplete", 0),
                mutation.get("completed_pct"),
            ]
        )
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
            ", ".join(_string_values(item["artifact_sha256"])) or "N/A",
            ", ".join(_string_values(item["source_identities"])) or "N/A",
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
        "### Artifact Mutation Coverage",
        "",
        "Artifact mutation counts cover only generated cases with a persisted mutation recipe identity; named boundary cases are excluded. This is descriptive reliability evidence, not a mutation score, and has no ranking or gate effect.",
        "",
        *_table(
            [
                "Target",
                "Denominator",
                "Completed",
                "Failures",
                "Crashes",
                "Timeouts",
                "Unsupported",
                "Incomplete",
                "Completed %",
            ],
            mutation_rows,
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


def _equivalence(results: dict) -> list[str]:
    evidence = results.get("equivalence", {})
    pairs = evidence.get("pairs", {})
    control = evidence.get("multiplicity_control")
    control_section = (
        [
            "### Primary Multiplicity Control",
            "",
            *_table(
                ["Field", "Value"],
                [
                    ["Error-control target", control.get("error_control_target")],
                    ["Method", control.get("method")],
                    ["Family", control.get("family_id")],
                    ["Planned comparisons", control.get("planned_comparisons")],
                    ["Family alpha", control.get("family_alpha")],
                    ["Comparison alpha", control.get("comparison_alpha")],
                    ["Primary interval", control.get("primary_interval_method")],
                    ["Coverage claim", control.get("coverage_claim")],
                    ["Status", control.get("status")],
                    ["Accepted risk", control.get("accepted_risk")],
                    ["Secondary metrics", control.get("secondary_metrics")],
                ],
            ),
            "",
        ]
        if isinstance(control, dict)
        else []
    )
    rows: list[list[object]] = []
    for pair, item in sorted(pairs.items()):
        endpoint = item.get("primary_endpoint", {})
        if not isinstance(endpoint, dict):
            endpoint = {}
        primary = "/".join(
            str(value)
            for value in (
                endpoint.get("scope"),
                endpoint.get("operation"),
                endpoint.get("metric"),
            )
            if value
        )
        rows.append(
            [
                pair,
                item.get("lane", "N/A"),
                item.get("comparison_scope", "format_pair"),
                item.get("reference", "N/A"),
                ", ".join(item.get("candidates", ())) or "N/A",
                primary or "legacy all-metrics",
                item.get("verdict", "N/A"),
                item.get("accepted_risk") or "",
                item.get("failure_reason") or "",
            ]
        )
    metric_rows: list[list[object]] = []
    for pair, item in sorted(pairs.items()):
        endpoint = item.get("primary_endpoint", {})
        if not isinstance(endpoint, dict):
            endpoint = {}
        for format_name, comparison in sorted(item.get("formats", {}).items()):
            scopes = [("storage", comparison.get("storage", {}))]
            scopes.extend(
                (operation, operation_evidence)
                for operation, operation_evidence in sorted(
                    comparison.get("operations", {}).items()
                )
            )
            for scope, scope_evidence in scopes:
                for metric in scope_evidence.get("metrics", ()):
                    role = (
                        "primary"
                        if endpoint.get("metric") == metric.get("metric")
                        and (
                            endpoint.get("scope") == scope == "storage"
                            or (
                                endpoint.get("scope") == "operation"
                                and endpoint.get("operation") == scope
                            )
                        )
                        else "descriptive"
                    )
                    metric_rows.append(
                        [
                            pair,
                            format_name,
                            scope,
                            metric.get("metric"),
                            role,
                            metric.get("ratio"),
                            metric.get("lower"),
                            metric.get("upper"),
                            metric.get("verdict", scope_evidence.get("verdict")),
                        ]
                    )
    return [
        "## Equivalence Evidence",
        "",
        "Contract v2 uses each pair's preregistered primary endpoint; secondary intervals remain descriptive evidence. Legacy v1 keeps its recorded all-metrics verdict.",
        "",
        *control_section,
        "### Pair Verdicts",
        "",
        *_table(
            [
                "Pair",
                "Lane",
                "Scope",
                "Reference",
                "Candidates",
                "Primary endpoint",
                "Verdict",
                "Accepted risk",
                "Failure",
            ],
            rows,
        ),
        "",
        "### Ratio Intervals",
        "",
        *_table(
            [
                "Pair",
                "Candidate",
                "Scope",
                "Metric",
                "Role",
                "Ratio",
                "Lower",
                "Upper",
                "Verdict",
            ],
            metric_rows,
        ),
        "",
        "Bounds: size +/-2%; p50 +/-5%; p95 +/-10%. Intervals crossing a bound are inconclusive.",
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
        "equivalence": lambda: _equivalence(results),
    }
    section = sections[profile]()
    for payload in (manifest, results):
        if payload["state"] == ExecutionState.BENCHMARKED:
            payload["state"] = transition(
                ExecutionState.BENCHMARKED, ExecutionState.REPORTED
            )
    lines = [
        f"# Data Format Lab: {profile} report",
        "",
        f"Dataset: `{results['dataset_id']}`<br>",
        f"Run: `{results['run_id']}`<br>",
        "No result in this report is comparable across lanes or hardware runs.",
        "",
        *_environment(manifest, results),
        "",
        *_provenance(run_dir, manifest, results),
        "",
        *section,
        "",
    ]
    path = run_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    for payload, json_path in (
        (manifest, run_dir / "manifest.json"),
        (results, run_dir / "results.json"),
    ):
        if payload["state"] == ExecutionState.BENCHMARKED:
            payload["state"] = transition(
                ExecutionState.BENCHMARKED, ExecutionState.REPORTED
            )
        atomic_write_json(json_path, payload)
    # LLM contract: transition in memory, then persist after durable report output.
    return path
