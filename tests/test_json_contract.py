import ast
import math
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from format_bench.json_contract import strict_json_dumps


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, {"nested": [math.nan]}])
def test_strict_json_dumps_rejects_nonfinite_numbers(value: object) -> None:
    with pytest.raises(ValueError, match="Out of range float values are not JSON compliant"):
        strict_json_dumps(value)


def test_strict_json_dumps_cannot_be_weakened_by_callers() -> None:
    untyped_dumps = cast(Callable[..., str], strict_json_dumps)
    with pytest.raises(TypeError, match="allow_nan is fixed to False"):
        untyped_dumps({"value": math.nan}, allow_nan=True)


def test_strict_json_dumps_accepts_finite_numbers() -> None:
    assert strict_json_dumps({"value": 1.25}) == '{"value": 1.25}'


def test_direct_json_writers_declare_nonfinite_policy() -> None:
    root = Path(__file__).parents[1]
    violations: list[str] = []
    for source_root in (root / "src" / "format_bench", root / "tools"):
        for path in sorted(source_root.rglob("*.py")):
            if path.name == "json_contract.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
                function = call.func
                if not (
                    isinstance(function, ast.Attribute)
                    and isinstance(function.value, ast.Name)
                    and function.value.id == "json"
                    and function.attr in {"dump", "dumps"}
                ):
                    continue
                allow_nan = next(
                    (
                        keyword.value
                        for keyword in call.keywords
                        if keyword.arg == "allow_nan"
                    ),
                    None,
                )
                if not (
                    isinstance(allow_nan, ast.Constant) and allow_nan.value is False
                ):
                    violations.append(f"{path.relative_to(root)}:{call.lineno}")

    assert violations == []
