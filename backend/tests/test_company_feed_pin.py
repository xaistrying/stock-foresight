"""`vnstock` and `vnai` are pinned exactly (`company-feed`, "pinned exactly").

A silent upgrade of either could move the AI-config write path that
`app.vnstock_guard` neutralises, so a bump must be deliberate and re-tested. The
procedure is in the comment above the pins in `backend/requirements.txt`.
"""

import re
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"
EXPECTED = ("vnstock==4.0.5", "vnai==2.5.5")
_NAME_RE = re.compile(r"^\s*(vnstock|vnai)\b", re.IGNORECASE)


def _vendor_requirements(text: str) -> list[str]:
    """Every non-comment line that names `vnstock` or `vnai`, whatever its specifier."""
    lines = (line.split("#", 1)[0].strip() for line in text.splitlines())
    return [line for line in lines if _NAME_RE.match(line)]


def test_requirements_pin_vnstock_and_vnai_exactly():
    """Scenario: Exact pins."""
    found = _vendor_requirements(REQUIREMENTS.read_text(encoding="utf-8"))
    assert sorted(found) == sorted(EXPECTED)


def _mutated(tmp_path, replacement: str, target: str) -> list[str]:
    text = REQUIREMENTS.read_text(encoding="utf-8").replace(target, replacement)
    copy = tmp_path / "requirements.txt"
    copy.write_text(text, encoding="utf-8")
    return _vendor_requirements(copy.read_text(encoding="utf-8"))


def test_a_loose_pin_fails_the_check(tmp_path):
    """Scenario: A loose pin fails a test. Each loosened form leaves the file unequal to the pins."""
    for target, loose in (
        ("vnstock==4.0.5", "vnstock>=4.0.5"),
        ("vnstock==4.0.5", "vnstock~=4.0.5"),
        ("vnstock==4.0.5", "vnstock"),
        ("vnai==2.5.5", "vnai>=2.5.5"),
        ("vnai==2.5.5", "vnai~=2.5.5"),
        ("vnai==2.5.5", "vnai"),
    ):
        assert sorted(_mutated(tmp_path, loose, target)) != sorted(EXPECTED), loose


def test_an_extra_vendor_requirement_fails_the_check(tmp_path):
    text = REQUIREMENTS.read_text(encoding="utf-8") + "\nvnstock>=4.0.5\n"
    copy = tmp_path / "requirements.txt"
    copy.write_text(text, encoding="utf-8")
    assert sorted(_vendor_requirements(copy.read_text(encoding="utf-8"))) != sorted(EXPECTED)


def test_the_bump_procedure_is_recorded_beside_the_pins():
    text = REQUIREMENTS.read_text(encoding="utf-8")
    for phrase in ("both pins", "fresh", "KNOWN_ISSUES", "dry-run", "latest"):
        assert phrase in text, phrase
