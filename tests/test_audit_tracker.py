import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _tracker() -> ModuleType:
    path = Path(__file__).parents[1] / "tools/audit_tracker.py"
    spec = importlib.util.spec_from_file_location("audit_tracker", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _registry() -> dict[str, object]:
    path = Path(__file__).parents[1] / "docs/audits/2026-07-19/audit.json"
    return json.loads(path.read_text())


def test_registry_matches_strict_audit_contract() -> None:
    tracker = _tracker()
    registry = _registry()
    items = tracker.validate_registry(registry)

    assert len(items) == 174
    assert sum(item.disposition == "ISSUE" for item in items) == 85
    assert tracker.render_report(registry, items).startswith("# Strict Audit Registry\n")
    report = Path(__file__).parents[1] / "docs/audits/2026-07-19/report.md"
    assert tracker.render_report(registry, items) == report.read_text()


def test_ui_readback_rejects_symlinked_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tracker = _tracker()
    registry = _registry()
    source = Path(__file__).parents[1] / registry["github"]["ui_readback"]["path"]
    real = tmp_path / "real"
    real.mkdir()
    (real / "ui-readback.json").write_bytes(source.read_bytes())
    (tmp_path / "evidence").symlink_to(real, target_is_directory=True)
    registry["github"]["ui_readback"]["path"] = "evidence/ui-readback.json"
    monkeypatch.setattr(tracker, "ROOT", tmp_path)

    with pytest.raises(tracker.AuditError, match="non-symlink"):
        tracker.validate_ui_readback(registry)


def test_ui_readback_rejects_impossible_timestamp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tracker = _tracker()
    registry = _registry()
    source = Path(__file__).parents[1] / registry["github"]["ui_readback"]["path"]
    evidence = json.loads(source.read_text())
    evidence["captured_at"] = "2026-99-99T99:99:99Z"
    raw = (json.dumps(evidence, indent=2) + "\n").encode()
    target = tmp_path / "ui-readback.json"
    target.write_bytes(raw)
    registry["github"]["ui_readback"] = {
        "path": target.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    monkeypatch.setattr(tracker, "ROOT", tmp_path)

    with pytest.raises(tracker.AuditError, match="UTC timestamp"):
        tracker.validate_ui_readback(registry)


def test_registry_rejects_original_score_drift_within_a_band() -> None:
    tracker = _tracker()
    registry = _registry()
    registry["items"][0]["original_score"] = 9

    with pytest.raises(tracker.AuditError, match="immutable audit source digest differs"):
        tracker.validate_registry(registry)


def test_registry_rejects_severity_drift() -> None:
    tracker = _tracker()
    registry = _registry()
    registry["items"][0]["severity"] = "HIGH"

    with pytest.raises(tracker.AuditError, match="severity"):
        tracker.validate_registry(registry)


def test_registry_rejects_dependency_cycle() -> None:
    tracker = _tracker()
    registry = _registry()
    registry["items"][0]["dependencies"] = ["DFL-AUDIT-002"]
    registry["items"][1]["dependencies"] = ["DFL-AUDIT-001"]
    registry["source_digest"] = tracker.SOURCE_DIGEST

    with pytest.raises(tracker.AuditError):
        tracker.validate_registry(registry)


def test_registry_rejects_unknown_item_fields() -> None:
    tracker = _tracker()
    registry = _registry()
    registry["items"][0]["unexpected"] = True

    with pytest.raises(tracker.AuditError, match="item fields differ"):
        tracker.validate_registry(registry)


def test_registry_requires_canonical_readiness_and_sync_state() -> None:
    tracker = _tracker()
    registry = _registry()
    issue = next(item for item in registry["items"] if item["disposition"] == "ISSUE")
    issue["readiness_label"] = "wayfinder:research"
    with pytest.raises(tracker.AuditError, match="canonical readiness"):
        tracker.validate_registry(registry)

    registry = _registry()
    registry["github"]["sync_state"] = "PLANNED"
    with pytest.raises(tracker.AuditError, match="issue_number"):
        tracker.validate_registry(registry)


@pytest.mark.parametrize(("field", "value"), [("priority", "P9"), ("owner", "Agnet")])
def test_registry_rejects_invalid_actionable_metadata(field: str, value: str) -> None:
    tracker = _tracker()
    registry = _registry()
    issue = next(item for item in registry["items"] if item["disposition"] == "ISSUE")
    issue[field] = value

    with pytest.raises(tracker.AuditError, match=field):
        tracker.validate_registry(registry)


def test_registry_pins_audited_commit_and_non_actionable_metadata() -> None:
    tracker = _tracker()
    registry = _registry()
    registry["audited_commit"] = "0" * 40
    with pytest.raises(tracker.AuditError, match="audited_commit"):
        tracker.validate_registry(registry)

    registry = _registry()
    monitor = next(item for item in registry["items"] if item["disposition"] == "MONITOR")
    monitor["priority"] = "P0"
    with pytest.raises(tracker.AuditError, match="issue-only metadata"):
        tracker.validate_registry(registry)


def test_registry_pins_audit_identity_and_triage_assignments() -> None:
    tracker = _tracker()
    registry = _registry()
    registry["repository"] = "example/data-format-lab"
    with pytest.raises(tracker.AuditError, match="audit identity"):
        tracker.validate_registry(registry)

    registry = _registry()
    registry["method"] = "A different review method."
    with pytest.raises(tracker.AuditError, match="audit identity"):
        tracker.validate_registry(registry)

    registry = _registry()
    issue = next(item for item in registry["items"] if item["id"] == "DFL-AUDIT-139")
    issue["priority"] = "P2"
    with pytest.raises(tracker.AuditError, match="priority differs"):
        tracker.validate_registry(registry)

    registry = _registry()
    issue = next(item for item in registry["items"] if item["id"] == "DFL-AUDIT-145")
    issue["owner"] = "Agent"
    issue["readiness_label"] = "ready-for-agent"
    with pytest.raises(tracker.AuditError, match="owner differs"):
        tracker.validate_registry(registry)


def test_registry_pins_github_plan_and_synced_issue_numbers() -> None:
    tracker = _tracker()
    registry = _registry()
    registry["github"]["labels"][0]["color"] = "ffffff"
    with pytest.raises(tracker.AuditError, match="GitHub plan"):
        tracker.validate_registry(registry)

    registry = _registry()
    issues = [item for item in registry["items"] if item["disposition"] == "ISSUE"]
    for number, issue in enumerate(issues, start=300):
        issue["issue_number"] = number
    registry["github"]["sync_state"] = "APPLIED"
    issues[-1]["issue_number"] = issues[0]["issue_number"]
    with pytest.raises(tracker.AuditError, match="present and unique"):
        tracker.validate_registry(registry)

    for number, issue in enumerate(issues, start=300):
        issue["issue_number"] = number
    registry["github"]["sync_state"] = "VERIFIED"
    with pytest.raises(tracker.AuditError, match="verified project and saved views"):
        tracker.validate_registry(registry)


def test_registry_pins_item_workstream_assignments() -> None:
    tracker = _tracker()
    registry = _registry()
    issue = next(item for item in registry["items"] if item["disposition"] == "ISSUE")
    issue["workstream"] = "submission"
    issue["milestone"] = "Audit M0 - Submission Ready"

    with pytest.raises(tracker.AuditError, match="triage assignments"):
        tracker.validate_registry(registry)


def test_registry_rejects_workstream_cycles_and_duplicates() -> None:
    tracker = _tracker()
    registry = _registry()
    registry["workstreams"][0]["blocked_by"] = ["measurement"]
    with pytest.raises(tracker.AuditError, match="workstream dependency cycle"):
        tracker.validate_registry(registry)

    registry = _registry()
    registry["workstreams"].append(registry["workstreams"][0])
    with pytest.raises(tracker.AuditError, match="exactly 15"):
        tracker.validate_registry(registry)
