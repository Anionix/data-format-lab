from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal, cast

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from review_closeout import (
    MARKER,
    ReviewCloseoutError,
    ReviewThread,
    batch_ready,
    _parse_page,
    issue_payload,
    review_priority,
    run,
    tracked_issues,
)

OWNER_LABELS = [{"name": "bug"}, {"name": "source:review"}]
FailureMode = Literal[
    "add-lifecycle", "closed-readback", "invalid-after-reply", "invalid-before-reply",
    "lifecycle", "outdated", "reply", "resolve", "spoof", "stale-collection",
    "stale-pending-collection", "stale-source-closed-collection",
]


class FakeClient:
    def __init__(self, merged_count: int = 0) -> None:
        self.actor = "Anionix"
        self.graphql_calls = 0
        self.rest_calls = 0
        self.rest_paths: list[str] = []
        self.created: list[dict[str, object]] = []
        self.issues: list[dict[str, object]] = []
        self.replies: list[str] = []
        self.resolves: list[str] = []
        self.label_adds: list[tuple[str, str]] = []
        self.label_removes: list[tuple[str, str]] = []
        self.failure_mode: FailureMode | None = None
        self.pages: list[object] = []
        self.payload = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [
                            {
                                "id": f"pr-{number}",
                                "number": number,
                                "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": [{
                                    "id": f"thread-{number}",
                                    "pullRequest": {"number": number, "repository": {"nameWithOwner": "Anionix/data-format-lab"}},
                                    "isResolved": False,
                                    "isOutdated": False,
                                    "comments": {
                                        "pageInfo": {"hasNextPage": False},
                                        "nodes": [{"body": "P2 Badge", "author": {"login": "reviewer"}}],
                                    },
                                }]},
                            }
                            for number in range(1, merged_count + 1)
                        ],
                    }
                }
            }
        }

    def graphql(self, query: str, fields: dict[str, str | None]) -> object:
        self.graphql_calls += 1
        if "query($node:ID!)" in query:
            if self.failure_mode == "invalid-before-reply":
                self.issues[0]["state"] = "closed"
            return {"data": {"node": self._thread(cast(str, fields["node"]))}}
        return self.pages.pop(0) if self.pages else self.payload

    def rest(self, path: str) -> object:
        self.rest_calls += 1
        self.rest_paths.append(path)
        if "/issues/" in path:
            number = int(path.rsplit("/", 1)[1])
            issue = next(issue for issue in self.issues if issue["number"] == number)
            if self.failure_mode == "closed-readback":
                return [{**issue, "state": "closed"}]
            return [issue]
        if self.failure_mode == "stale-collection" and self.created:
            return [self.issues[:1]]
        if self.failure_mode == "stale-source-closed-collection":
            return [[{
                **issue,
                "labels": [item for item in cast(list[dict[str, str]], issue["labels"])
                           if item["name"] != "lifecycle:source-closed"],
            } for issue in self.issues]]
        if self.failure_mode == "stale-pending-collection":
            return [[{
                **issue,
                "labels": [*cast(list[dict[str, str]], issue["labels"]),
                           {"name": "lifecycle:closeout-pending"}],
            } for issue in self.issues]]
        return [self.issues]

    def current_user(self) -> str:
        return self.actor

    def create_issue(self, path: str, payload: dict[str, object]) -> object:
        self.created.append(payload)
        labels = cast(list[str], payload["labels"])
        issue = {**payload, "number": len(self.issues) + 1, "html_url": f"https://example.test/{len(self.issues) + 1}", "author_association": "OWNER",
                 "state": "open", "labels": [{"name": label} for label in labels]}
        self.issues.append(issue)
        thread_id = cast(str, payload["body"]).split("thread=", 1)[1].split(" ", 1)[0]
        if self.failure_mode == "spoof":
            self._thread(thread_id)["comments"]["nodes"].append({"body": f"<!-- review-closeout-reply:v1 issue={issue['number']} url={issue['html_url']} -->", "author": {"login": "attacker"}})
        if self.failure_mode == "outdated":
            self._thread(thread_id)["isOutdated"] = True
        return issue

    def add_issue_label(self, path: str, label: str) -> object:
        self.label_adds.append((path, label))
        cast(list[dict[str, str]], next(issue for issue in self.issues if path.endswith(f"/{issue['number']}"))["labels"]).append({"name": label})
        if self.failure_mode == "add-lifecycle":
            self.failure_mode = "stale-source-closed-collection"
            raise ReviewCloseoutError("add label response lost")

    def remove_issue_label(self, path: str, label: str) -> object:
        self.label_removes.append((path, label))
        issue = next(issue for issue in self.issues if path.endswith(f"/{issue['number']}"))
        issue["labels"] = [item for item in cast(list[dict[str, str]], issue["labels"]) if item["name"] != label]
        if self.failure_mode == "lifecycle":
            assert self.rest_calls >= 3
            self.failure_mode = "stale-pending-collection"
            raise ReviewCloseoutError("label response lost")

    def reply_thread(self, thread_id: str, body: str) -> object:
        self.replies.append(body)
        self._thread(thread_id)["comments"]["nodes"].append({"body": body, "author": {"login": "Anionix"}})
        if self.failure_mode == "invalid-after-reply":
            self.issues[0]["state"] = "closed"
        if self.failure_mode == "reply":
            self.failure_mode = None
            raise ReviewCloseoutError("reply response lost")

    def resolve_thread(self, thread_id: str) -> object:
        self.resolves.append(thread_id)
        self._thread(thread_id)["isResolved"] = True
        if self.failure_mode == "resolve":
            raise ReviewCloseoutError("resolve response lost")

    def _thread(self, thread_id: str) -> dict[str, Any]:
        nodes = cast(dict[str, Any], self.payload)["data"]["repository"]["pullRequests"]["nodes"]
        return next(thread for pr in nodes for thread in pr["reviewThreads"]["nodes"] if thread["id"] == thread_id)


