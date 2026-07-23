import subprocess
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

from format_bench import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_package_version_has_one_hatch_source() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    # LLM contract: RELEASE_IDENTIFIED -> VERSION_NORMALIZED -> METADATA_BOUND -> VERIFIED.
    assert "version" not in pyproject["project"]
    assert "version" in pyproject["project"]["dynamic"]
    assert (
        pyproject["tool"]["hatch"]["version"]["path"]
        == "src/format_bench/__init__.py"
    )
    assert __version__ == "0.2.0rc1"


def test_lock_does_not_retain_a_stale_static_version() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    package = next(item for item in lock["package"] if item["name"] == "format-bench")

    assert package["source"] == {"editable": "."}
    assert "version" not in package


def test_built_wheel_metadata_uses_the_canonical_version(tmp_path: Path) -> None:
    subprocess.run(
        [
            "uv",
            "build",
            "--offline",
            "--wheel",
            "--out-dir",
            str(tmp_path),
            "--no-create-gitignore",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    wheel = next(tmp_path.glob("format_bench-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        metadata_path = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = BytesParser().parsebytes(archive.read(metadata_path))

    assert metadata["Version"] == __version__
    assert wheel.name == f"format_bench-{__version__}-py3-none-any.whl"
