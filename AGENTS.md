# Repository Instructions

## GitHub workflow

- This is an owner-original repository. Never stack pull requests.
- Start every work branch from the latest `origin/main`.
- Keep human-authored pull request diffs near 250 lines. Isolate generated lockfiles in a dedicated pull request.
- Merge one pull request before starting the next dependent branch.
- After merge, resolve or mark every review thread outdated. Turn remaining defects into a `bug`-labelled issue.

## Reproducibility

- Keep `flake.nix`, `flake.lock`, `pyproject.toml`, and `uv.lock` current.
- Never mix interpreters, package environments, datasets, or benchmark hosts in one result set.
- Record dataset hashes, package versions, writer settings, hardware, seed, and failure reasons.

## Research contract

- Separate fair storage comparison, format-native claims, and prompt/token comparison.
- Rank only `FULL_COMPARABLE` entries within the same benchmark lane.
- Add the lifecycle contract comment beside implementation state transitions:
  `DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED`.
- Failure states are `UNSUPPORTED` and `FAILED`; neither is rankable.
- Prefer primary sources and pin source commits for experimental implementations.

## Clarity

- Keep modules focused, interfaces small, and terminology consistent with `CONTEXT.md`.
- Do not commit benchmark artifacts, vendor checkouts, API tokens, or machine-specific absolute paths.
- Use `ask-matt` when the appropriate engineering flow is unclear.

## Agent skills

### Issue tracker

Work is tracked in GitHub Issues for `Anionix/data-format-lab`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the canonical triage roles. See `docs/agents/triage-labels.md`.

### Domain docs

Use the single-context `CONTEXT.md` and root `docs/adr/` layout. See `docs/agents/domain.md`.
