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
REPLY_RE = re.compile(r"<!-- review-closeout-reply:v1 issue=([0-9]{1,10}) url=([^\s]+) -->")
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
      pageInfo { hasNextPage endCursor } nodes { body author { login } }
    }
  } }
}
"""
THREAD_READ_QUERY = "query($node:ID!){node(id:$node){...on PullRequestReviewThread{id isResolved isOutdated pullRequest{number repository{nameWithOwner}} comments(first:100){pageInfo{hasNextPage endCursor}nodes{body author{login}}}}}}"

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
    def add_issue_label(self, path: str, label: str) -> object: ...
    def remove_issue_label(self, path: str, label: str) -> object: ...
    def reply_thread(self, thread_id: str, body: str) -> object: ...
    def resolve_thread(self, thread_id: str) -> object: ...


class GhClient:
    def _call(self, args: list[str], payload: dict[str, object] | None = None) -> object:
        result = subprocess.run(
            ["gh", "api", *args],
            input=json.dumps(payload, allow_nan=False) if payload is not None else None,
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

    def add_issue_label(self, path: str, label: str) -> object:
        return self._call([f"{path}/labels", "--method", "POST", "--input", "-"], {"labels": [label]})

    def remove_issue_label(self, path: str, label: str) -> object:
        return self._call([f"{path}/labels/{label}", "--method", "DELETE"])

    def reply_thread(self, thread_id: str, body: str) -> object:
        return self.graphql("mutation($thread:ID!,$body:String!){addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$thread,body:$body}){comment{id}}}", {"thread": thread_id, "body": body})

    def resolve_thread(self, thread_id: str) -> object:
        return self.graphql("mutation($thread:ID!){resolveReviewThread(input:{threadId:$thread}){thread{id}}}", {"thread": thread_id})


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
        if page_info.get("hasNextPage") is False:
            return tuple(result)
        if page_info.get("hasNextPage") is not True:
            raise ReviewCloseoutError(f"{field}.hasNextPage must be a boolean")
        cursor = _text(page_info.get("endCursor"), f"{field}.endCursor")
        if client is None or cursor in seen:
            raise ReviewCloseoutError(f"{field} pagination cannot advance")
        seen.add(cursor)
        response = _obj(client.graphql(query, {"node": node_id, "after": cursor}), f"{field} response")
        data = _obj(response.get("data") if not response.get("errors") else None, f"{field} data")
        connection = _obj(_obj(data.get("node"), f"{field} node").get(field), field)


def _read_thread(client: GitHubClient, thread_id: str, repository: str, pull_request: int) -> tuple[bool, bool, str, str]:
    response = _obj(client.graphql(THREAD_READ_QUERY, {"node": thread_id}), "thread response")
    data = _obj(response.get("data") if not response.get("errors") else None, "thread data")
    node = _obj(data.get("node"), "thread node")
    source = _obj(node.get("pullRequest"), "thread pull request")
    if node.get("id") != thread_id or type(source.get("number")) is not int or source.get("number") != pull_request or _text(_obj(source.get("repository"), "thread repository").get("nameWithOwner"), "thread repository name").casefold() != repository.casefold():
        raise ReviewCloseoutError(f"thread {thread_id} readback identity mismatch")
    comments = _connection_nodes(client, _obj(node.get("comments"), "comments"), thread_id, "comments", COMMENT_PAGE_QUERY)
    parts: list[tuple[str, bool]] = []
    for comment in comments:
        item = _obj(comment, "review comment")
        body = _text(item.get("body"), "body")
        author = item.get("author")
        login = cast(dict[object, object], author).get("login") if isinstance(author, dict) else None
        is_reply = REPLY_RE.search(body) is not None and isinstance(login, str) and login.casefold() == repository.split("/", 1)[0].casefold()
        parts.append((body, is_reply))
    resolved, outdated = node.get("isResolved"), node.get("isOutdated")
    if type(resolved) is not bool or type(outdated) is not bool:
        raise ReviewCloseoutError("thread closed states must be booleans")
    return resolved, outdated, "\n".join(body for body, _ in parts), "\n".join(body for body, is_reply in parts if is_reply)


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


def _read_tracked_issue(
    client: GitHubClient, repository: str, key: tuple[int, str], number: int
) -> TrackedIssue:
    payload = _list(
        client.rest(f"repos/{repository}/issues/{number}"),
        f"issue #{number} targeted readback",
    )
    found = tracked_issues([payload], repository)
    if set(found) != {key} or found[key].number != number:
        raise ReviewCloseoutError(f"issue #{number} targeted identity mismatch")
    return found[key]


def _validate_issue(issue: TrackedIssue, lifecycle: str, priority: str | None = None) -> None:
    lifecycles = {label for label in issue.labels if label.startswith("lifecycle:")}
    expected = {f"lifecycle:{lifecycle}"} | ({"lifecycle:source-closed"} if "lifecycle:source-closed" in issue.labels else set[str]())
    required = {"bug", "source:review", f"lifecycle:{lifecycle}"} | ({f"priority:{priority.lower()}"} if priority else set[str]())
    normalized = frozenset(issue.labels - {"lifecycle:source-closed"} | {f"lifecycle:{lifecycle}"})
    if issue.state != "open" or not required <= issue.labels or lifecycles != expected or not _classified(normalized) or (
        "bug-class:unclassified" in issue.labels and "needs-triage" not in issue.labels
    ):
        raise ReviewCloseoutError(f"issue #{issue.number} is not an open classified bug")


def _read_valid_pending_issue(
    client: GitHubClient,
    repository: str,
    key: tuple[int, str],
    expected: TrackedIssue,
    priority: str,
) -> TrackedIssue:
    current = _read_tracked_issue(client, repository, key, expected.number)
    if current.url != expected.url:
        raise ReviewCloseoutError(f"PR #{key[0]} targeted issue URL mismatch")
    _validate_issue(current, "closeout-pending", priority)
    return current


def _validate_link(body: str, issue: TrackedIssue) -> None:
    if (links := [(int(number), url) for number, url in REPLY_RE.findall(body)]) != [(issue.number, issue.url)]:
        raise ReviewCloseoutError(f"thread has {len(links)} non-canonical tracking replies")


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
            f"- Source: `review`\n- Thread ID: `{thread.thread_id}`\n\n"
            "Automation owns source-thread closeout; implement the fix "
            "and use a new non-stacked PR from the latest `origin/main`.\n\n"
            f"{marker}"
        ),
        "labels": ["bug", f"priority:{priority.lower()}", "bug-class:unclassified",
                   "source:review", "lifecycle:closeout-pending", "needs-triage"],
    }


def _repository_labels(payload: object) -> frozenset[str]:
    labels: set[str] = set()
    for page_number, page in enumerate(_list(payload, "repository label pages"), start=1):
        for raw_label in _list(page, f"repository label page {page_number}"):
            name = _text(_obj(raw_label, "repository label").get("name"),
                         "repository label name")
            if not name:
                raise ReviewCloseoutError("repository label name cannot be empty")
            canonical = name.casefold()
            if canonical in labels:
                raise ReviewCloseoutError(f"repository label pagination repeated {name}")
            labels.add(canonical)
    return frozenset(labels)


def _preflight_issue_labels(
    client: GitHubClient, repository: str, threads: tuple[ReviewThread, ...]
) -> None:
    required = {"lifecycle:source-closed"}
    for thread in threads:
        required.update(
            _text(label, "issue payload label")
            for label in _list(issue_payload(thread, repository).get("labels"), "issue payload labels")
        )
    available = _repository_labels(client.rest(f"repos/{repository}/labels?per_page=100"))
    if missing := sorted(required - available):
        raise ReviewCloseoutError(f"missing required labels: {', '.join(missing)}")


def run(client: GitHubClient, repository: str, minimum: int = 10) -> dict[str, object]:
    actor = client.current_user()
    if actor.casefold() != repository.split("/", 1)[0].casefold():
        raise ReviewCloseoutError("review closeout must run as the repository owner")
    merged, current = merged_review_threads(client, repository)
    result: dict[str, object] = {
        "schema_version": "review_closeout/v2", "repository": repository,
        "merged_pull_requests_with_threads": merged, "minimum": minimum,
        "candidate_count": len(current), "created_issue_numbers": [],
        "status": "NOOP_NO_CURRENT_THREADS" if not current else "NOOP_BELOW_BATCH_THRESHOLD",
    }
    eligible = current if batch_ready(merged, minimum) else tuple(
        thread for thread in current if review_priority(thread.body) in {"P0", "P1"}
    )
    issues_path = f"repos/{repository}/issues?state=all&per_page=100"
    tracked = tracked_issues(client.rest(issues_path), repository)
    current_by_key = {(thread.pull_request, thread.thread_id): thread for thread in current}
    recovery = tuple(ReviewThread(pr, thread_id, "") for (pr, thread_id), issue in tracked.items()
                     if "lifecycle:closeout-pending" in issue.labels and (pr, thread_id) not in current_by_key)
    work = {(thread.pull_request, thread.thread_id): thread for thread in recovery + eligible}
    if not work:
        return result
    for key, thread in current_by_key.items():
        issue = tracked.get(key)
        if issue is None:
            continue
        _validate_issue(issue, "closeout-pending", review_priority(thread.body))
        if "lifecycle:source-closed" in issue.labels:
            raise ReviewCloseoutError("source-closed issue has an open thread")
    eligible_keys = {(thread.pull_request, thread.thread_id) for thread in eligible}
    for key, thread in work.items():
        if key in current_by_key:
            continue
        issue = tracked.get(key)
        if issue is not None:
            _validate_issue(issue, "closeout-pending", review_priority(thread.body) if key in eligible_keys else None)
    # LLM contract: LABELS_DECLARED -> PAGES_VALIDATED -> MUTATIONS_ALLOWED.
    _preflight_issue_labels(client, repository, tuple(work.values()))
    created: list[int] = []
    for key, thread in work.items():
        if key not in eligible_keys or key in tracked:
            continue
        issue = _obj(client.create_issue(f"repos/{repository}/issues", issue_payload(thread, repository)), "created issue")
        number = issue.get("number")
        if type(number) is not int:
            raise ReviewCloseoutError("created issue number must be an integer")
        created.append(number)
        readback = _read_tracked_issue(client, repository, key, number)
        if readback.url != _text(issue.get("html_url"), "created issue URL"):
            raise ReviewCloseoutError(f"issue #{number} targeted URL mismatch")
        _validate_issue(readback, "closeout-pending", review_priority(thread.body))
        tracked[key] = readback
    # LLM contract: DISCOVERED -> CLASSIFIED -> TRACKED -> (REPLIED -> RESOLVED | OUTDATED) -> READBACK_CONFIRMED.
    for key, thread in work.items():
        issue = tracked.get(key)
        if issue is None:
            raise ReviewCloseoutError(f"PR #{thread.pull_request} thread has no tracked issue")
        current_issue = _read_tracked_issue(client, repository, key, issue.number)
        if current_issue.url != issue.url:
            raise ReviewCloseoutError(f"PR #{key[0]} targeted issue URL mismatch")
        issue = current_issue
        is_resolved, is_outdated, body, reply_body = _read_thread(client, thread.thread_id, repository, thread.pull_request)
        priority = review_priority(body)
        if "lifecycle:source-closed" in issue.labels and "lifecycle:closeout-pending" not in issue.labels:
            _validate_issue(issue, "source-closed", priority)
            if not (is_resolved or is_outdated):
                raise ReviewCloseoutError("source-closed issue has an open thread")
            if not is_outdated or REPLY_RE.search(reply_body):
                _validate_link(reply_body, issue)
            continue
        _validate_issue(issue, "closeout-pending", priority)
        if "lifecycle:source-closed" in issue.labels and not (is_resolved or is_outdated):
            raise ReviewCloseoutError("source-closed issue has an open thread")
        if not is_outdated and REPLY_RE.search(reply_body) is None:
            if is_resolved:
                raise ReviewCloseoutError(f"thread {thread.thread_id} closed before source reply")
            issue = _read_valid_pending_issue(client, repository, key, issue, priority)
            reply = f"Tracked as bug #{issue.number}: {issue.url}\n\n<!-- review-closeout-reply:v1 issue={issue.number} url={issue.url} -->"
            client.reply_thread(thread.thread_id, reply)
            is_resolved, is_outdated, body, reply_body = _read_thread(client, thread.thread_id, repository, thread.pull_request)
        if not is_outdated or REPLY_RE.search(reply_body):
            _validate_link(reply_body, issue)
        if not is_resolved and not is_outdated:
            issue = _read_valid_pending_issue(client, repository, key, issue, priority)
            client.resolve_thread(thread.thread_id)
            is_resolved, is_outdated, body, reply_body = _read_thread(client, thread.thread_id, repository, thread.pull_request)
            _validate_link(reply_body, issue)
        if not (is_resolved or is_outdated) or review_priority(body) != priority:
            raise ReviewCloseoutError(f"thread {thread.thread_id} state changed during closeout")
        issue = _read_valid_pending_issue(client, repository, key, issue, priority)
        if "lifecycle:source-closed" not in issue.labels:
            client.add_issue_label(f"repos/{repository}/issues/{issue.number}", "lifecycle:source-closed")
        final = _read_tracked_issue(client, repository, key, issue.number)
        if final.url != issue.url or "lifecycle:source-closed" not in final.labels:
            raise ReviewCloseoutError(f"PR #{key[0]} thread lost its tracked issue")
        _validate_issue(final, "closeout-pending", priority)
        client.remove_issue_label(f"repos/{repository}/issues/{final.number}", "lifecycle:closeout-pending")
        terminal = _read_tracked_issue(client, repository, key, issue.number)
        if terminal.url != issue.url:
            raise ReviewCloseoutError(f"PR #{key[0]} terminal issue identity mismatch")
        _validate_issue(terminal, "source-closed", priority)
    result["created_issue_numbers"] = created
    result["status"] = "THREADS_CLOSED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--min-merged-with-threads", type=int, default=10)
    args = parser.parse_args()
    if "/" not in args.repo or args.min_merged_with_threads < 1:
        parser.error("--repo must be owner/name and the threshold must be positive")
    try:
        print(
            json.dumps(
                run(GhClient(), args.repo, args.min_merged_with_threads),
                indent=2,
                allow_nan=False,
            )
        )
    except ReviewCloseoutError as error:
        print(f"review closeout failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
