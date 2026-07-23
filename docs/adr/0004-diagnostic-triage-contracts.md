# ADR 0004: Diagnostic Triage Contracts

## Status

Amended

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

Use the standalone Apache-2.0
[`Anionix/diagnostic-triage`](https://github.com/Anionix/diagnostic-triage)
repository as the sole owner of the Rust implementation, taxonomy, schemas,
versioned JSON Lines protocol, providers, and release artifacts. This repository is
a pinned consumer. It owns only `diagnostic-triage.toml`, repository policy,
integration fixtures, observation workflow, and the immutable Nix lock.

The initial consumer pin is source revision
`f6877942a0de2b0c91f5334e7197996515e6344a`. The Nix input supplies the CLI,
providers, observer, schemas, and fixtures without a runtime network fetch. The
consumer test requires the configuration revision and locked input revision to be
identical.

The module separates collection from policy. A finding records tool evidence,
an optional source location, expected and observed behavior, classification, fix applicability, and a
stable fingerprint. Policy maps findings to `PASS`, `POLICY_FAIL`, `INCOMPLETE`, or
`UNSUPPORTED`; diagnostic providers do not decide repository policy.

The public commands include `check`, `ci`, `fix`, `verify --patch`, `observe`, and
`issue-draft`.
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

`data-format-lab` is the first real consumer. `Code-Review_Security` and
`nix-maintenance-status` remain rollout candidates. Generic changes belong in the
standalone repository; data-format-specific policy and defects remain here.

## Consequences

- Callers learn one small interface while normalization stays in the standalone
  engine and repository policy stays with the consumer.
- New tools require diagnostic providers, not changes to format adapters or ranking logic.
- Tool-native safe-fix metadata is preserved; absence of authoritative safety is
  treated as manual or unsafe.
- Protocol and taxonomy changes are proposed upstream and require compatibility
  tests plus an explicit schema version; published identifiers are never reassigned.
- Local generic schema, taxonomy, and protocol copies are removed to prevent
  divergent authorities.
