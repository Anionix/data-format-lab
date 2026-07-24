import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Primary source: the current benchmark-lane contract in the English README.
LANE_ROW = re.compile(r"^\| `([^`]+)` \|", re.MULTILINE)


def _readme(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_english_and_japanese_readmes_list_the_same_lanes() -> None:
    english = set(LANE_ROW.findall(_readme("README.md")))
    japanese = set(LANE_ROW.findall(_readme("README.ja.md")))

    # LLM contract: SOURCE_PARSED -> LANE_SET_COMPARED -> PARITY_VERIFIED.
    assert english == japanese


def test_japanese_readme_exposes_the_equivalence_contract() -> None:
    japanese = _readme("README.ja.md")

    assert "--profile equivalence" in japanese
    assert "PRACTICALLY_EQUIVALENT" in japanese
    assert "INCONCLUSIVE" in japanese
