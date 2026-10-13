"""The COMPANY block and the investor's holdings (`add-announcement-tags-and-insider-sizing`, "A redacted copy keeps the COMPANY
block without anything derived from the issued log or the holdings"): nothing in the block depends on what the investor holds,
and what the issued log decides is left out of the redacted copy."""

from __future__ import annotations

import ast
import dataclasses
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.services.brief import sections_company
from app.services.brief.compose import TickerReport, build_brief
from app.services.brief.facts import MarketFacts
from app.services.brief.feed_source import FeedSnapshot, IssueClass
from app.services.brief.share_cache import ShareCount
from app.services.brief.sizing import MODE_OK, SizingInput

from .brief_announcement_rows import make_announcement, make_company, make_issue_item, make_trade_item
from .test_brief_support import brief_isolation, ict, make_facts, make_holding, make_level  # noqa: F401

NOW = ict("2026-10-09 16:30")
PACKAGE = Path(sections_company.__file__).parent
FETCHED = datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc)
COUNT = ShareCount(1_282_562_372, 2026, 2, datetime(2026, 10, 12, 5, 0, tzinfo=timezone.utc))

# Distinctive hypothetical holdings: none of these may appear inside a COMPANY block.
SHARES, COST, BOUGHT = 7654, 38.37, date(2024, 3, 17)
LEVEL_PRICE, ENTERED, LEVEL_TEXT = 36.41, date(2026, 9, 14), "Zeta rule 9981 on the low side"


def _company(*, previous="2026-10-02"):
    history = [
        make_trade_item("AAA", qty="1,000,000", name=f"Fictional H{i} Ltd", published=f"2025-0{1 + i}-10", start="2025-01-01", end="2025-01-31")
        for i in range(6)
    ]
    items = [
        make_trade_item("AAA", qty="30,000,000"), make_issue_item(IssueClass.BONUS, 0.1, ex="2026-10-20"),
        make_issue_item(IssueClass.EMPLOYEE, 0.002), make_announcement("news", "AAA: a notice", published="2026-10-08"), *history,
    ]
    return make_company(items, previous=previous, sizing=SizingInput(MODE_OK, COUNT))


def _facts(**company):
    feed = FeedSnapshot("fetched", (), None, 0, FETCHED, FETCHED, False)
    return make_facts("AAA", company=_company(**company), feed=feed)


def _block(lines) -> list[str]:
    lines = list(lines)
    start = next(i for i, line in enumerate(lines) if line.startswith("COMPANY ("))
    end = next((i for i, line in enumerate(lines[start:], start) if line.startswith("YOUR LEVELS")), len(lines))
    return lines[start:end]


def _brief(holding, facts, *, redact):
    return build_brief((TickerReport(holding, facts),), redact=redact, now=NOW)


def _rich_holding():
    return make_holding(
        "AAA", shares=SHARES, cost=COST, purchase_date=BOUGHT, levels=(make_level("below", LEVEL_PRICE, ENTERED, LEVEL_TEXT),),
    )


def _plain_holding():
    return make_holding("AAA", shares=111, cost=99.99, purchase_date=None)


@pytest.mark.parametrize("redact", [False, True], ids=["full", "redacted"])
def test_the_company_block_is_identical_whatever_the_investor_holds(redact):
    rich = _block(_brief(_rich_holding(), _facts(), redact=redact))
    plain = _block(_brief(_plain_holding(), _facts(), redact=redact))

    assert rich == plain and len(rich) > 10


@pytest.mark.parametrize("redact", [False, True], ids=["full", "redacted"])
def test_no_holdings_value_or_date_appears_inside_the_block(redact):
    block = "\n".join(_block(_brief(_rich_holding(), _facts(), redact=redact)))

    for secret in (str(SHARES), f"{SHARES:,}", f"{COST:.2f}", f"{LEVEL_PRICE:.2f}", BOUGHT.isoformat(), ENTERED.isoformat(), "Zeta", "9981"):
        assert secret not in block


def test_the_redacted_block_has_no_trace_of_the_issued_log():
    first = "\n".join(_block(_brief(_rich_holding(), _facts(previous=None), redact=True)))
    later = "\n".join(_block(_brief(_rich_holding(), _facts(previous="2026-10-02"), redact=True)))

    assert first == later
    assert not re.search(r"since the last brief|first brief|earlier brief|2026-10-02", later)


def test_the_full_copy_does_use_the_log_for_its_heading():
    assert "since the last brief" in "\n".join(_block(_brief(_rich_holding(), _facts(), redact=False)))
    assert "no earlier brief for this ticker" in "\n".join(_block(_brief(_rich_holding(), _facts(previous=None), redact=False)))


def test_every_number_in_the_redacted_block_comes_from_the_announcements_the_count_or_the_fixed_sentences():
    from app.services.brief import wording

    block = "\n".join(_block(_brief(_rich_holding(), _facts(), redact=True)))
    numbers = re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", re.sub(r"\d{4}-\d{2}-\d{2}", "", block))
    allowed = set()
    for sentence in wording.fixed_sentences():
        allowed |= set(re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", sentence))
    allowed |= {"1,000,000", "30,000,000", f"{COUNT.count:,}", str(COUNT.year_report), str(COUNT.quarter)}
    allowed |= {"10", "3", "2.3", "0.078", "1", "4", "5", "6", "7", "12", "11", "50", "2025"}  # ratio, counts, percents, days, the benchmark year and the fetch time (hh:mm)

    assert [n for n in numbers if n not in allowed] == []
    assert str(SHARES) not in numbers


# --- the modules cannot see the holdings ----------------------------------------------------------------------------

COMPANY_MODULES = ["sections_company.py", "company_lines.py", "company_facts.py", "announcements.py", "sizing.py", "insider.py", "share_cache.py"]


@pytest.mark.parametrize("name", COMPANY_MODULES)
def test_no_company_module_imports_the_holdings_levels_or_investor_sections(name):
    tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported += [node.module or "", *[f"{node.module}.{a.name}" for a in node.names]]
        elif isinstance(node, ast.Import):
            imported += [a.name for a in node.names]

    allowed_holdings = {"app.services.brief.holdings.TICKER_PATTERN"}  # the ticker pattern only, from the share cache
    bad = [n for n in imported if re.search(r"holdings|levels|sections_holding|compose", n) and n not in allowed_holdings]
    assert bad in ([], ["app.services.brief.holdings"])  # `from ...holdings import TICKER_PATTERN` names the module once


def test_the_section_functions_take_market_facts_only_and_read_only_its_fields():
    fields = {f.name for f in dataclasses.fields(MarketFacts)}
    tree = ast.parse((PACKAGE / "sections_company.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        facts_params = set()
        for argument in node.args.args + node.args.kwonlyargs:
            annotation = ast.unparse(argument.annotation) if argument.annotation else ""
            assert not any(w in annotation for w in ("Holding", "Level", "TickerReport")), (node.name, annotation)
            if "MarketFacts" in annotation:
                facts_params.add(argument.arg)
        for access in ast.walk(node):
            if isinstance(access, ast.Attribute) and isinstance(access.value, ast.Name) and access.value.id in facts_params:
                assert access.attr in fields, (node.name, access.attr)
