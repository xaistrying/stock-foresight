"""Repository hygiene for the brief: ignore patterns that hide holdings but not code, and no mention
of the company feed outside its one adapter (design D2, tasks 1.3 and 1.4; `add-dividend-and-ex-date-lines`)."""

from __future__ import annotations

import subprocess

import pytest

from .test_brief_support import BACKEND, REPO_ROOT, brief_isolation  # noqa: F401  (autouse fixture)

PACKAGE = BACKEND / "app" / "services" / "brief"
# Built by concatenation so this test's own text is not what the feed isolation test forbids.
FORBIDDEN = "company" + "_feed"


def _ignored(paths: list[str]) -> set[str]:
    result = subprocess.run(
        ["git", "check-ignore", *paths], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode in (0, 1), result.stderr
    return set(result.stdout.split())


@pytest.mark.parametrize("prefix", ["", "backend/"])
def test_holdings_files_are_ignored_at_the_root_and_under_backend(prefix):
    names = ["holdings.toml", "holdings_issued.jsonl", "holdings_share_counts.json"]
    paths = [prefix + name for name in names]

    assert _ignored(paths) == set(paths)


def test_the_ignore_patterns_are_not_a_bare_holdings_glob():
    lines = [line.strip() for line in (REPO_ROOT / ".gitignore").read_text().splitlines()]

    assert "holdings*" not in lines
    assert {"holdings*.toml", "holdings*.jsonl", "holdings*.json"} <= set(lines)


def test_no_file_this_change_adds_is_ignored():
    added = [
        *PACKAGE.glob("*.py"),
        BACKEND / "scripts" / "weekly_brief.py",
        *(BACKEND / "tests").glob("test_brief_*.py"),
        *(BACKEND / "tests").glob("brief_*.py"),
        *(BACKEND / "tests" / "brief_golden").glob("*"),
    ]
    existing = [str(path.relative_to(REPO_ROOT)) for path in added if path.exists()]

    assert len(existing) >= 3 and any("brief_golden" in path for path in existing)
    assert _ignored(existing) == set()


ADAPTER = "feed_source.py"  # the one brief file allowed to name the feed (`add-dividend-and-ex-date-lines`)


def test_only_the_adapter_mentions_the_company_feed():
    offenders = [
        str(path.relative_to(BACKEND)) for path in PACKAGE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.name != ADAPTER
        and FORBIDDEN in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
    assert FORBIDDEN in (PACKAGE / ADAPTER).read_text(encoding="utf-8")
