"""Batch-detect unresolved review threads on merged pull requests."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from typing import Protocol, cast

MARKER = "review-closeout:v3"
MARKERS = (
    re.compile(r"<!-- review-closeout:v2 pr=([0-9]{1,10}) thread=([^ ]+) -->"),
    re.compile(r"<!-- data-format-lab-review-closeout:v1 pr=([0-9]{1,10}) thread=([^ ]+) -->"),
    re.compile(r"<!-- review-followup:v1 source=PR-([0-9]{1,10}) thread=([^ ]+) -->"),
)
MARKER_RE = re.compile(r"<!-- " + re.escape(MARKER) + r" repo=([^ ]+) pr=([0-9]{1,10}) thread=([^ ]+) -->")
PRIORITY_RE = re.compile(r"(?:!\[|^|\n)P([0-3]) Badge\b")
AXES = ("priority:", "bug-class:", "source:", "lifecycle:")
THREAD_PAGE_QUERY = """
query($node:ID!, $after:String) {
  node(id:$node) { ... on PullRequest {
    reviewThreads(first:100, after:$after) {
      pageInfo { hasNextPage endCursor }
      nodes { id isResolved isOutdated comments(first:100) {
        pageInfo { hasNextPage endCursor } nodes { body }
      } }
    }
  } }
}
"""
COMMENT_PAGE_QUERY = """
query($node:ID!, $after:String) {
  node(id:$node) { ... on PullRequestReviewThread {
    comments(first:100, after:$after) {
      pageInfo { hasNextPage endCursor } nodes { body }
    }
  } }
}
"""

# LLM contract: REVIEW_DISCOVERED -> CLASSIFIED -> ISSUE_TRACKED -> HUMAN_CLOSED.
# The scheduled workflow never advances the final state automatically.


class ReviewCloseoutError(RuntimeError):
    """The scheduled review sweep could not produce a trustworthy result."""


@dataclass(frozen=True)
class ReviewThread:
    pull_request: int
    thread_id: str
    body: str


@dataclass(frozen=True)
class TrackedIssue:
    number: int
    url: str
    state: str
    labels: frozenset[str]


class GitHubClient(Protocol):
    def graphql(self, query: str, fields: dict[str, str | None]) -> object: ...
    def rest(self, path: str) -> object: ...
    def create_issue(self, path: str, payload: dict[str, object]) -> object: ...
    def current_user(self) -> str: ...


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

    def current_user(self) -> str:
        return _text(_obj(self._call(["user"]), "viewer").get("login"), "viewer.login")


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


def _classified(labels: frozenset[str]) -> bool:
    return {"bug", "source:review"} <= labels and all(
        sum(label.startswith(prefix) for label in labels) == 1 for prefix in AXES
    )


def _connection_nodes(
    client: GitHubClient | None, initial: dict[str, object], node_id: str, field: str, query: str,
) -> tuple[object, ...]:
    connection = initial
    result: list[object] = []
    seen: set[str] = set()
    while True:
        page_info = _obj(connection.get("pageInfo"), f"{field}.pageInfo")
        result.extend(_list(connection.get("nodes"), f"{field}.nodes"))
        if page_info.get("hasNextPage") is not True:
            return tuple(result)
        cursor = _text(page_info.get("endCursor"), f"{field}.endCursor")
        if client is None or cursor in seen:
            raise ReviewCloseoutError(f"{field} pagination cannot advance")
        seen.add(cursor)
        response = _obj(client.graphql(query, {"node": node_id, "after": cursor}), f"{field} response")
        data = _obj(response.get("data"), f"{field} data")
        connection = _obj(_obj(data.get("node"), f"{field} node").get(field), field)


def review_priority(body: str) -> str:
    priorities = [int(value) for value in PRIORITY_RE.findall(body)]
    return f"P{min(priorities)}" if priorities else "UNCLASSIFIED"


def batch_ready(merged_with_threads: int, minimum: int = 10) -> bool:
    return merged_with_threads >= minimum


def _parse_page(
    payload: object, client: GitHubClient | None = None,
) -> tuple[int, str | None, bool, tuple[ReviewThread, ...]]:
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
        pr_id = _text(pr.get("id"), "pull request id")
        threads = _connection_nodes(
            client, _obj(pr.get("reviewThreads"), "reviewThreads"), pr_id,
            "reviewThreads", THREAD_PAGE_QUERY,
        )
        merged += bool(threads)
        for raw_thread in threads:
            thread = _obj(raw_thread, "review thread")
            if thread.get("isResolved") or thread.get("isOutdated"):
                continue
            thread_id = _text(thread.get("id"), "thread.id")
            comments = _connection_nodes(
                client, _obj(thread.get("comments"), "comments"), thread_id,
                "comments", COMMENT_PAGE_QUERY,
            )
            body = "\n".join(_text(_obj(comment, "review comment").get("body"), "body") for comment in comments)
            current.append(ReviewThread(number, thread_id, body))
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
          nodes { id number reviewThreads(first:100) {
            pageInfo { hasNextPage endCursor }
            nodes { id isResolved isOutdated comments(first:20) {
              pageInfo { hasNextPage endCursor } nodes { body }
            } }
          } }
        }
      }
    }
    """
    cursor: str | None = None
    merged = 0
    current: list[ReviewThread] = []
    seen: set[str] = set()
    while True:
        page_merged, cursor, has_next, page_current = _parse_page(
            client.graphql(query, {"owner": owner, "name": name, "after": cursor}), client
        )
        merged += page_merged
        current.extend(page_current)
        if not has_next:
            return merged, tuple(current)
        if cursor is None or cursor in seen:
            raise ReviewCloseoutError("merged pull request pagination cannot advance")
        seen.add(cursor)


