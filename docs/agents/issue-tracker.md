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
- The scheduled sweep is the recurring batch trigger; it scans once at least 10 merged PRs with review threads are available.
- Scan immediately for P0/P1, security, release-blocking, or user-reported concerns.
- Restrict discovery to current unresolved threads; `lifecycle:closeout-pending` may re-enter only to finish an idempotent transition.
- Create a `bug` issue, reply with its URL, then resolve or mark the thread outdated. Fixes use a new non-stacked PR from the latest `origin/main`.

## Scheduled historical sweep

- The Codex automation `Data Format Lab review closeout sweep` runs daily in the Data Format Lab project.
- It runs `python3 tools/review_closeout.py --repo Anionix/data-format-lab --min-merged-with-threads 10` from the latest `origin/main`.
- It exits without mutation until at least 10 merged PRs with review threads exist.
- Once the threshold is reached, it creates idempotent `bug` follow-up issues for current unresolved threads.
- After owner and exact source-identity readback it may reply/resolve once, but succeeds only after canonical reply, exact issue, thread, and lifecycle readback; it never mutates code, branches, PRs, or outdated threads.
- The Codex schedule is the single recurring trigger. Do not start a second sweep while one is running; the scanner's issue lookup is idempotent but is not a distributed lock.
- For recovery or an intentional manual run, execute the same command from the repository root after confirming no scheduled sweep is active. The automation name is `Data Format Lab review closeout sweep` and its ID is `data-format-lab-review-closeout-sweep`.
- The scanner remains reusable locally and in CI-like environments, while recurring scheduling stays in Codex to avoid duplicate triggers.
