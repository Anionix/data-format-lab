from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from review_closeout import (
    MARKER,
    ReviewThread,
    batch_ready,
    _parse_page,
    issue_payload,
    marked_issue_bodies,
    review_priority,
    run,
)


class FakeClient:
    def __init__(self, merged_count: int = 0) -> None:
        self.created: list[dict[str, object]] = []
        self.payload = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [
                            {
                                "number": number,
                                "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": [{
                                    "id": f"thread-{number}",
                                    "isResolved": False,
                                    "isOutdated": False,
                                    "comments": {"nodes": [{"body": "P2 Badge"}]},
                                }]},
                            }
                            for number in range(1, merged_count + 1)
                        ],
                    }
                }
            }
        }

    def graphql(self, query: str, fields: dict[str, str | None]) -> object:
        return self.payload

    def rest(self, path: str) -> object:
        return [[]]

    def create_issue(self, path: str, payload: dict[str, object]) -> object:
        self.created.append(payload)
        return {"number": len(self.created)}


def test_review_priority_defaults_and_preserves_badge() -> None:
    assert review_priority("P1 Badge") == "P1"
    assert review_priority("P2 Badge\nP1 Badge in a later reply") == "P1"
    assert review_priority("ordinary comment") == "P2"


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
                        "number": 230,
                        "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": [
                            {"id": "open", "isResolved": False, "isOutdated": False,
                             "comments": {"nodes": [{"body": "P2 Badge"}]}},
                            {"id": "resolved", "isResolved": True, "isOutdated": False,
                             "comments": {"nodes": []}},
                            {"id": "outdated", "isResolved": False, "isOutdated": True,
                             "comments": {"nodes": []}},
                        ]},
                    }],
                }
            }
        }
    }
    assert _parse_page(payload)[3] == (ReviewThread(230, "open", "P2 Badge"),)


def test_issue_marker_is_idempotency_key() -> None:
    body = f"<!-- {MARKER} pr=230 thread=PRRT_1 -->"
    legacy = "<!-- review-followup:v1 source=PR-229 thread=PRRT_2 -->"
    pages = [[
        {"body": body},
        {"body": legacy},
        {"body": None},
        {"pull_request": {"url": "ignored"}, "body": body},
    ]]
    assert marked_issue_bodies(pages) == frozenset({(229, "PRRT_2"), (230, "PRRT_1")})


def test_issue_payload_exposes_priority_mapping() -> None:
    payload = issue_payload(ReviewThread(230, "PRRT_1", "P1 Badge"), "Anionix/data-format-lab")
    assert payload["labels"] == ["bug", "priority:p1", "ready-for-agent"]
    assert "priority:p1" in payload["body"]


def test_run_is_read_only_below_batch_threshold() -> None:
    client = FakeClient(9)
    result = run(client, "Anionix/data-format-lab")
    assert result["status"] == "NOOP_BELOW_BATCH_THRESHOLD"
    assert client.created == []


def test_run_creates_one_issue_per_current_thread_after_threshold() -> None:
    client = FakeClient(10)
    result = run(client, "Anionix/data-format-lab")
    assert result["status"] == "ISSUES_CREATED"
    assert len(client.created) == 10
