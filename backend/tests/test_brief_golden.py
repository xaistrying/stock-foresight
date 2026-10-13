"""Golden-file tests: a hypothetical two-holding brief and a one-holding first brief, full and redacted.

The fixtures under `brief_golden/` hold only hypothetical figures. Read once against Appendix K of
`docs/DISCUSSION_purpose_and_weekly_brief.md` (v5.3); the deliberate differences are:

- the title line names the newest last bar and "the 5 sessions after" it, not a Friday and a Monday to
  Friday period (Rule 1);
- the units line "Prices are per share in thousand VND." is a fixed line under the header;
- the range is labelled "Usual range (typical 5-session move)" and its edges are `close x exp(-/+ band/100)`;
- the amount on the investor's shares is its own sentence ("On your N shares: ...") instead of a clause;
- the close and the value/gain line are two lines (market line, then the position line);
- HOLDINGS LISTED carries "for the usual ranges ... larger moves are possible" (one clause more);
- a level is checked against "the last close", not "the Friday close";
- the footer is the v5.3 sentence of `add-announcement-tags-and-insider-sizing` (a registered trade, a share issue or a level);
- no net line exists; the DIVIDENDS block appears only for facts that carry a feed snapshot and the COMPANY block only for
  facts that carry announcements (none here).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.brief.compose import TickerReport, build_brief

from .test_brief_support import brief_isolation, ict, make_facts, make_holding, make_level, make_week  # noqa: F401

GOLDEN = Path(__file__).resolve().parent / "brief_golden"
NOW = ict("2026-10-09 16:30")


def _two_holdings() -> tuple[TickerReport, ...]:
    reached = make_level("below", 41.60, date(2026, 10, 2), "Trim 300 shares if the close is below 41.60")
    aaa = TickerReport(
        make_holding("AAA", shares=1234, cost=41.80, levels=(reached,)),
        make_facts("AAA", close=41.20, band_pct=2.7, band_lo=40.10, band_hi=42.34, week=make_week(
            base_close=40.30, last_close=41.20, move_pct=(41.20 / 40.30 - 1) * 100,
        )),
    )
    bbb = TickerReport(
        make_holding("BBB", shares=500, cost=18.25, purchase_date=None),
        make_facts(
            "BBB", close=17.90, status="ineligible", reasons=("stale", "near_gap"), band_pct=None, band_lo=None,
            band_hi=None, range_coverage=None, calibrated=None,
            week=make_week(kind="no_band", prior_status="ineligible", band_pct=None, band_lo=None, band_hi=None,
                           inside=None, base_close=18.10, last_close=17.90, move_pct=(17.90 / 18.10 - 1) * 100),
        ),
    )
    return aaa, bbb


def _one_holding_first() -> tuple[TickerReport, ...]:
    not_reached = make_level("above", 44.00, date(2026, 10, 5), "Look again if it closes above 44.00")
    first_week = make_week(kind="first", band_pct=None, band_lo=None, band_hi=None, inside=None)
    return (TickerReport(
        make_holding("CCC", shares=800, cost=39.50, levels=(not_reached,)),
        make_facts("CCC", close=42.90, band_lo=41.76, band_hi=44.07, week=first_week),
    ),)


CASES = {
    "two_holdings_full.txt": (_two_holdings, False),
    "two_holdings_redacted.txt": (_two_holdings, True),
    "one_holding_first_full.txt": (_one_holding_first, False),
    "one_holding_first_redacted.txt": (_one_holding_first, True),
}


def render(name: str) -> str:
    reports, redact = CASES[name][0](), CASES[name][1]
    return "\n".join(build_brief(reports, redact=redact, now=NOW)) + "\n"


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_rendered_brief_equals_its_golden_file(name):
    assert render(name) == (GOLDEN / name).read_text(encoding="utf-8")
