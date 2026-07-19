from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pyarrow as pa
import pyarrow.compute as pc


Comparison = Callable[
    [pa.Array | pa.ChunkedArray, object], pa.Array | pa.ChunkedArray
]


def _comparison(name: str) -> Comparison:
    function = getattr(pc, name, None)
    if not callable(function):
        raise RuntimeError(f"PyArrow compute function {name!r} is unavailable")
    return cast(Comparison, function)


equal = _comparison("equal")
greater = _comparison("greater")
greater_equal = _comparison("greater_equal")
less = _comparison("less")
less_equal = _comparison("less_equal")
