import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _taxonomy_mapping() -> dict[str, list[str]]:
    text = (ROOT / "docs/diagnostic-triage/taxonomy.md").read_text()
    rows = (line for line in text.splitlines() if line.startswith("| `"))
    return {
        cells[0]: cells[1:]
        for line in rows
        if len(cells := re.findall(r"`([^`]+)`", line)) > 1
    }


def _schema_mapping() -> dict[str, list[str]]:
    path = ROOT / "schemas/diagnostic-triage/v1/finding.schema.json"
    schema = json.loads(path.read_text())
    category_rules = next(
        group["oneOf"]
        for group in schema["allOf"]
        if "oneOf" in group and "category" in group["oneOf"][0]["properties"]
    )
    return {
        rule["properties"]["category"]["const"]: rule["properties"]["micro_category"]["enum"]
        for rule in category_rules
    }


def test_taxonomy_and_finding_schema_are_synchronized() -> None:
    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    assert _schema_mapping() == _taxonomy_mapping()


def _valid_finding() -> dict[str, object]:
    return {
        "schema_version": "diagnostic-triage.finding/v1",
        "finding_id": "018F1F30-8A85-7C2C-9F1A-2B3C4D5E6F72",
        "fingerprint": "0" * 64,
        "tool": {"name": "ty", "version": "0.0.1", "rule_id": "invalid-return-type"},
        "language": "PYTHON",
        "severity": "ERROR",
        "category": "type",
        "micro_category": "incompatible-type",
        "message": "return type differs",
        "expected": "str",
        "observed": "int",
        "verdict": "POLICY_FAIL",
        "state": "CLASSIFIED",
        "evidence_ids": ["00000000-0000-0000-0000-000000000000"],
        "fix": {
            "applicability": "SAFE",
            "tool_native": True,
            "patch_evidence_id": "018F1F30-8A85-7C2C-9F1A-2B3C4D5E6F73",
        },
    }


def _check_schema(*paths: Path, schema: Path | None = None) -> subprocess.CompletedProcess[str]:
    args = ["check-jsonschema", "--disable-formats", "*"]
    args.extend(["--schemafile", str(schema)] if schema else ["--check-metaschema"])
    args.extend(str(path) for path in paths)
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=10)


def _assert_schema_result(
    result: subprocess.CompletedProcess[str], *, valid: bool
) -> None:
    assert (result.returncode == 0) is valid, result.stdout + result.stderr


def test_finding_schema_rejects_malformed_uuids_without_format_assertion(
    tmp_path: Path,
) -> None:
    schema_path = ROOT / "schemas/diagnostic-triage/v1/finding.schema.json"
    _assert_schema_result(_check_schema(schema_path), valid=True)

    valid_path = tmp_path / "valid.json"
    valid_path.write_text(json.dumps(_valid_finding()))
    _assert_schema_result(_check_schema(valid_path, schema=schema_path), valid=True)

    malformed_finding_id = _valid_finding()
    malformed_finding_id["finding_id"] = "not-a-uuid"
    malformed_evidence_id = _valid_finding()
    malformed_evidence_id["evidence_ids"] = ["not-a-uuid"]
    malformed_patch_id = _valid_finding()
    malformed_patch_id["fix"] = {
        "applicability": "SAFE",
        "tool_native": True,
        "patch_evidence_id": "not-a-uuid",
    }
    for name, malformed in (
        ("finding-id", malformed_finding_id),
        ("evidence-id", malformed_evidence_id),
        ("patch-evidence-id", malformed_patch_id),
    ):
        malformed_path = tmp_path / f"malformed-{name}.json"
        malformed_path.write_text(json.dumps(malformed))
        _assert_schema_result(
            _check_schema(malformed_path, schema=schema_path), valid=False
        )
