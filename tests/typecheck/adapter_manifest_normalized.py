from format_bench.adapter_contract import AdapterManifest
from format_bench.contracts import NormalizedColumn


def manifest_with_normalized_columns(
    columns: list[NormalizedColumn],
) -> AdapterManifest:
    # LLM contract: RAW_COLUMNS -> NORMALIZED_COLUMNS -> ADAPTER_ACCEPTED.
    return {
        "rows": 0,
        "columns": columns,
        "canonical_hash": "",
        "expected_counts": {},
    }