def test_review_priority_defaults_and_preserves_badge() -> None:
    assert review_priority("P1 Badge") == "P1"
    assert review_priority("P2 Badge\nP1 Badge in a later reply") == "P1"
    assert review_priority("ordinary comment") == "UNCLASSIFIED"
    assert review_priority("P1 is not applicable") == "UNCLASSIFIED"


def test_batch_threshold_is_inclusive() -> None:
    assert not batch_ready(9)
    assert batch_ready(10)


def test_parse_page_preserves_cursor_for_large_repositories() -> None:
    payload = {"data": {"repository": {"pullRequests": {
        "pageInfo": {"hasNextPage": True, "endCursor": "cursor-2"},
        "nodes": [],
    }}}}
    assert _parse_page(payload)[:3] == (0, "cursor-2", True)


def test_current_threads_excludes_resolved_and_outdated() -> None:
    payload = {
        "data": {
            "repository": {
                "pullRequests": {
                    "pageInfo": {"hasNextPage": False},
                    "nodes": [{
                        "id": "pr-230",
                        "number": 230,
                        "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": [
                            {"id": "open", "isResolved": False, "isOutdated": False,
                             "comments": {"pageInfo": {"hasNextPage": False},
                                          "nodes": [{"body": "P2 Badge"}]}},
                            {"id": "resolved", "isResolved": True, "isOutdated": False,
                             "comments": {"pageInfo": {"hasNextPage": False}, "nodes": []}},
                            {"id": "outdated", "isResolved": False, "isOutdated": True,
                             "comments": {"pageInfo": {"hasNextPage": False}, "nodes": []}},
                        ]},
                    }],
                }
            }
        }
    }
    assert _parse_page(payload)[3] == (ReviewThread(230, "open", "P2 Badge"),)


def test_issue_marker_is_idempotency_key() -> None:
    body = f"<!-- {MARKER} repo=Anionix/data-format-lab pr=230 thread=PRRT_1 -->"
    legacy = "<!-- review-closeout:v2 pr=229 thread=PRRT_2 -->"
    pages = [[
        {"number": 1, "html_url": "u1", "state": "open", "labels": OWNER_LABELS, "author_association": "OWNER", "body": body},
        {"number": 2, "html_url": "u2", "state": "open", "labels": OWNER_LABELS, "author_association": "OWNER", "body": legacy},
        {"number": 3, "html_url": "u3", "state": "open", "labels": OWNER_LABELS, "author_association": "COLLABORATOR", "body": body},
        {"number": 4, "html_url": "u4", "state": "open", "labels": [], "user": {"login": "attacker"}, "body": f"<!-- review-closeout:v2 pr={'9' * 4301} thread=T -->"},
        {"body": None},
        {"pull_request": {"url": "ignored"}, "body": body},
    ]]
    assert set(tracked_issues(pages, "Anionix/data-format-lab")) == {(229, "PRRT_2"), (230, "PRRT_1")}
    assert set(tracked_issues(pages, "anionix/data-format-lab")) == {(229, "PRRT_2"), (230, "PRRT_1")}
    pages[0][0]["body"] = body.replace("data-format-lab", "diagnostic-triage")
    with pytest.raises(ReviewCloseoutError, match="repository marker mismatch"):
        tracked_issues(pages, "Anionix/data-format-lab")


