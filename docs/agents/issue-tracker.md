# Issue Tracker

GitHub Issues in `Anionix/data-format-lab` are the canonical work tracker.

- Specifications and implementation tickets are issues.
- Agent-ready work carries the `ready-for-agent` label.
- Wayfinder maps use `wayfinder:map`; child decisions use the matching `wayfinder:*` label.
- Use GitHub sub-issues and blocking relationships when ordering work.
- Pull requests are implementation artifacts, not an incoming request queue.
- Close issues only after merged behavior and generated artifacts are verified on `main`.

## Post-merge review closeout

- After every merge, close every review thread on that PR by resolving it or marking it outdated.
- In addition, batch-scan merged PRs with review threads after every 10 such PRs.
- Scan immediately for P0/P1, security, release-blocking, or user-reported concerns.
- Restrict the actionable set to current unresolved threads: `MERGED` + review thread + `!isResolved` + `!isOutdated`.
- Create a `bug` issue, reply with its URL, then resolve or mark the thread outdated. Fixes use a new non-stacked PR from the latest `origin/main`.
