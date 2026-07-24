import ast
import json
import math
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, cast

import pytest

from format_bench import json_contract
from format_bench.json_contract import (
    atomic_write_json,
    strict_json_dumps,
    strict_json_loads,
)


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
            (keyword.value for keyword in call.keywords if keyword.arg == "allow_nan"),
            None,
        )
        if not (isinstance(allow_nan, ast.Constant) and allow_nan.value is False):
            violations.append(call.lineno)
    return violations


@pytest.mark.parametrize(
    "value", [math.nan, math.inf, -math.inf, {"nested": [math.nan]}]
)
def test_strict_json_dumps_rejects_nonfinite_numbers(value: object) -> None:
    with pytest.raises(
        ValueError, match="Out of range float values are not JSON compliant"
    ):
        strict_json_dumps(value)


def test_strict_json_dumps_cannot_be_weakened_by_callers() -> None:
    untyped_dumps = cast(Callable[..., str], strict_json_dumps)
    with pytest.raises(TypeError, match="allow_nan is fixed to False"):
        untyped_dumps({"value": math.nan}, allow_nan=True)


def test_strict_json_dumps_accepts_finite_numbers() -> None:
    assert strict_json_dumps({"value": 1.25}) == '{"value": 1.25}'


def test_atomic_write_json_creates_and_replaces_deterministic_document(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "manifest.json"

    atomic_write_json(destination, {"value": 1})
    assert destination.read_bytes() == b'{\n  "value": 1\n}\n'

    atomic_write_json(destination, {"value": 2})
    assert destination.read_bytes() == b'{\n  "value": 2\n}\n'


def test_atomic_write_json_serialization_failure_preserves_previous_document(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "manifest.json"
    previous = b'{"state":"ENCODED"}\n'
    destination.write_bytes(previous)

    with pytest.raises(ValueError, match="Out of range float values"):
        atomic_write_json(destination, {"value": math.nan})

    assert destination.read_bytes() == previous
    assert list(tmp_path.glob(".manifest.json.*.tmp")) == []


def test_atomic_file_writer_completes_short_writes() -> None:
    class ShortWriter:
        def __init__(self) -> None:
            self.payload = bytearray()

        def write(self, payload: bytes) -> int:
            accepted = min(2, len(payload))
            self.payload.extend(payload[:accepted])
            return accepted

    destination = ShortWriter()
    json_contract._write_atomic_file(cast(BinaryIO, destination), b"evidence")

    assert destination.payload == b"evidence"


@pytest.mark.parametrize("fault", ("write", "flush", "replace"))
def test_atomic_write_json_failure_preserves_previous_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    destination = tmp_path / "manifest.json"
    previous = b'{"state":"ROUNDTRIP_VERIFIED"}\n'
    destination.write_bytes(previous)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError(f"injected {fault} failure")

    if fault == "replace":
        monkeypatch.setattr(json_contract.os, "replace", fail)
    else:
        monkeypatch.setattr(json_contract, f"_{fault}_atomic_file", fail)

    with pytest.raises(OSError, match=f"injected {fault} failure"):
        atomic_write_json(destination, {"state": "BENCHMARKED"})

    assert destination.read_bytes() == previous
    assert list(tmp_path.glob(".manifest.json.*.tmp")) == []


def test_atomic_write_json_rejects_symlink_destination(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_bytes(b'{"outside":true}\n')
    destination = tmp_path / "manifest.json"
    destination.symlink_to(outside)

    with pytest.raises(ValueError, match="symbolic link"):
        atomic_write_json(destination, {"outside": False})

    assert destination.is_symlink()
    assert outside.read_bytes() == b'{"outside":true}\n'


def test_atomic_write_json_accepts_same_directory_with_parent_segments(
    tmp_path: Path,
) -> None:
    destination_dir = tmp_path / "destination"
    nested = destination_dir / "nested"
    nested.mkdir(parents=True)
    destination = nested / ".." / "manifest.json"

    atomic_write_json(destination, {"state": "ENCODED"})

    assert (destination_dir / "manifest.json").read_bytes() == (
        b'{\n  "state": "ENCODED"\n}\n'
    )


def test_atomic_write_json_rejects_cross_directory_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination_dir = tmp_path / "destination"
    destination_dir.mkdir()
    destination = destination_dir / "manifest.json"
    previous = b'{"state":"ENCODED"}\n'
    destination.write_bytes(previous)
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    real_mkstemp = tempfile.mkstemp

    def cross_directory_mkstemp(
        *,
        prefix: str,
        suffix: str,
        dir: str | Path,
    ) -> tuple[int, str]:
        del dir
        return real_mkstemp(prefix=prefix, suffix=suffix, dir=other_dir)

    monkeypatch.setattr(json_contract.tempfile, "mkstemp", cross_directory_mkstemp)

    with pytest.raises(ValueError, match="same directory"):
        atomic_write_json(destination, {"state": "BENCHMARKED"})

    assert destination.read_bytes() == previous
    assert list(other_dir.iterdir()) == []


@pytest.mark.parametrize(
    "token",
    ("NaN", "Infinity", "-Infinity", "1e9999", "-1e9999"),
)
def test_strict_json_loads_rejects_nonfinite_numbers(token: str) -> None:
    with pytest.raises(json.JSONDecodeError, match="non-finite JSON number"):
        strict_json_loads(f'{{"nested":[{{"value":{token}}}]}}')


def test_strict_json_loads_accepts_finite_numbers() -> None:
    assert strict_json_loads('{"value":1.25}') == {"value": 1.25}


@pytest.mark.parametrize(
    "payload",
    ('{"value":1,"value":2}', '{"nested":{"value":1,"value":2}}'),
)
def test_strict_json_loads_rejects_duplicate_object_keys(payload: str) -> None:
    with pytest.raises(json.JSONDecodeError, match="duplicate JSON object key: value"):
        strict_json_loads(payload)


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