def tracked_issues(payload: object, repository: str) -> dict[tuple[int, str], TrackedIssue]:
    found: dict[tuple[int, str], TrackedIssue] = {}
    for page in _list(payload, "issues pages"):
        for raw_issue in _list(page, "issues page"):
            issue = _obj(raw_issue, "issue")
            body = issue.get("body")
            if "pull_request" in issue or not isinstance(body, str):
                continue
            legacy = tuple(match for pattern in MARKERS for match in pattern.finditer(body))
            scoped = tuple(MARKER_RE.finditer(body))
            if not legacy and not scoped:
                continue
            labels = frozenset(_text(_obj(label, "issue label").get("name"), "label name")
                               for label in _list(issue.get("labels"), "issue labels"))
            if issue.get("author_association") != "OWNER":
                continue
            # Ownership requires the repository owner; marker text and mutable labels are not provenance.
            keys = {(int(match.group(1)), match.group(2)) for match in legacy}
            for match in scoped:
                if match.group(1).casefold() != repository.casefold():
                    raise ReviewCloseoutError("tracked issue repository marker mismatch")
                keys.add((int(match.group(2)), match.group(3)))
            if len(keys) > 1:
                raise ReviewCloseoutError("one issue cannot own multiple review threads")
            if not keys:
                continue
            number = issue.get("number")
            if type(number) is not int:
                raise ReviewCloseoutError("tracked issue number must be an integer")
            tracked = TrackedIssue(number, _text(issue.get("html_url"), "tracked issue URL"),
                                   _text(issue.get("state"), "tracked issue state"), labels)
            for key in keys:
                if key in found and found[key] != tracked:
                    raise ReviewCloseoutError(f"multiple issues track PR #{key[0]} thread {key[1]}")
                found[key] = tracked
    return found


def _validate_issue(issue: TrackedIssue, priority: str) -> None:
    required = {"bug", "source:review", "lifecycle:tracked", f"priority:{priority.lower()}"}
    if issue.state != "open" or not required <= issue.labels or not _classified(issue.labels) or (
        "bug-class:unclassified" in issue.labels and "needs-triage" not in issue.labels
    ):
        raise ReviewCloseoutError(f"issue #{issue.number} is not an open classified bug")


def issue_payload(thread: ReviewThread, repository: str) -> dict[str, object]:
    priority = review_priority(thread.body)
    marker = f"<!-- {MARKER} repo={repository} pr={thread.pull_request} thread={thread.thread_id} -->"
    return {
        "title": f"[{priority} review follow-up] PR #{thread.pull_request} thread",
        "body": (
            "## Review follow-up\n\n"
            f"A scheduled sweep found a current unresolved review thread on "
            f"[PR #{thread.pull_request}](https://github.com/{repository}/pull/{thread.pull_request}).\n\n"
            "### Classification\n\n"
            f"- Priority: `{priority}`\n- Failure domain: `unclassified`\n"
            f"- Source: `review`\n- Lifecycle: `tracked`\n- Thread ID: `{thread.thread_id}`\n\n"
            "Reply to the source thread, resolve or mark it outdated after the fix, "
            "and use a new non-stacked PR from the latest `origin/main`.\n\n"
            f"{marker}"
        ),
        "labels": ["bug", f"priority:{priority.lower()}", "bug-class:unclassified",
                   "source:review", "lifecycle:tracked", "needs-triage"],
    }


def run(client: GitHubClient, repository: str, minimum: int = 10) -> dict[str, object]:
    actor = client.current_user()
    if actor.casefold() != repository.split("/", 1)[0].casefold():
        raise ReviewCloseoutError("review closeout must run as the repository owner")
    merged, current = merged_review_threads(client, repository)
    result: dict[str, object] = {
        "schema_version": "review_closeout/v1", "repository": repository,
        "merged_pull_requests_with_threads": merged, "minimum": minimum,
        "candidate_count": len(current), "created_issue_numbers": [],
        "status": "NOOP_NO_CURRENT_THREADS" if not current else "NOOP_BELOW_BATCH_THRESHOLD",
    }
    eligible = current if batch_ready(merged, minimum) else tuple(
        thread for thread in current if review_priority(thread.body) in {"P0", "P1"}
    )
    if not eligible:
        return result
    issues_path = f"repos/{repository}/issues?state=all&per_page=100"
    tracked = tracked_issues(client.rest(issues_path), repository)
    marked = set(tracked)
    for thread in eligible:
        issue = tracked.get((thread.pull_request, thread.thread_id))
        if issue is not None:
            _validate_issue(issue, review_priority(thread.body))
    created: list[int] = []
    for thread in eligible:
        if (thread.pull_request, thread.thread_id) in marked:
            continue
        issue = _obj(client.create_issue(f"repos/{repository}/issues", issue_payload(thread, repository)), "created issue")
        number = issue.get("number")
        if type(number) is not int:
            raise ReviewCloseoutError("created issue number must be an integer")
        created.append(number)
        marked.add((thread.pull_request, thread.thread_id))
    if created:
        tracked = tracked_issues(client.rest(issues_path), repository)
    for thread in eligible:
        issue = tracked.get((thread.pull_request, thread.thread_id))
        if issue is None:
            raise ReviewCloseoutError(f"PR #{thread.pull_request} thread has no tracked issue")
        _validate_issue(issue, review_priority(thread.body))
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
