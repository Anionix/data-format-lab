# GitHub Stars 2026-07-03 Data Card

## Summary

This immutable case study contains 2,331 public repositories starred by GitHub user `steipete`, captured on 2026-07-03 and enriched into 13 columns. It is the first fair-lane dataset for Data Format Lab.

The compressed CSV is a `v0.1.0` release asset. The repository tracks only its manifest, hashes, schema, and a four-row fixture.

## Composition

- 2,331 rows and 13 columns.
- Public repository names, URLs, language, star count, fork/archive flags, topics, and descriptions.
- Five historical enrichment fields: group, category, micro-category, classification score, and matched terms.
- 119 rows classified as AI / LLM.
- 15 rows with more than 100,000 repository stars.

## Provenance

The source was GitHub's public starred-repositories endpoint. The exact CSV SHA-256 is `39cc70109d9dddf947257584e15f2f9a6bc97dcdf0a7bf939c26cccbcda0e22e`.

The original raw API response, request headers/API version, and classification generator were not retained. The enriched CSV is therefore reproducible as an immutable benchmark input, not regenerable from first principles.

## Limitations

- One person's stars are not representative of GitHub.
- Apple-platform repositories account for 1,459 rows, so workload selectivity is skewed.
- Categories are heuristic annotations, not ground truth.
- Repository descriptions and star counts reflect capture time.
- Performance results generalize only to the recorded dataset, settings, software, and hardware.

## Intended Use

Use this snapshot to verify equal-schema round trips, storage size, fixed query results, retrieval serialization, and format-native claims. Do not use it to infer user traits, repository quality, or ecosystem popularity.

## Updates

Future captures are new dataset IDs. They retain raw JSON, request metadata, and capture time and never overwrite this snapshot.
