#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

required_runs=(
  runs/full-20260719-nyc-shards/jsonl-avro
  runs/full-20260719-nyc-shards/jsonl-msgpack-cbor
  runs/full-20260718-retail-current-shards/jsonl-avro
  runs/full-20260718-geonames-current-shards-v3/jsonl-avro
)

for run in "${required_runs[@]}"; do
  if [[ ! -f "$run/results.json" ]]; then
    echo "required run is incomplete: $run" >&2
    exit 2
  fi
  PYTHONPATH=src .venv/bin/python -m format_bench report --run-dir "$run"
done

PYTHONPATH=src .venv/bin/python tools/build_revalidation_aggregate.py

if ! .venv/bin/python - <<'PY'
import json
from pathlib import Path
result = json.loads(Path('.data/revalidation-20260719/results.json').read_text())
raise SystemExit(0 if result['completion_state'] == 'COMPLETE' else 1)
PY
then
  echo 'aggregate is not complete; leaving evidence un-packaged' >&2
  exit 2
fi

mkdir -p .data/revalidation-20260719/package-run
cp .data/revalidation-20260719/manifest.json .data/revalidation-20260719/package-run/manifest.json
cp .data/revalidation-20260719/results.json .data/revalidation-20260719/package-run/results.json
cp .data/revalidation-20260719/report.md .data/revalidation-20260719/package-run/report.md
rsync -a --delete .data/revalidation-20260719/claims/ .data/revalidation-20260719/package-run/claims/

PYTHONPATH=src .venv/bin/python -m format_bench package \
  --run-dir .data/revalidation-20260719/package-run \
  --output .data/release-evidence \
  --platform macos-arm64
