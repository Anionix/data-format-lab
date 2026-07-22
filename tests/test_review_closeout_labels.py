import json
import sys
from pathlib import Path
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from github_labels import LabelSpec, plan_labels
import review_closeout_labels as sync
from audit_tracker import AuditError


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


class FakeRest:
    def __init__(self, *, invalid_second: bool = False, response_loss: bool = False) -> None:
        repositories, required, managed = sync.load_manifest()
        base = [LabelSpec(name, "000000", "required") for name in required] + list(managed)
        self.live = {repository: list(base) for repository in repositories}
        if invalid_second:
            self.live[repositories[1]].pop(0)
        self.response_loss = response_loss
        self.mutations: list[object] = []
    def get(self, path: str) -> object:
        return {"full_name": path.removeprefix("repos/")}
    def pages(self, path: str) -> object:
        repository = path.removeprefix("repos/").split("/labels", 1)[0]
        return [[vars(label) for label in self.live[repository]]]
    def mutate(self, mutation: object) -> object:
        item = cast(sync.Mutation, mutation)
        repository = item.path.removeprefix("repos/").split("/labels", 1)[0]
        name = cast(str, item.payload.get("name", item.payload.get("new_name")))
        desired = LabelSpec(name, cast(str, item.payload["color"]), cast(str, item.payload["description"]))
        self.live[repository] = [label for label in self.live[repository]
                                 if label.name.casefold() != name.casefold()] + [desired]
        self.mutations.append(item)
        if self.response_loss:
            self.response_loss = False
            raise AuditError("response lost")
        return vars(desired)


def test_sync_preflights_all_targets_before_mutation() -> None:
    client = FakeRest(invalid_second=True)
    with pytest.raises(AuditError, match="missing required labels"):
        sync.synchronize(True, client)
    assert client.mutations == []


def test_check_is_read_only_and_apply_recovers_then_converges() -> None:
    client = FakeRest(response_loss=True)
    repository = next(iter(client.live))
    client.live[repository].pop()
    assert any(sync.synchronize(False, client).values()) and client.mutations == []
    sync.synchronize(True, client)
    assert len(client.mutations) == 1
    assert not any(sync.synchronize(False, client).values())


@pytest.mark.parametrize(("plans", "expected"), [({}, 0), ({"repo": (object(),)}, 1)])
def test_cli_check_exit_codes(monkeypatch: pytest.MonkeyPatch, plans: object, expected: int) -> None:
    monkeypatch.setattr(sync, "synchronize", lambda _apply: plans)
    monkeypatch.setattr("sys.argv", ["review-closeout-labels"])
    assert sync.main() == expected


def test_cli_failure_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "synchronize", lambda _apply: (_ for _ in ()).throw(AuditError("bad")))
    monkeypatch.setattr("sys.argv", ["review-closeout-labels"])
    assert sync.main() == 2
