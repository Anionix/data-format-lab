import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Primary source: the current benchmark-lane contract in the English README.
LANE_ROW = re.compile(r"^\| `([^`]+)` \|")
FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")


def _readme(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _section(document: str, heading: str) -> str:
    target = f"## {heading}"
    selected = False
    lines: list[str] = []
    fence: tuple[str, int] | None = None
    for line in document.splitlines():
        match = FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            if selected:
                lines.append(line)
            continue
        if fence is not None:
            if selected:
                lines.append(line)
            continue
        if line == target:
            selected = True
            continue
        if selected and line.startswith("## "):
            break
        if selected:
            lines.append(line)
    if not selected:
        raise ValueError(f"missing README section: {heading}")
    return "\n".join(lines)


def _lane_names(section: str) -> tuple[str, ...]:
    names: list[str] = []
    fence: tuple[str, int] | None = None
    for line in section.splitlines():
        match = FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            continue
        if fence is None and (row := LANE_ROW.match(line)):
            names.append(row.group(1))
    return tuple(names)


def _shell_commands(section: str) -> tuple[str, ...]:
    commands: list[str] = []
    active = False
    fence: tuple[str, int] | None = None
    pending = ""
    for line in section.splitlines():
        match = FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
                active = match.group(2).strip().split(maxsplit=1)[0] in {"bash", "sh"}
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                if pending:
                    commands.append(pending)
                    pending = ""
                fence = None
                active = False
            continue
        if not active or not line.strip():
            continue
        command = line.strip()
        if command.endswith("\\"):
            pending += command[:-1].rstrip() + " "
        else:
            commands.append((pending + command).strip())
            pending = ""
    return tuple(commands)


def test_english_and_japanese_readmes_list_the_same_lanes() -> None:
    english = _lane_names(_section(_readme("README.md"), "Benchmark lanes"))
    japanese = _lane_names(_section(_readme("README.ja.md"), "ベンチマークlane"))

    # LLM contract: SOURCE_PARSED -> LANE_SEQUENCE_COMPARED -> PARITY_VERIFIED.
    assert english == japanese


def test_english_and_japanese_readmes_expose_the_same_equivalence_contract() -> None:
    english = _readme("README.md")
    japanese = _readme("README.ja.md")
    command = (
        "uv run --frozen format-bench run --profile equivalence "
        "--dataset github-stars-2026-07-03 --fixture --pair csv-tsv"
    )
    assert command in _shell_commands(_section(english, "Reproduce"))
    assert command in _shell_commands(_section(japanese, "実行"))
    for token in (
        "±2%",
        "±5%",
        "±10%",
        "PRACTICALLY_EQUIVALENT",
        "MEANINGFUL_DIFFERENCE",
        "INCONCLUSIVE",
        "NOT_APPLICABLE",
    ):
        assert token in _section(english, "Benchmark lanes")
        assert token in _section(japanese, "ベンチマークlane")


def test_markdown_examples_do_not_change_section_lane_rows() -> None:
    document = """## Target
```markdown
## Fenced heading
| `fenced` | example |
```
| `real` | contract |
## Next
| `later` | unrelated |
"""

    assert _lane_names(_section(document, "Target")) == ("real",)


def test_shell_commands_join_backslash_continuations() -> None:
    section = """```sh
tool run \\
  --profile equivalence
```
"""

    assert _shell_commands(section) == ("tool run --profile equivalence",)
