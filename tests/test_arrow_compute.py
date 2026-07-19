import pyarrow as pa
import pyarrow.compute as pc
import pytest

from format_bench import arrow_compute


@pytest.mark.parametrize(
    "name",
    ("equal", "greater", "greater_equal", "less", "less_equal"),
)
def test_typed_comparison_matches_pinned_pyarrow(name: str) -> None:
    comparison = getattr(arrow_compute, name)
    assert comparison is getattr(pc, name)
    result = comparison(pa.array([1, 2]), 1)
    expected = {
        "equal": [True, False],
        "greater": [False, True],
        "greater_equal": [True, True],
        "less": [False, False],
        "less_equal": [True, False],
    }
    assert result.to_pylist() == expected[name]
