"""--redact: nothing derived from holdings survives, tested by content and by an allow-list of numbers
(spec: "--redact removes everything derived from holdings and keeps tickers"; design D11)."""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.services.brief import wording
from app.services.brief.compose import TickerReport, build_brief
from app.services.brief.levels import Readjusted

from .test_brief_support import brief_isolation, ict, make_facts, make_holding, make_level, make_week  # noqa: F401

NOW = ict("2026-10-09 11:00")  # before 15:15 ICT: a provisional run
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")

# Distinctive hypothetical holdings: none of these numbers may appear in the redacted copy.
SHARES_A, COST_A, BOUGHT_A = 7654, 38.37, date(2024, 3, 17)
SHARES_B, COST_B = 2917, 19.46
LEVEL_PRICES = (36.41, 47.93)
LEVEL_TEXTS = ("Zeta rule 9981 on the low side", "Kappa rule 5527 on the high side")
ENTERED = date(2026, 9, 14)


def _reports() -> tuple[TickerReport, ...]:
    aaa = TickerReport(
        make_holding(
            "AAA", shares=SHARES_A, cost=COST_A, purchase_date=BOUGHT_A, shares_as_of=date(2025, 1, 6),
            levels=(
                make_level("below", LEVEL_PRICES[0], ENTERED, LEVEL_TEXTS[0]),
                make_level("above", LEVEL_PRICES[1], ENTERED, LEVEL_TEXTS[1]),
            ),
        ),
        make_facts("AAA", close=42.90, provisional=True, readjusted=Readjusted("2026-07-23", 43.60, 46.60)),
    )
    bbb = TickerReport(
        make_holding("BBB", shares=SHARES_B, cost=COST_B, levels=(make_level("below", 20.02, ENTERED, LEVEL_TEXTS[0]),)),
        make_facts("BBB", close=18.35, refresh="failed", refresh_detail="RuntimeError", band_pct=3.4, band_lo=17.74, band_hi=18.98,
                   week=make_week(kind="first", band_pct=None, band_lo=None, band_hi=None, inside=None,
                                  base_close=18.10, last_close=18.35, move_pct=1.38)),
    )
    return aaa, bbb


def _redacted(reports=None) -> str:
    return "\n".join(build_brief(reports or _reports(), redact=True, now=NOW))


def _forms(value: float) -> set[str]:
    """Common ways a number could be printed."""
    forms = {f"{value:g}", f"{value:.1f}", f"{value:.2f}", f"{value:,.2f}", f"{value:,.0f}", f"{value:.0f}"}
    return {form for form in forms if len(form.replace(".", "").replace(",", "")) >= 3}


def _holdings_values() -> dict[str, set[str]]:
    shares = {str(SHARES_A), f"{SHARES_A:,}", str(SHARES_B), f"{SHARES_B:,}"}
    cost = _forms(COST_A) | _forms(COST_B)
    levels = set().union(*(_forms(p) for p in (*LEVEL_PRICES, 20.02)))
    value_a, value_b = SHARES_A * 42.90 / 1000, SHARES_B * 18.35 / 1000  # millions of VND
    amounts = _forms(value_a) | _forms(value_b) | _forms(SHARES_A * (42.90 - COST_A) / 1000)
    return {"shares": shares, "cost": cost, "levels": levels, "amounts": amounts}


def _contains(text: str, form: str) -> bool:
    return re.search(rf"(?<![\d.,]){re.escape(form)}(?![\d])", text) is not None


def _allowed_numbers(reports: tuple[TickerReport, ...]) -> set[str]:
    """Numbers the market facts and the fixed sentences can legitimately put on the page."""
    allowed = {"5"}  # the horizon: "the 5 sessions after", "5-session", "5 calendar days"
    for sentence in (*wording.fixed_sentences(), wording.coverage_sentence(0.68), wording.not_measured("AAA")):
        allowed |= set(NUMBER.findall(sentence))
    for report in reports:
        f = report.facts
        numbers = [f.close, f.band_lo, f.band_hi]
        if f.week:
            numbers += [f.week.base_close, f.week.last_close, f.week.band_lo, f.week.band_hi]
        if f.readjusted:
            numbers += [f.readjusted.stored, f.readjusted.issued]
        allowed |= {wording.fmt_price(n) for n in numbers if n is not None}
        if f.band_pct is not None:
            allowed.add(f"{round(f.band_pct, 2):g}")
        if f.week:
            allowed.add(f"{abs(round(f.week.move_pct, 1)):.1f}")
            if f.week.band_pct is not None:
                allowed.add(f"{round(f.week.band_pct, 2):g}")
    return allowed


