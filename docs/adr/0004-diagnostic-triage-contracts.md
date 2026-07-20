# ADR 0004: Diagnostic Triage Contracts

## Status

Accepted

## Context

Python, Rust, and web tooling emit incompatible diagnostics. Tool-specific output
is useful evidence, but it does not provide one stable model for classification,
deduplication, policy, safe fixes, or before-and-after verification. Folding those
concerns into benchmark adapters would widen their interfaces and couple evidence
collection to ranking.

ADR 0002 already separates conformance from robustness. Diagnostic Triage must
preserve that seam: it can report defects in either lane, but it cannot reinterpret
robustness evidence as benchmark evidence.

## Decision

Add Diagnostic Triage as a deep Rust module under
`tools/diagnostic-triage/`. Its public interface is the
`diagnostic-triage` command and versioned JSON Lines protocol. Diagnostic providers
sit at that seam and normalize Ruff, ty, Pyright, pytest, Biome, Cargo, Clippy, and process
evidence into `FindingV1`. The taxonomy in
`docs/diagnostic-triage/taxonomy.md` owns stable classification identifiers.

The module separates collection from policy. A finding records tool evidence,
an optional source location, expected and observed behavior, classification, fix applicability, and a
stable fingerprint. Policy maps findings to `PASS`, `POLICY_FAIL`, `INCOMPLETE`, or
`UNSUPPORTED`; diagnostic providers do not decide repository policy.

The public commands are `check`, `ci`, `fix`, `verify --patch`, and `issue-draft`.
`check` and `ci` never write tracked files. CLI exit status `0` means policy pass,
`1` means a completed policy failure, and `2` means configuration, protocol,
provider, or other operational failure.

`check` and `ci` are read-only. Fixes are delegated to the originating tool in an
isolated copy. A safe fix may be applied only by an explicit `--apply-safe` request
and only when the tool authoritatively marks it safe. All other fixes remain patches.
A fix is verified only when the original finding disappears, every required provider
completes, and no finding of equal or greater policy severity is introduced.

Diagnostic evidence never changes comparability. In particular, robustness
findings never affect rankings in fair, claims, prompt, equivalence, or
engine-container lanes. Conformance remains the only gate from encoding to ranked
performance evidence, and unsupported or failed observations remain publishable.

Diagnostic state is:

`DISCOVERED -> NORMALIZED -> CLASSIFIED -> FIX_PROPOSED -> VERIFIED -> REPORTED`

`INCOMPLETE` and `UNSUPPORTED` are terminal evidence states. This diagnostic state
does not replace the repository lifecycle. Implementation state transitions must
retain the exact required comment beside the transition:

`# LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.`

Rollout advances from observation to warning and then blocking. Each of the first
two phases requires at least 14 days and 20 successful runs per participating real
repository. Blocking additionally requires an operational incomplete rate at or
below 1%, a confirmed false-positive rate at or below 2% for candidate blocking
rules, and zero unauthorized source writes. Only syntax, type, correctness, build,
and test findings may block initially; style, preview rules, robustness findings,
and unsupported tools remain non-blocking.

Extraction to `Anionix/diagnostic-triage` requires two independent repositories to
consume the same schema and protocol without repository-specific changes. Candidate
consumers are `data-format-lab`, `Code-Review_Security`, and
`nix-maintenance-status`. After extraction, consumers pin a verified commit or Nix
lock; schema identifiers and finding fingerprints retain compatibility.

## Consequences

- Callers learn one small interface while normalization and policy stay local to
  the module.
- New tools require diagnostic providers, not changes to format adapters or ranking logic.
- Tool-native safe-fix metadata is preserved; absence of authoritative safety is
  treated as manual or unsafe.
- Protocol and taxonomy changes require compatibility tests and an explicit schema
  version; published identifiers are never reassigned.
- A second independent consumer is required before package extraction, consistent
  with ADR 0002.
