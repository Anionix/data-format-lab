#!/usr/bin/env bash
set -euo pipefail

# LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
profile="${1:?usage: ci_smoke.sh PROFILE}"
case "$profile" in
  fair | claims | prompt | equivalence) ;;
  *)
    echo "unsupported CI smoke profile: $profile" >&2
    exit 2
    ;;
esac

run_dir="runs/ci-smoke-$profile-$BASHPID"
pair_args=()
if test "$profile" = equivalence; then
  pair_args=(--pair csv-tsv)
fi

result=$(
  .venv/bin/format-bench run \
    --profile "$profile" \
    --dataset github-stars-2026-07-03 \
    --run-dir "$run_dir" \
    --fixture \
    "${pair_args[@]}"
)
run_dir=$(dirname "$result")
report=$(.venv/bin/format-bench report --run-dir "$run_dir")
before=$(sha256sum "$report")
.venv/bin/format-bench report --run-dir "$run_dir" >/dev/null
after=$(sha256sum "$report")
test "$before" = "$after"

.venv/bin/python -c \
  'import json,sys; m=json.load(open(sys.argv[1])); assert m.get("fixture") and not m.get("rankable")' \
  "$run_dir/manifest.json"

if test "$profile" = claims; then
  .venv/bin/python -c \
    'import json,sys; r=json.load(open(sys.argv[1]))["results"]; assert all(r[name]["target_tier"] == "EXPERIMENTAL" for name in ("tsfile_time_series", "fastlanes_official"))' \
    "$run_dir/results.json"
fi

if test "$profile" = equivalence; then
  .venv/bin/python -c \
    'import json,sys; r=json.load(open(sys.argv[1])); assert r["profile"]=="equivalence" and "csv-tsv" in r["equivalence"]["pairs"]' \
    "$run_dir/results.json"
fi