def _unexpected_numbers(text: str, reports: tuple[TickerReport, ...]) -> list[str]:
    allowed = _allowed_numbers(reports)
    return [token for token in NUMBER.findall(ISO_DATE.sub("", text)) if token not in allowed]


def _market_dates(reports) -> set[str]:
    dates = set()
    for report in reports:
        f = report.facts
        dates |= {f.last_bar}
        if f.week:
            dates |= {f.week.first_date, f.week.last_date, f.week.base_date}
        if f.readjusted:
            dates.add(f.readjusted.date)
    return dates


# --- no holdings value in any common format ------------------------------------------------------------

@pytest.mark.parametrize("group", ["shares", "cost", "levels", "amounts"])
def test_no_holdings_value_appears_in_any_common_format(group):
    text = _redacted()

    leaked = [form for form in _holdings_values()[group] if _contains(text, form)]

    assert leaked == []


def test_no_date_the_investor_entered_appears():
    text = _redacted()

    for entered in (BOUGHT_A.isoformat(), ENTERED.isoformat(), "2025-01-06"):
        assert entered not in text


def test_the_investors_level_texts_do_not_appear():
    text = _redacted()

    assert not any(fragment in text for fragment in ("Zeta", "Kappa", "9981", "5527"))


def test_every_iso_date_is_a_market_date():
    reports = _reports()

    assert set(ISO_DATE.findall(_redacted(reports))) <= _market_dates(reports)


def test_every_number_token_is_in_the_allow_list_built_from_market_facts():
    reports = _reports()

    assert _unexpected_numbers(_redacted(reports), reports) == []


def test_the_allow_list_check_catches_a_number_nobody_thought_about():
    reports = _reports()
    text = _redacted(reports) + "\nWeight 61%; fall to level 33.17 is 8.4% away."

    assert _unexpected_numbers(text, reports) == ["61", "33.17", "8.4"]


# --- the inference routes named in review ---------------------------------------------------------------

def test_no_gain_loss_figure_so_cost_cannot_be_recovered_from_a_percentage_and_the_close():
    text = _redacted()

    assert not re.search(r"\bgain\b|\bloss\b|your cost|\bvalue\b|M VND", text, re.I)
    assert "%" not in re.sub(r"±?\d+(\.\d+)?%", "", text).replace("About 80%", "")  # only market percentages remain


def test_no_distance_from_a_level_so_a_level_cannot_be_recovered_from_a_distance_and_the_close():
    text = _redacted()

    assert not re.search(r"REACHED|not reached;|the level \d|you wrote this|by \d", text)


def test_no_weight_and_no_upper_bound_figure():
    text = _redacted()

    assert "HOLDINGS LISTED" not in text and "upper bound" not in text and "edge of its own range" not in text


# --- 8.2a: the triggers line and the provisional run ---------------------------------------------------

def test_the_redacted_copy_has_no_triggers_line_and_no_level_count():
    text = _redacted()

    assert "Re-read triggers" not in text and "levels reached" not in text and "could not be checked" not in text


def test_the_provisional_warning_and_mark_stay_in_the_redacted_copy():
    lines = build_brief(_reports(), redact=True, now=NOW)

    assert lines[1] == wording.PROVISIONAL_WARNING
    assert "Close 42.90 (2026-10-09, provisional)" in lines


def test_the_allow_list_still_holds_for_a_provisional_run():
    reports = _reports()
    lines = build_brief(reports, redact=True, now=NOW)

    assert any(wording.PROVISIONAL_WARNING == line for line in lines)
    assert _unexpected_numbers("\n".join(lines), reports) == []


def test_the_levels_line_is_fixed_whether_or_not_levels_exist():
    reports = (*_reports(), TickerReport(make_holding("CCC"), make_facts("CCC")))

    levels_lines = [l for l in build_brief(reports, redact=True, now=NOW) if l.startswith("YOUR LEVELS")]

    assert levels_lines == [f"YOUR LEVELS: {wording.REDACTED_LEVELS_LINE}"] * 3


def test_the_redacted_copy_names_what_it_is():
    assert wording.REDACTED_NOTICE in build_brief(_reports(), redact=True, now=NOW)


