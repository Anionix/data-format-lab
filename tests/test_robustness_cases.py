import json
from pathlib import Path

import pytest

from format_bench.canonical import canonical_hash, read_csv
from format_bench.model import RobustnessExpectation
from format_bench.robustness import generated_cases, materialize_case, named_cases


DATASET = Path("datasets/github-stars-2026-07-03")


def _base():
    manifest = json.loads((DATASET / "manifest.json").read_text())
    return read_csv(DATASET / "fixture.csv", manifest)


def test_named_cases_cover_the_public_boundaries() -> None:
    cases = {case.case_id: case for case in named_cases()}
    assert all(f"rows-{rows}" in cases for rows in (0, 1, 1023, 1024, 1025, 2048, 2049))
    assert all(f"dictionary-{size}" in cases for size in (1, 2, 255, 256))
    assert cases["malformed-missing-column"].expectation is RobustnessExpectation.MUST_REJECT
    assert cases["malformed-truncated"].expectation is RobustnessExpectation.MUST_NOT_CRASH


def test_valid_named_cases_preserve_schema_and_requested_values() -> None:
    base = _base()
    cases = {case.case_id: case for case in named_cases()}
    rows = materialize_case(base, cases["rows-1025"])
    dictionary = materialize_case(base, cases["dictionary-256"])
    utf8 = materialize_case(base, cases["string-utf8"])

    assert rows.num_rows == 1025 and rows.schema == base.schema
    assert len(set(dictionary["group"].to_pylist())) == 256
    assert utf8["description"][0].as_py() == "日本語 cafe"


def test_generated_cases_are_seeded_and_have_stable_semantics() -> None:
    base = _base()
    first = generated_cases(20260703, 4)
    second = generated_cases(20260703, 4)
    assert first == second
    other = generated_cases(20260704, 4)
    first_hashes = [canonical_hash(materialize_case(base, case)) for case in first]
    assert first != other
    assert first_hashes == [
        canonical_hash(materialize_case(base, case)) for case in second
    ]
    assert first_hashes != [canonical_hash(materialize_case(base, case)) for case in other]


def test_generated_cases_preserve_requested_rows() -> None:
    base = _base()
    for case in generated_cases(20260703, 32):
        table = materialize_case(base, case)
        assert table.num_rows == case.options["rows"]
        if case.options["rows"]:
            assert case.options["cardinality"] <= case.options["rows"]
        else:
            assert case.options["cardinality"] == 0


def test_empty_generated_case_preserves_following_seed_sequence() -> None:
    cases = generated_cases(74, 32)
    assert cases[8].options["rows"] == 0
    assert cases[8].options["cardinality"] == 0
    assert cases[9].case_id == "generated-009-ad1bb43efc"


def test_malformed_case_has_no_valid_arrow_materialization() -> None:
    case = next(case for case in named_cases() if case.case_id == "malformed-extra-column")
    with pytest.raises(ValueError, match="no valid Arrow input"):
        materialize_case(_base(), case)


def test_negative_generated_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        generated_cases(1, -1)
