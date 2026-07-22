import json
import sys
from pathlib import Path
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from github_labels import LabelSpec, plan_labels


def _manifest() -> dict[str, object]:
    path = Path(__file__).parents[1] / "docs/agents/review-closeout-labels.json"
    return cast(dict[str, object], json.loads(path.read_text()))


def test_manifest_declares_both_targets_and_unique_labels() -> None:
    manifest = _manifest()
    assert manifest["schema_version"] == "review-closeout-labels/v1"
    assert set(cast(list[str], manifest["repositories"])) == {
        "Anionix/data-format-lab", "Anionix/diagnostic-triage",
    }
    names = cast(list[str], manifest["required_existing"]) + [
        cast(dict[str, str], item)["name"]
        for item in cast(list[object], manifest["managed_labels"])
    ]
    assert len({name.casefold() for name in names}) == len(names)


def test_pure_label_plan_is_encoded_managed_and_convergent() -> None:
    desired = (LabelSpec("source:review", "6f42c1", "review"),
               LabelSpec("lifecycle:tracked", "1d76db", "tracked"))
    unmanaged = LabelSpec("unmanaged", "000000", "preserved")
    plan = plan_labels(
        "Anionix/data-format-lab", desired,
        (LabelSpec("source:review", "ffffff", "drift"), unmanaged),
    )
    assert [(item.method, item.key) for item in plan] == [
        ("POST", "lifecycle:tracked"), ("PATCH", "source:review"),
    ]
    assert plan[1].path.endswith("source%3Areview")
    assert plan_labels("Anionix/data-format-lab", desired, (*desired, unmanaged)) == ()
    assert plan_labels("repo/name", (LabelSpec("x", "ABCDEF", "x"),),
                       (LabelSpec("x", "abcdef", "x"),)) == ()
    with pytest.raises(ValueError, match="duplicate desired label"):
        plan_labels("repo/name", (desired[0], LabelSpec("SOURCE:REVIEW", "ffffff", "x")), ())
