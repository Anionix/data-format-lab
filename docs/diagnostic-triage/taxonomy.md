# Diagnostic Triage Taxonomy v1

This taxonomy classifies observed failures; it does not infer root cause without
evidence. `category` and `micro_category` are stable machine identifiers. Published
identifiers are never renamed or reused. Additive identifiers are allowed in v1;
semantic changes require a new taxonomy version.

Every finding has exactly one primary category and micro-category. Related evidence
may be linked without duplicating the finding. If no specific identifier is
supported, use the category's `unknown` member. Never classify from message wording
alone when the originating tool supplies a rule or structured kind.

| Category | Stable micro-categories | Meaning |
| --- | --- | --- |
| `syntax` | `parse-error`, `invalid-token`, `invalid-structure`, `unknown` | Source or configuration cannot be parsed. |
| `type` | `incompatible-type`, `missing-type`, `nullability`, `unresolved-symbol`, `invalid-call`, `contract-mismatch`, `unknown` | Static or runtime type contract is violated. |
| `correctness` | `assertion`, `invariant`, `wrong-result`, `data-loss`, `state-transition`, `nondeterminism`, `unknown` | Execution completes or is inspected but violates required behavior. |
| `runtime` | `exception`, `panic`, `abort`, `signal`, `import-failure`, `initialization`, `unknown` | Program execution terminates or cannot initialize normally. |
| `build` | `compile`, `link`, `dependency-resolution`, `code-generation`, `configuration`, `unknown` | A reproducible build step cannot produce its target. |
| `test` | `collection`, `setup`, `assertion`, `teardown`, `flaky`, `coverage-gate`, `unknown` | The test harness or a declared test contract fails. |
| `resource` | `timeout`, `memory-limit`, `disk-limit`, `output-limit`, `file-descriptor-limit`, `unknown` | A bounded execution exhausts an explicit resource budget. |
| `concurrency` | `race`, `deadlock`, `livelock`, `ordering`, `atomicity`, `unknown` | Interleaving or synchronization violates the execution contract. |
| `security` | `input-validation`, `path-escape`, `injection`, `unsafe-deserialization`, `permission`, `secret-exposure`, `unknown` | A supported security invariant is violated. |
| `environment` | `tool-missing`, `version-mismatch`, `platform`, `locale`, `timezone`, `network`, `filesystem`, `unknown` | Execution depends on unavailable or incompatible surroundings. |
| `tooling` | `protocol`, `malformed-output`, `provider-crash`, `unsupported-version`, `configuration`, `unknown` | Diagnostic collection itself is incomplete or invalid. |
| `style` | `format`, `lint`, `documentation`, `complexity`, `deprecation`, `unknown` | Non-correctness maintainability guidance is emitted. |
| `robustness` | `boundary-input`, `malformed-input`, `crash-resistance`, `roundtrip-mismatch`, `fuzz-finding`, `unknown` | Isolated robustness behavior defined by ADR 0002. |

## Classification rules

1. Preserve the originating `tool`, `tool_version`, and `rule_id`; taxonomy IDs do
   not replace native identifiers.
2. Prefer the most direct observed failure. For example, a test exposing a type
   contract defect is `type`, while failure to collect that test is `test.collection`.
3. Use `tooling` when the diagnostic provider or protocol fails, and `environment` when the
   requested tool cannot run because of its surroundings.
4. Use `resource` only when a declared limit is reached; an unexplained process exit
   is `runtime.unknown` until evidence improves.
5. Use `security` only for a stated security invariant, not as a severity synonym.
6. Robustness findings remain in the robustness lane. They never change rankings or
   comparability in any performance, prompt, equivalence, or engine-container lane.
7. `unknown` is publishable evidence and must not be silently promoted to a more
   specific class.

## Stability and rollout

- Fingerprints use native rule identity, normalized repository-relative location,
  symbol or structural context when available, and taxonomy identity. Line number
  alone is not identity.
- Observation and warning phases collect taxonomy coverage and false-positive data.
  Blocking is limited to eligible categories and the thresholds in ADR 0004.
- Extraction requires two independent consumers to accept this taxonomy and the
  versioned protocol unchanged. Repository-specific aliases do not satisfy that
  criterion.
