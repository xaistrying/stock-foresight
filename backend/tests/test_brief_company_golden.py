"""Golden files for whole briefs with a COMPANY block (`add-announcement-tags-and-insider-sizing`, task 4.4): a sized
registration with its benchmark, the settling-window fallback with an unclassified notice, and a redacted copy with
disagreeing vendor counts. Fictional ticker and counterparty, synthetic figures, no real title.

Read once against the v5.3 filled examples B, C and D of `docs/DISCUSSION_purpose_and_weekly_brief.md` (Appendix K); the
intended differences are:

- the seller is not "registered to SELL": the line is "filed a notice of a sale of <n> <TICKER> shares (window ...; status:
  not started | under way | ended)" (owner decision 1); "planned, not yet executed" is gone because most stored records
  appear after their window ended, and the status follows the window against the last bar;
- the counterparty name and every title are third-party text inside curly quotes, under the label "Title (third-party text)";
- the size line says "VCI share count via vnstock, latest-quarter row <year>-Q<q>, fetched <date>", never "as of <quarter>";
- the benchmark sentence gives its count, first year, how many were larger, the largest of the others, and its basis;
- the checklist reads "who filed it, whether it is a sale or a purchase, ... how it will be done" (no selling or buying word);
- the tag carries its basis, "(event record)"; the item line is "- <date>, <tag> (<basis>)" and the detail sits on indented lines;
- the one source line of the template is two lines (announcements, corporate events), each with the age of the last answer;
- "none" reads "none found in what the source returned" and is printed only after a fetch, "not checked" otherwise;
- the Scheduled line is the one N2a printed under DIVIDENDS, now in COMPANY with the dated meetings, and ends with its
  after-the-last-fetch sentence;
- a quiet line counts small share issues, and the triggers line near the top carries the announcement counts;
- the redacted copy shows no title and no counterparty name (review fix 3): the trade line reads "A notice of a sale of ... was filed"
  and each item says the title and name are not shown;
- the DIVIDENDS block and the net line are N2a's and N2b's and are absent from these fixtures (no feed events of that kind).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.brief.compose import TickerReport, build_brief
from app.services.brief.feed_source import Event, FeedSnapshot, IssueClass
from app.services.brief.share_cache import ShareCount
from app.services.brief.sizing import MODE_DISAGREE, MODE_OK, SizingInput

from .brief_announcement_rows import d, make_announcement, make_company, make_issue_item, make_trade_item
from .test_brief_support import brief_isolation, ict, make_facts, make_holding  # noqa: F401

GOLDEN = Path(__file__).resolve().parent / "brief_golden"
NOW = ict("2026-10-09 16:30")
FETCHED = datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc)
COUNT = ShareCount(1_282_562_372, 2026, 2, datetime(2026, 10, 12, 5, 0, tzinfo=timezone.utc))
CURRENT = dict(name="Example Holdings Ltd", qty="30,000,000", published="2026-10-08", start="2026-10-12", end="2026-10-23")
BONUS_2023 = Event("ISS", d("2023-09-14"), d("2023-09-15"), None, None, 1.0, d("2023-08-01"), IssueClass.BONUS)


def _earlier_sales():
    """13 earlier sales with a stated quantity: one before the 2023 bonus issue and larger than the current one against the
    count at its own date (53.6% of 641,281,186), then twelve very small ones."""
    rows = [("2018-03-01", "343,662,587"), ("2019-05-10", "100,000"), ("2020-06-10", "80,000")]
    rows += [(f"2024-{1 + i % 12:02d}-{3 + i:02d}", "20,000") for i in range(10)]
    return [
        make_trade_item("AAA", name=f"Example Seller {i} Ltd", qty=qty, published=published, start="2018-01-01", end="2018-01-31")
        for i, (published, qty) in enumerate(rows)
    ]


def _brief(items, events, sizing, *, redact=False, previous="2026-10-02"):
    feed = FeedSnapshot("fetched", tuple(events), None, 0, FETCHED, FETCHED, False)
    facts = make_facts("AAA", company=make_company(items, previous=previous, sizing=sizing), feed=feed)
    return "\n".join(build_brief((TickerReport(make_holding("AAA", shares=1000, cost=41.80), facts),), redact=redact, now=NOW)) + "\n"


def _sized():
    items = [make_trade_item("AAA", **CURRENT), *_earlier_sales(), make_announcement("events", "Example dividend notice", published="2026-10-07", event_code="DIV", exright_date="2026-10-14")]
    return _brief(items, [BONUS_2023], SizingInput(MODE_OK, COUNT))


def _fallback():
    stock = Event("ISS", d("2026-09-24"), d("2026-09-25"), None, None, 0.1, d("2026-08-20"), IssueClass.STOCK_DIVIDEND)
    items = [
        make_trade_item("AAA", **CURRENT), make_announcement("news", "AAA: synthetic penalty notice", published="2026-10-08"),
        make_issue_item(IssueClass.EMPLOYEE, 0.002, published="2026-10-06"), make_issue_item(IssueClass.EMPLOYEE, 0.003, published="2026-10-07"),
        make_announcement("events", "Example meeting notice", published="2026-09-01", event_code="AGME", record_date="2026-10-12"),
    ]
    return _brief(items, [stock], SizingInput(MODE_OK, COUNT))


def _disagree_redacted():
    items = [make_trade_item("AAA", **CURRENT), make_trade_item("AAA", name="Example Buyer Ltd", act="Buy", qty=None, published="2026-10-07")]
    return _brief(items, [], SizingInput(MODE_DISAGREE), redact=True)


CASES = {"company_sized.txt": _sized, "company_settling_fallback.txt": _fallback, "company_disagree_redacted.txt": _disagree_redacted}


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_rendered_brief_equals_its_golden_file(name):
    assert CASES[name]() == (GOLDEN / name).read_text(encoding="utf-8")


def test_the_sized_brief_reproduces_the_numbers_of_example_b():
    text = _sized()

    assert "Size: 2.3% of the shares outstanding (the vendor's count is 1,282,562,372" in text
    assert "(13 sales with a stated quantity, 2018 onward): 1 was larger than this one; the largest of the others was 0.016% of the shares then." in text


def test_the_fallback_names_the_issue_date_and_the_unclassified_notice_like_examples_c_and_d():
    text = _fallback()

    assert "size not shown, because the share count is changing (issue on 2026-09-24)." in text
    assert "Other announcement, not classified; the title gives no amount" in text and "The title does not give the amount; the notice does." in text
