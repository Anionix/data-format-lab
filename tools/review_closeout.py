"""Batch-detect unresolved review threads on merged pull requests."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from typing import Protocol, cast

MARKER = "data-format-lab-review-closeout:v1"
MARKERS = (
    re.compile(r"<!-- " + re.escape(MARKER) + r" pr=(\d+) thread=([^ ]+) -->"),
    re.compile(r"<!-- review-followup:v1 source=PR-(\d+) thread=([^ ]+) -->"),
)
PRIORITY_RE = re.compile(r"\bP([0-3])\b")

# LLM contract: REVIEW_DISCOVERED -> ISSUE_TRACKED -> HUMAN_CLOSED.
# The scheduled workflow never advances the final state automatically.


class ReviewCloseoutError(RuntimeError):
    """The scheduled review sweep could not produce a trustworthy result."""


@dataclass(frozen=True)
class ReviewThread:
    pull_request: int
    thread_id: str
    body: str


class GitHubClient(Protocol):
    def graphql(self, query: str, fields: dict[str, str | None]) -> object: ...
    def rest(self, path: str) -> object: ...
    def create_issue(self, path: str, payload: dict[str, object]) -> object: ...


class GhClient:
    def _call(self, args: list[str], payload: dict[str, object] | None = None) -> object:
        result = subprocess.run(
            ["gh", "api", *args], input=json.dumps(payload) if payload is not None else None,
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise ReviewCloseoutError(result.stderr.strip() or "gh api failed")
        try:
            return json.loads(result.stdout) if result.stdout.strip() else None
        except json.JSONDecodeError as error:
            raise ReviewCloseoutError("gh api returned invalid JSON") from error

    def graphql(self, query: str, fields: dict[str, str | None]) -> object:
        args = ["graphql", "-f", f"query={query}"]
        for key, value in fields.items():
            args += ["-F" if value is None else "-f", f"{key}={'null' if value is None else value}"]
        return self._call(args)

    def rest(self, path: str) -> object:
        return self._call(["--paginate", "--slurp", path])

    def create_issue(self, path: str, payload: dict[str, object]) -> object:
        return self._call([path, "--method", "POST", "--input", "-"], payload)


def _obj(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ReviewCloseoutError(f"{context} must be an object")
    raw = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise ReviewCloseoutError(f"{context} must have string keys")
    return {cast(str, key): item for key, item in raw.items()}


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise ReviewCloseoutError(f"{context} must be a list")
    return cast(list[object], value)


def _text(value: object, context: str) -> str:
    if not isinstance(value, str):
        raise ReviewCloseoutError(f"{context} must be a string")
    return value


def review_priority(body: str) -> str:
    priorities = [int(value) for value in PRIORITY_RE.findall(body)]
    return f"P{min(priorities)}" if priorities else "P2"


def batch_ready(merged_with_threads: int, minimum: int = 10) -> bool:
    return merged_with_threads >= minimum


def _parse_page(payload: object) -> tuple[int, str | None, bool, tuple[ReviewThread, ...]]:
    root = _obj(_obj(payload, "GraphQL response").get("data"), "data")
    repository = _obj(root.get("repository"), "repository")
    pull_requests = _obj(repository.get("pullRequests"), "pullRequests")
    page_info = _obj(pull_requests.get("pageInfo"), "pullRequests.pageInfo")
    has_next = page_info.get("hasNextPage") is True
    cursor = page_info.get("endCursor")
    if cursor is not None and not isinstance(cursor, str):
        raise ReviewCloseoutError("pull request page cursor must be a string or null")
    merged = 0
    current: list[ReviewThread] = []
    for raw_pr in _list(pull_requests.get("nodes"), "pullRequests.nodes"):
        pr = _obj(raw_pr, "pull request")
        number = pr.get("number")
        if type(number) is not int:
            raise ReviewCloseoutError("pull request number must be an integer")
        threads = _obj(pr.get("reviewThreads"), "reviewThreads")
        if _obj(threads.get("pageInfo"), "reviewThreads.pageInfo").get("hasNextPage") is True:
            raise ReviewCloseoutError(f"PR #{number} has more than 100 review threads")
        nodes = _list(threads.get("nodes"), "reviewThreads.nodes")
        merged += bool(nodes)
        for raw_thread in nodes:
            thread = _obj(raw_thread, "review thread")
            if thread.get("isResolved") or thread.get("isOutdated"):
                continue
            comments = _list(_obj(thread.get("comments"), "comments").get("nodes"), "comments.nodes")
            body = "\n".join(_text(_obj(comment, "review comment").get("body"), "body") for comment in comments)
            current.append(ReviewThread(number, _text(thread.get("id"), "thread.id"), body))
    if has_next and not cursor:
        raise ReviewCloseoutError("merged pull request page has no end cursor")
    return merged, cursor, has_next, tuple(current)


def merged_review_threads(client: GitHubClient, repository: str) -> tuple[int, tuple[ReviewThread, ...]]:
    owner, name = repository.split("/", 1)
    query = """
    query($owner:String!, $name:String!, $after:String) {
      repository(owner:$owner, name:$name) {
        pullRequests(first:100, after:$after, states:MERGED, orderBy:{field:UPDATED_AT, direction:DESC}) {
          pageInfo { hasNextPage endCursor }
          nodes { number reviewThreads(first:100) {
            pageInfo { hasNextPage }
            nodes { id isResolved isOutdated comments(first:20) { nodes { body } } }
          } }
        }
      }
    }
    """
    cursor: str | None = None
    merged = 0
    current: list[ReviewThread] = []
    while True:
        page_merged, cursor, has_next, page_current = _parse_page(
            client.graphql(query, {"owner": owner, "name": name, "after": cursor})
        )
        merged += page_merged
        current.extend(page_current)
        if not has_next:
            return merged, tuple(current)


def marked_issue_bodies(payload: object) -> frozenset[tuple[int, str]]:
    found: set[tuple[int, str]] = set()
    for page in _list(payload, "issues pages"):
        for raw_issue in _list(page, "issues page"):
            issue = _obj(raw_issue, "issue")
            body = issue.get("body")
            if "pull_request" in issue or not isinstance(body, str):
                continue
            for pattern in MARKERS:
                found.update((int(match.group(1)), match.group(2)) for match in pattern.finditer(body))
    return frozenset(found)


def issue_payload(thread: ReviewThread, repository: str) -> dict[str, object]:
    priority = review_priority(thread.body)
    marker = f"<!-- {MARKER} pr={thread.pull_request} thread={thread.thread_id} -->"
    return {
        "title": f"[{priority} review follow-up] PR #{thread.pull_request} thread",
        "body": (
            "## Review follow-up\n\n"
            f"A scheduled sweep found a current unresolved review thread on "
            f"[PR #{thread.pull_request}](https://github.com/{repository}/pull/{thread.pull_request}).\n\n"
            f"**Review priority:** `{priority}`  \n**Canonical label:** `priority:{priority.lower()}`  \n"
            f"**Thread ID:** `{thread.thread_id}`\n\n"
            "Reply to the source thread, resolve or mark it outdated after the fix, "
            "and use a new non-stacked PR from the latest `origin/main`.\n\n"
            f"{marker}"
        ),
        "labels": ["bug", f"priority:{priority.lower()}", "ready-for-agent"],
    }


def run(client: GitHubClient, repository: str, minimum: int = 10) -> dict[str, object]:
    merged, current = merged_review_threads(client, repository)
    result: dict[str, object] = {
        "schema_version": "review_closeout/v1", "repository": repository,
        "merged_pull_requests_with_threads": merged, "minimum": minimum,
        "candidate_count": len(current), "created_issue_numbers": [],
        "status": "NOOP_BELOW_BATCH_THRESHOLD",
    }
    if not batch_ready(merged, minimum):
        return result
    marked = marked_issue_bodies(client.rest(f"repos/{repository}/issues?state=all&per_page=100"))
    created: list[int] = []
    for thread in current:
        if (thread.pull_request, thread.thread_id) in marked:
            continue
        issue = _obj(client.create_issue(f"repos/{repository}/issues", issue_payload(thread, repository)), "created issue")
        number = issue.get("number")
        if type(number) is not int:
            raise ReviewCloseoutError("created issue number must be an integer")
        created.append(number)
    result["created_issue_numbers"] = created
    result["status"] = "ISSUES_CREATED" if created else "NOOP_ALREADY_TRACKED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--min-merged-with-threads", type=int, default=10)
    args = parser.parse_args()
    if "/" not in args.repo or args.min_merged_with_threads < 1:
        parser.error("--repo must be owner/name and the threshold must be positive")
    try:
        print(json.dumps(run(GhClient(), args.repo, args.min_merged_with_threads), indent=2))
    except ReviewCloseoutError as error:
        print(f"review closeout failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
