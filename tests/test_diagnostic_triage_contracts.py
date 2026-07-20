import json
import re
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