def test_the_same_ticker_renders_identically_across_holdings_with_and_without_levels():
    facts = make_facts("AAA")
    plain = TickerReport(make_holding("AAA"), facts)
    rich = TickerReport(make_holding("AAA", shares=SHARES_A, levels=(make_level(text=LEVEL_TEXTS[0]),)), facts)

    assert build_brief((plain,), redact=True, now=NOW) == build_brief((rich,), redact=True, now=NOW)


# --- 8.2: the market sections cannot see the holdings --------------------------------------------------

def _market_modules():
    from pathlib import Path

    from app.services.brief import sections_market

    modules = sorted(Path(sections_market.__file__).parent.glob("sections_market*.py"))
    assert modules, "no market sections module found"
    return modules


@pytest.mark.parametrize("path", _market_modules(), ids=lambda p: p.name)
def test_every_market_sections_module_has_none_of_the_investors_words(path):
    source = path.read_text(encoding="utf-8").lower()

    for word in ("shares", "cost", "purchase", "holding", "level"):
        assert word not in source, word


@pytest.mark.parametrize("path", _market_modules(), ids=lambda p: p.name)
def test_market_functions_take_only_market_facts_and_read_only_its_fields(path):
    import ast
    import dataclasses

    from app.services.brief.facts import MarketFacts

    fields = {f.name for f in dataclasses.fields(MarketFacts)}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
            assert not any(("holdings" in n or "levels" in n or "sections_holding" in n) for n in imported), imported
        if not isinstance(node, ast.FunctionDef):
            continue
        facts_params = set()
        for argument in node.args.args + node.args.kwonlyargs:
            annotation = ast.unparse(argument.annotation) if argument.annotation else ""
            assert not any(w in annotation for w in ("Holding", "Level", "TickerReport")), (node.name, annotation)
            if annotation == "MarketFacts":
                facts_params.add(argument.arg)
        for access in ast.walk(node):
            if isinstance(access, ast.Attribute) and isinstance(access.value, ast.Name) and access.value.id in facts_params:
                assert access.attr in fields, (node.name, access.attr)  # only a field the market facts really have


# --- the dividend and ex-date lines (`add-dividend-and-ex-date-lines`): market lines stay, the rest is dropped ----------

def _dividend_reports():
    from datetime import datetime, timezone

    from app.services.brief import corporate_actions as ca
    from app.services.brief.adjustment_status import adjustment_status
    from app.services.brief.company_facts import CompanyFacts
    from app.services.brief.feed_source import AnnouncementRead, Event, FeedSnapshot, IssueClass
    from app.services.brief.sizing import MODE_OFF, SizingInput

    from .brief_event_rows import bars_from, d, model_with_sigma

    bars = bars_from(
        [("2026-10-02", 28.2, 28.2), ("2026-10-05", 28.2, 28.2), ("2026-10-06", 28.2, 28.2), ("2026-10-07", 28.1, 28.2),
         ("2026-10-08", 28.2, 28.2), ("2026-10-09", 28.3, 28.3)], level=28.2,
    )
    model = model_with_sigma(1.0)
    ex_week = Event("DIV", d("2026-10-07"), d("2026-10-08"), None, 2000.0, None, d("2026-09-20"), None)
    earlier = Event("DIV", d("2026-09-30"), d("2026-10-01"), None, 1700.0, None, d("2026-09-10"), None)  # after the level was entered
    window_issue = Event("ISS", d("2026-10-14"), None, None, None, 0.1, d("2026-09-28"), IssueClass.BONUS)
    window_cash = Event("DIV", d("2026-10-15"), None, d("2026-11-10"), 1500.0, None, d("2026-09-29"), None)
    snapshot = FeedSnapshot(
        "fetched", events=(ex_week, earlier, window_issue, window_cash), oldest_event_date=d("2017-05-15"),
        last_success_at=datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc), latest_attempt_at=datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc),
    )
    statuses = tuple((e, adjustment_status(e, bars.dates, bars.opens, bars.closes, model)) for e in (ex_week, earlier))
    facts = make_facts(
        "AAA", close=28.3, band_pct=None, band_lo=None, band_hi=None, range_coverage=None, calibrated=None, status="ok",
        week=make_week(kind="first", band_pct=None, band_lo=None, band_hi=None, inside=None, base_close=28.2, last_close=28.3,
                       move_pct=(28.3 / 28.2 - 1) * 100, base_date="2026-10-02", first_date="2026-10-05"),
        dates=bars.dates, opens=bars.opens, closes=bars.closes, model=model, feed=snapshot, ex_status=statuses,
        company=CompanyFacts(AnnouncementRead(), date(2026, 10, 12), None, SizingInput(MODE_OFF)),  # the one Scheduled line is in COMPANY
    )
    holding = make_holding(
        "AAA", shares=SHARES_A, cost=COST_A, purchase_date=BOUGHT_A,
        levels=(make_level("below", LEVEL_PRICES[0], ENTERED, LEVEL_TEXTS[0]),),
    )
    assert [s.name for _, s in statuses] == ["ADJUSTED", "ADJUSTED"]
    assert ca.events_in_window(snapshot.events, d("2026-10-09")) == (window_issue, window_cash)
    return (TickerReport(holding, facts),)


