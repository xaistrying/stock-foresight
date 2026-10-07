"""CLAUDE.md and openspec/config.yaml each carry the six domain rules and must not drift.

CLAUDE.md says to change a rule in BOTH files; this fails on any wording difference
(after stripping bold, backticks and line wrapping).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULE_START = re.compile(r"^\s*([1-6])\. ", re.MULTILINE)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).strip()


def _rules(region: str) -> dict[int, str]:
    marks = list(RULE_START.finditer(region))
    ends = [m.start() for m in marks[1:]] + [len(region)]
    return {int(m[1]): _normalise(region[m.end():end]) for m, end in zip(marks, ends)}


def _claude_md_rules() -> dict[int, str]:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    region = text.split("## Non-Negotiable Domain Rules", 1)[1].split("\n## ", 1)[0]
    return _rules(region)


def _config_rules() -> dict[int, str]:
    text = (ROOT / "openspec" / "config.yaml").read_text(encoding="utf-8")
    region = text.split("Non-negotiable domain rules", 1)[1].split("Repository structure:", 1)[0]
    return _rules(region)


def test_both_files_state_all_six_rules():
    assert sorted(_claude_md_rules()) == [1, 2, 3, 4, 5, 6]
    assert sorted(_config_rules()) == [1, 2, 3, 4, 5, 6]


def test_the_six_rules_read_the_same_in_both_files():
    claude, config = _claude_md_rules(), _config_rules()

    for number in range(1, 7):
        assert claude[number] == config[number], f"Rule {number} differs between CLAUDE.md and config.yaml"