def test_duplicate_marker_owners_fail_closed() -> None:
    body = f"<!-- {MARKER} repo=Anionix/data-format-lab pr=230 thread=PRRT_1 -->"
    with pytest.raises(ReviewCloseoutError, match="multiple issues track"):
        tracked_issues([[{"number": 1, "html_url": "u1", "state": "open", "labels": OWNER_LABELS, "author_association": "OWNER", "body": body}],
                        [{"number": 2, "html_url": "u2", "state": "open", "labels": OWNER_LABELS, "author_association": "OWNER", "body": body}]], "Anionix/data-format-lab")
    with pytest.raises(ReviewCloseoutError, match="multiple review threads"):
        tracked_issues([[{"number": 1, "html_url": "u1", "state": "open", "labels": OWNER_LABELS, "author_association": "OWNER",
                          "body": body + "\n<!-- review-closeout:v2 pr=231 thread=PRRT_2 -->"}]], "Anionix/data-format-lab")


def test_issue_payload_exposes_priority_mapping() -> None:
    payload = issue_payload(ReviewThread(230, "PRRT_1", "P1 Badge"), "Anionix/data-format-lab")
    assert payload["labels"] == ["bug", "priority:p1", "bug-class:unclassified",
                                 "source:review", "lifecycle:closeout-pending", "needs-triage"]
    assert "Failure domain: `unclassified`" in cast(str, payload["body"])
    assert f"<!-- {MARKER} repo=Anionix/data-format-lab pr=230 thread=PRRT_1 -->" in cast(str, payload["body"])


def test_run_is_read_only_below_batch_threshold() -> None:
    client = FakeClient(9)
    result = run(client, "Anionix/data-format-lab")
    assert result["status"] == "NOOP_BELOW_BATCH_THRESHOLD"
    assert client.created == []
    assert run(FakeClient(), "Anionix/data-format-lab")["status"] == "NOOP_NO_CURRENT_THREADS"


def test_run_creates_one_issue_per_current_thread_after_threshold() -> None:
    client = FakeClient(10)
    result = run(client, "Anionix/data-format-lab")
    assert result["status"] == "THREADS_CLOSED"
    assert len(client.created) == 10


def test_run_uses_targeted_issue_readback_after_writes() -> None:
    client = FakeClient(2)
    client.failure_mode = "stale-collection"
    result = run(client, "Anionix/data-format-lab", minimum=1)
    assert result["status"] == "THREADS_CLOSED"
    assert sum("?state=all" in path for path in client.rest_paths) == 1
    assert {path.rsplit("/", 1)[-1] for path in client.rest_paths if "/issues/" in path} == {"1", "2"}


def test_invalid_targeted_readback_stops_before_next_creation() -> None:
    client = FakeClient(2)
    client.failure_mode = "closed-readback"
    with pytest.raises(ReviewCloseoutError, match="not an open classified bug"):
        run(client, "Anionix/data-format-lab", minimum=1)
    assert len(client.created) == 1


def test_existing_issue_classification_must_match_source() -> None:
    client = FakeClient(2)
    client.create_issue("", issue_payload(ReviewThread(1, "thread-1", "P3 Badge"), "Anionix/data-format-lab"))
    client.created.clear()
    with pytest.raises(ReviewCloseoutError, match="not an open classified bug"):
        run(client, "Anionix/data-format-lab", minimum=1)
    assert client.created == []
    cast(list[dict[str, str]], client.issues[0]["labels"])[:] = [{"name": name} for name in ("bug", "priority:p2", "bug-class:unclassified", "lifecycle:tracked", "needs-triage")]
    with pytest.raises(ReviewCloseoutError, match="not an open classified bug"):
        run(client, "Anionix/data-format-lab", minimum=1)