def _feed_numbers(reports) -> set[str]:
    from app.services.brief import corporate_actions as ca
    from app.services.brief.week_move import board_move

    allowed: set[str] = set()
    for report in reports:
        f = report.facts
        for e in f.feed.events:
            if e.value_per_share:
                allowed |= {f"{e.value_per_share:,.0f}", f"{e.value_per_share:.0f}"}
            if e.exercise_ratio:
                allowed.add(wording.fmt_new_shares(e.exercise_ratio))
        for event, _ in f.ex_status:
            move = board_move(event, f.dates, f.closes)
            if move:
                allowed |= {wording.fmt_price(v) for v in (move.raw_prior, move.base_close, move.last_close)}
                allowed |= {f"{abs(round(v, 1)):.1f}" for v in (move.board_pct, move.excluding_pct)}
        allowed.add("1")  # "1 calendar day after the last bar"
        fetched = f.feed.last_success_at
        allowed |= {f"{fetched.hour:02d}", f"{fetched.minute:02d}"}  # "12:11 UTC": the fetch time
    return allowed


def test_the_redacted_dividend_lines_keep_the_market_part_and_drop_the_rest():
    text = _redacted(_dividend_reports())

    assert "DIVIDENDS (company-announcement source; events last fetched 2026-10-10 12:11 UTC" in text
    assert "Scheduled (company-announcement source, events fetched 2026-10-10 12:11 UTC; dated after the last bar, 2026-10-09)" in text
    assert "Share issue in the window (company-announcement source): ex 2026-10-14, 10 new shares per 100 held." in text
    assert "Ex-date in the window (company-announcement source): ex-dividend 2026-10-15, 1,500 VND per share" in text
    assert "Board move: " in text and "the dividend that went ex on 2026-10-07" in text and "Board figures are calculated" in text
    for fragment in (
        "since your purchase date", "Note from", "update your entries", "may be incomplete", "Last week's range", "Recomputed",
        "first brief", "not shown as complete", "Move:",
    ):
        assert fragment not in text, fragment


def test_no_purchase_date_level_date_or_level_note_reaches_the_redacted_dividend_lines():
    text = _redacted(_dividend_reports())

    for secret in (BOUGHT_A.isoformat(), ENTERED.isoformat(), "Zeta", "Kappa", "9981", "5527", f"{SHARES_A:,}", str(SHARES_A)):
        assert secret not in text
    assert not any(_contains(text, form) for group in _holdings_values().values() for form in group)


def test_the_dividend_numbers_in_the_redacted_copy_are_in_an_allow_list_built_from_the_feed_and_the_bars():
    reports = _dividend_reports()
    text = _redacted(reports)

    unexpected = [
        token for token in NUMBER.findall(ISO_DATE.sub("", text))
        if token not in _allowed_numbers_with_feed(reports)
    ]

    assert unexpected == []
    assert "30" not in _feed_numbers(reports) | {"x"}  # the allow-list is not trivially everything


def _allowed_numbers_with_feed(reports) -> set[str]:
    return _allowed_numbers(reports) | _feed_numbers(reports)


def test_the_dividend_allow_list_catches_an_unexpected_number():
    reports = _dividend_reports()
    text = _redacted(reports) + "\nYou bought 51 days before the 2,350 VND dividend."

    unexpected = [t for t in NUMBER.findall(ISO_DATE.sub("", text)) if t not in _allowed_numbers_with_feed(reports)]

    assert unexpected == ["51", "2,350"]


def test_the_unredacted_copy_has_the_lists_the_notes_and_the_range_clause_the_redacted_one_lacks():
    reports = _dividend_reports()

    full = "\n".join(build_brief(reports, redact=False, now=NOW))

    assert "since your purchase date" in full and "Note from the company-announcement source" in full
    assert "Your share count and cost per share change from 2026-10-14; update your entries." in full
    assert "first brief: no previous range." in full and "Recomputed" not in full.split("Board move")[0]
