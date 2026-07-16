from pathlib import Path


GUIDE = Path(__file__).parents[1] / "docs" / "format-selection.md"


def _section(text: str, heading: str, next_heading: str) -> str:
    start = text.index(heading)
    end = text.index(next_heading, start)
    return text[start:end]


def test_selection_guide_only_recommends_measured_workloads() -> None:
    text = GUIDE.read_text()
    decisions = _section(text, "## Quick Decisions", "## Formats Without A Selection")
    incomplete = _section(text, "## Formats Without A Selection", "## Decision Rules")

    assert "| Measured device/tag time-range query | TsFile |" in decisions
    assert "| Time-series workloads | TsFile |" not in decisions
    assert "| Experimental numeric pipeline | FastLanes |" not in decisions
    assert "FastLanes also has no general selection yet." in incomplete