def test_non_owner_writer_fails_before_mutation() -> None:
    client = FakeClient(1)
    client.actor = "rotated-writer"
    with pytest.raises(ReviewCloseoutError, match="repository owner"):
        run(client, "Anionix/data-format-lab", minimum=1)
    assert client.created == []
    assert client.graphql_calls == 0


def test_partial_mutations_resume_monotonically() -> None:
    client = FakeClient(1)
    client.failure_mode = "reply"
    with pytest.raises(ReviewCloseoutError, match="reply response lost"):
        run(client, "Anionix/data-format-lab", minimum=1)
    assert (len(client.issues), len(client.replies), client.resolves) == (1, 1, [])
    client.failure_mode = "resolve"
    with pytest.raises(ReviewCloseoutError, match="resolve response lost"):
        run(client, "Anionix/data-format-lab", minimum=1)
    client.rest_calls, client.failure_mode = 1, "lifecycle"
    with pytest.raises(ReviewCloseoutError, match="label response lost"):
        run(client, "Anionix/data-format-lab", minimum=1)
    assert (run(client, "Anionix/data-format-lab", minimum=1)["status"], len(client.replies), len(client.resolves)) == ("THREADS_CLOSED", 1, 1)
    assert len(client.label_removes) == 1
    for mode, expected in (("spoof", (1, 1)), ("outdated", (0, 0))):
        client = FakeClient(1)
        client.failure_mode = mode
        assert (run(client, "Anionix/data-format-lab", minimum=1)["status"], len(client.replies), len(client.resolves)) == ("THREADS_CLOSED", *expected)

    client = FakeClient(1)
    client.failure_mode = "add-lifecycle"
    with pytest.raises(ReviewCloseoutError, match="add label response lost"):
        run(client, "Anionix/data-format-lab", minimum=1)
    assert run(client, "Anionix/data-format-lab", minimum=1)["status"] == "THREADS_CLOSED"
    assert len(client.label_adds) == 1


def test_reply_revalidates_issue_before_resolution() -> None:
    client = FakeClient(1)
    client.failure_mode = "invalid-after-reply"
    with pytest.raises(ReviewCloseoutError, match="not an open classified bug"):
        run(client, "Anionix/data-format-lab", minimum=1)
    assert (len(client.replies), len(client.resolves)) == (1, 0)


def test_reply_revalidates_issue_after_thread_read() -> None:
    client = FakeClient(1)
    client.failure_mode = "invalid-before-reply"
    with pytest.raises(ReviewCloseoutError, match="not an open classified bug"):
        run(client, "Anionix/data-format-lab", minimum=1)
    assert (len(client.replies), len(client.resolves)) == (0, 0)


def test_p1_bypasses_threshold_without_releasing_p2() -> None:
    client = FakeClient(2)
    payload = cast(dict[str, Any], client.payload)
    payload["data"]["repository"]["pullRequests"]["nodes"][0]["reviewThreads"]["nodes"][0]["comments"]["nodes"][0]["body"] = "P1 Badge"
    result = run(client, "Anionix/data-format-lab")
    assert result["created_issue_numbers"] == [1]


def test_nested_connections_are_paginated_to_exhaustion() -> None:
    client = FakeClient()
    initial = {"data": {"repository": {"pullRequests": {
        "pageInfo": {"hasNextPage": False}, "nodes": [{
            "id": "pr-230", "number": 230,
            "reviewThreads": {"pageInfo": {"hasNextPage": True, "endCursor": "threads-1"}, "nodes": [
                {"id": "thread-0", "isResolved": False, "isOutdated": False,
                 "comments": {"pageInfo": {"hasNextPage": False}, "nodes": [{"body": "page 1"}]}},
            ]},
        }],
    }}}}
    client.pages = [
        {"data": {"node": {"reviewThreads": {
            "pageInfo": {"hasNextPage": False},
            "nodes": [{"id": "thread-1", "isResolved": False, "isOutdated": False,
                       "comments": {"pageInfo": {"hasNextPage": True, "endCursor": "comments-1"},
                                    "nodes": [{"body": "P1 Badge"}]}}],
        }}}},
        {"data": {"node": {"comments": {
            "pageInfo": {"hasNextPage": False}, "nodes": [{"body": "page 2"}],
        }}}},
    ]
    assert _parse_page(initial, client)[3] == (
        ReviewThread(230, "thread-0", "page 1"),
        ReviewThread(230, "thread-1", "P1 Badge\npage 2"),
    )
