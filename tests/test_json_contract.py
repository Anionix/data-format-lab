import ast
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from format_bench.json_contract import strict_json_dumps, strict_json_loads


def _unsafe_json_writer_lines(source: str, filename: str) -> list[int]:
    tree = ast.parse(source, filename=filename)
    module_names: set[str] = set()
    writer_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            module_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "json"
            )
        elif isinstance(node, ast.ImportFrom) and node.module == "json":
            writer_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name in {"dump", "dumps"}
            )

    violations: list[int] = []
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        function = call.func
        direct_writer = (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id in module_names
            and function.attr in {"dump", "dumps"}
        ) or (isinstance(function, ast.Name) and function.id in writer_names)
        if not direct_writer:
            continue
        allow_nan = next(
            (
                keyword.value
                for keyword in call.keywords
                if keyword.arg == "allow_nan"
            ),
            None,
        )
        if not (isinstance(allow_nan, ast.Constant) and allow_nan.value is False):
            violations.append(call.lineno)
    return violations


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


@pytest.mark.parametrize(
    "token",
    ("NaN", "Infinity", "-Infinity", "1e9999", "-1e9999"),
)
def test_strict_json_loads_rejects_nonfinite_numbers(token: str) -> None:
    with pytest.raises(json.JSONDecodeError, match="non-finite JSON number"):
        strict_json_loads(f'{{"nested":[{{"value":{token}}}]}}')


def test_strict_json_loads_accepts_finite_numbers() -> None:
    assert strict_json_loads('{"value":1.25}') == {"value": 1.25}


def test_direct_json_writers_declare_nonfinite_policy() -> None:
    root = Path(__file__).parents[1]
    violations: list[str] = []
    for source_root in (root / "src" / "format_bench", root / "tools"):
        for path in sorted(source_root.rglob("*.py")):
            if path.name == "json_contract.py":
                continue
            for line in _unsafe_json_writer_lines(
                path.read_text(encoding="utf-8"),
                str(path),
            ):
                violations.append(f"{path.relative_to(root)}:{line}")

    assert violations == []


@pytest.mark.parametrize(
    "source",
    (
        "import json as codec\ncodec.dumps({'value': 1})\n",
        "from json import dump as emit\nemit({'value': 1}, None)\n",
    ),
)
def test_json_writer_policy_resolves_import_aliases(source: str) -> None:
    assert _unsafe_json_writer_lines(source, "alias.py") == [2]


def test_json_writer_policy_allows_explicit_strict_alias() -> None:
    source = "import json as codec\ncodec.dumps({'value': 1}, allow_nan=False)\n"
    assert _unsafe_json_writer_lines(source, "strict-alias.py") == []
