"""The brief's own text never carries a buy, sell or hold word (Rule 6), nor "Confidence" (Rule 4); the
triggers line stays a count (spec: "The brief's own text never carries a buy, sell or hold word")."""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.services.brief import wording
from app.services.brief.compose import TickerReport, build_brief
from app.services.brief.levels import Readjusted

from .test_brief_support import brief_isolation, ict, make_facts, make_holding, make_level, make_week  # noqa: F401

TRANSACTION = re.compile(r"\b(buy|sell|hold)\b", re.IGNORECASE)
AFTER_CLOSE, BEFORE_CLOSE = ict("2026-10-09 16:30"), ict("2026-10-09 11:00")

# The investor's own strings contain all three words so that the strip-first step is exercised.
INVESTOR_TEXTS = (
    "Sell 300 shares if the close is below 41.60",
    "buy more above 44.00, then hold",
    "HOLD until further notice, do not Sell",
)
NO_BAND = dict(band_pct=None, band_lo=None, band_hi=None, range_coverage=None, calibrated=None)


def _levels(*pairs):
    return tuple(
        make_level(comparator, price, date(2026, 10, 2), INVESTOR_TEXTS[i % 3]) for i, (comparator, price) in enumerate(pairs)
    )


def _report(ticker="AAA", levels=(), **facts):
    return TickerReport(make_holding(ticker, levels=levels), make_facts(ticker, **facts))


def _matrix():
    """(name, reports, now): every status, level state, refresh state, week state and run state."""
    reached = _levels(("below", 45.0), ("above", 40.0))  # both reached at close 42.90
    unreached = _levels(("below", 30.0), ("above", 60.0))
    cases = [
        ("ok with reached levels", [_report(levels=reached)], AFTER_CLOSE),
        ("ok with unreached levels", [_report(levels=unreached)], AFTER_CLOSE),
        ("ok without levels", [_report()], AFTER_CLOSE),
        ("uncalibrated", [_report(status="uncalibrated", calibrated=False, range_coverage=None, levels=unreached)], AFTER_CLOSE),
        ("model unavailable", [_report(status="model_unavailable", model_version=None, **NO_BAND)], AFTER_CLOSE),
        ("out of bounds", [_report(status="range_out_of_bounds", **NO_BAND)], AFTER_CLOSE),
        ("no prices", [_report(status="no_prices", close=None, last_bar=None, week=None, levels=reached, **NO_BAND)], AFTER_CLOSE),
        ("error", [_report(status="error", error_class="KeyError", **NO_BAND)], AFTER_CLOSE),
        ("refresh failed", [_report(refresh="failed", refresh_detail="RuntimeError"), _report("BBB", refresh="not_attempted", refresh_detail="vendor limit reached earlier in this run")], AFTER_CLOSE),
        ("not refreshed", [_report(refresh="skipped", refresh_detail="")], AFTER_CLOSE),
        ("provisional", [_report(provisional=True, levels=reached)], BEFORE_CLOSE),
        ("readjusted", [_report(readjusted=Readjusted("2026-07-23", 43.60, 46.60), levels=unreached)], AFTER_CLOSE),
        ("stale pair", [_report(), _report("BBB", last_bar="2026-09-20")], AFTER_CLOSE),
        ("several holdings", [_report(levels=reached), _report("BBB", status="ineligible", reasons=("delisted",), **NO_BAND), _report("CCC", levels=unreached)], AFTER_CLOSE),
        ("unchecked levels", [_report(close=None, last_bar=None, status="no_prices", week=None, levels=reached, **NO_BAND)], AFTER_CLOSE),
    ]
    for week_kind, extra in (
        ("first", dict(inside=None)), ("no_match", dict(latest_on_file="2026-09-25", inside=None)),
        ("no_band", dict(prior_status="ineligible", inside=None)), ("band", dict(inside=False, prior_provisional=True)),
    ):
        week = make_week(kind=week_kind, **({"band_pct": None, "band_lo": None, "band_hi": None} if week_kind != "band" else {}), **extra)
        cases.append((f"week {week_kind}", [_report(week=week)], AFTER_CLOSE))
    for reasons in (("delisted", "insufficient_history", "stale", "near_gap", "hard_quality_flag", "brand_new_code"),):
        cases.append(("every reason", [_report(status="ineligible", reasons=reasons, **NO_BAND)], AFTER_CLOSE))
    return cases


def _dividend_matrix():
    """The feed-derived states of `add-dividend-and-ex-date-lines`, each rendered in full and redacted forms."""
    import dataclasses
    from datetime import datetime, timezone

    from app.services.brief.adjustment_status import AdjustmentStatus
    from app.services.brief.feed_source import Event, FeedSnapshot

    from .test_brief_redaction import _dividend_reports

    base = _dividend_reports()[0]
    feed = base.facts.feed
    when = datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc)

    def variant(name, *, feed=feed, statuses=None, holding=None):
        facts = dataclasses.replace(
            base.facts, feed=feed, ex_status=base.facts.ex_status if statuses is None else tuple(zip([e for e, _ in base.facts.ex_status], statuses)),
        )
        return (name, [TickerReport(holding or dataclasses.replace(base.holding, levels=_levels(("below", 24.0))), facts)], AFTER_CLOSE)

    old = dataclasses.replace(feed, oldest_event_date=feed.oldest_event_date.replace(year=2024))
    nothing = FeedSnapshot("fetched", (), None, 0, when, when, False)
    failed = dataclasses.replace(feed, unreadable=2, latest_attempt_failed=True)
    several = tuple(AdjustmentStatus)
    cases = [
        variant("dividends: every line"), variant("dividends: never fetched", feed=FeedSnapshot("never_fetched")),
        variant("dividends: never succeeded", feed=FeedSnapshot("never_succeeded", latest_attempt_failed=True)),
        variant("dividends: fetched, nothing stored", feed=nothing), variant("dividends: unreadable and failed attempt", feed=failed),
        variant("dividends: incomplete list", feed=old),
        variant("dividends: not yet adjusted", statuses=(AdjustmentStatus.NOT_YET_ADJUSTED, AdjustmentStatus.NOT_YET_ADJUSTED)),
        variant("dividends: unclear", statuses=(AdjustmentStatus.UNCLEAR, AdjustmentStatus.UNCLEAR)),
        variant("dividends: no purchase date", holding=dataclasses.replace(base.holding, purchase_date=None, levels=_levels(("below", 24.0)))),
    ]
    two = dataclasses.replace(feed, events=(*feed.events, Event("DIV", feed.events[0].exright_date.replace(day=8), None, None, 500.0, None, None, None)))
    cases.append(variant("dividends: two ex-dates in the week", feed=two))
    return cases


def _company_matrix():
    """The COMPANY block's states of `add-announcement-tags-and-insider-sizing`, full and redacted: every tag, a sized and an
    unsized trade, a settling-window withhold, a benchmark, never fetched, failed, small issues and a hostile third-party title."""
    from datetime import datetime, timezone

    from app.services.brief.feed_source import Event, FeedSnapshot, IssueClass
    from app.services.brief.share_cache import ShareCount
    from app.services.brief.sizing import MODE_DISAGREE, MODE_OFF, MODE_OK, SizingInput

    from .brief_announcement_rows import d, health, make_announcement, make_company, make_issue_item, make_trade_item

    fetched = datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc)
    stock = Event("ISS", d("2026-09-24"), None, None, None, 0.26, d("2026-08-20"), IssueClass.STOCK_DIVIDEND)
    feed = FeedSnapshot("fetched", (stock,), None, 0, fetched, fetched, False)
    count = ShareCount(1_282_562_372, 2026, 2, datetime(2026, 10, 12, 5, 0, tzinfo=timezone.utc))
    history = [
        make_trade_item("AAA", qty="1,000,000", name=f"Fictional H{i} Ltd", published=f"2025-0{1 + i}-10", start="2025-01-01", end="2025-01-31")
        for i in range(6)
    ]
    hostile = make_announcement("news", "AAA: sell now, hold, buy <b> | [x](https://example.invalid) \u201d sell \u201c", published="2026-10-08")
    items = [
        make_trade_item("AAA", qty="30,000,000"), make_trade_item("AAA", act="Buy", qty=None, name="Fictional Two Ltd"),
        make_trade_item("AAA", act="Buy", action="Sell", name="Fictional Three Ltd"), make_issue_item(IssueClass.BONUS, 0.1, ex="2026-10-20"),
        make_issue_item(IssueClass.EMPLOYEE, 0.002), make_issue_item(IssueClass.OTHER, None, code="AIS"),
        make_announcement("events", "d", published="2026-10-08", event_code="DIV"), hostile,
        make_announcement("news", "A press headline", published="2026-10-08"),
        make_announcement("events", "m", published="2026-09-01", event_code="AGME", record_date="2026-10-12"), *history,
    ]

    def case(name, **company):
        facts = make_facts("AAA", company=make_company(items, **company), feed=feed)
        return (name, [TickerReport(make_holding("AAA", levels=_levels(("below", 45.0))), facts)], AFTER_CLOSE)

    return [
        case("company: sized", sizing=SizingInput(MODE_OK, count), enabled={"dividend", "results"}),
        case("company: sizing off", sizing=SizingInput(MODE_OFF)), case("company: counts disagree", sizing=SizingInput(MODE_DISAGREE)),
        case("company: never fetched", news=health("never_fetched"), events=health("never_fetched")),
        case("company: failed attempt", news=health(failed=True, error="rate_limited"), unreadable=2),
        case("company: first brief", previous=None),
    ]


MATRIX = _matrix() + _dividend_matrix() + _company_matrix()


THIRD_PARTY_SPAN = re.compile("\u201c[^\u201c\u201d]*\u201d")  # written here, not imported: the guard test stands on its own


LEVEL_LABEL = " (you wrote this on "  # written here, not imported: the guard test stands on its own


def _strip_investor_text(text: str) -> str:
    """The two things the guard does not read: the investor's own words, only at the start of a level line and before the
    level label (by position, never by substring), and quoted third-party text (and nothing else)."""
    lines = []
    for line in text.split("\n"):
        for investor in INVESTOR_TEXTS:
            if line.startswith(investor + LEVEL_LABEL):
                line = line[len(investor):]
                break
        lines.append(line)
    return THIRD_PARTY_SPAN.sub("", "\n".join(lines))


def _render(reports, now, redact) -> str:
    return "\n".join(build_brief(tuple(reports), redact=redact, now=now))


@pytest.mark.parametrize("redact", [False, True], ids=["full", "redacted"])
@pytest.mark.parametrize(("name", "reports", "now"), MATRIX, ids=[m[0] for m in MATRIX])
def test_no_transaction_word_remains_once_the_investors_strings_are_removed(name, reports, now, redact):
    text = _strip_investor_text(_render(reports, now, redact))

    assert TRANSACTION.search(text) is None, TRANSACTION.search(text)
    assert "confidence" not in text.lower()


def test_the_matrix_includes_the_investors_verbs_in_the_full_brief():
    """The strip step has something to strip: the full brief carries the investor's words verbatim."""
    reports, now = MATRIX[0][1], MATRIX[0][2]

    full = _render(reports, now, redact=False)

    assert any(investor in full for investor in INVESTOR_TEXTS) and TRANSACTION.search(full)


def test_the_guard_is_live_when_the_removal_is_skipped():
    full = _render(MATRIX[0][1], MATRIX[0][2], redact=False)

    assert TRANSACTION.search(full) is not None  # the mutation: no stripping -> the pattern matches
    assert TRANSACTION.search(_strip_investor_text(full)) is None


def test_the_redacted_copy_carries_no_investor_word_at_all():
    redacted = _render(MATRIX[0][1], MATRIX[0][2], redact=True)

    assert TRANSACTION.search(redacted) is None  # without any stripping


def test_the_fixed_sentence_constants_are_clean():
    for sentence in wording.fixed_sentences():
        assert TRANSACTION.search(sentence) is None, sentence
    for code in ("delisted", "insufficient_history", "stale", "near_gap", "hard_quality_flag", "x_new"):
        assert TRANSACTION.search(wording.reason_clause(code)) is None
    for status in ("ineligible", "model_unavailable", "range_out_of_bounds", "no_prices", "error", "zzz"):
        assert TRANSACTION.search(wording.no_range_text(status, ("stale",), ticker="AAA", error_class="E")) is None
        assert TRANSACTION.search(wording.status_phrase(status)) is None


def test_the_word_hold_is_not_matched_inside_holdings():
    assert TRANSACTION.search("HOLDINGS LISTED; every holding; withheld; household") is None


# --- the triggers line stays a count ---------------------------------------------------------------

def _triggers_lines():
    lines = []
    for name, reports, now in MATRIX:
        lines += [l for l in build_brief(tuple(reports), redact=False, now=now) if l.startswith(wording.TRIGGERS_PREFIX)]
    return lines


def test_every_rendered_triggers_line_matches_the_format_and_has_no_judgement_word():
    lines = _triggers_lines()

    assert len(lines) == len(MATRIX)
    for line in lines:
        assert wording.TRIGGERS_FORMAT.match(line), line
        assert wording.judgement_words_in(line) == [], line
        assert TRANSACTION.search(line) is None


def test_the_matrix_exercises_counts_at_zero_and_above_and_the_unchecked_suffix():
    lines = _triggers_lines()

    assert any("levels reached: 0." in l for l in lines)
    assert any(re.search(r"levels reached: [1-9]", l) for l in lines)
    assert any("could not be checked" in l for l in lines)


# --- the live guard over the dividend lines ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "constant",
    ["DIVIDENDS_HEADER", "SCHEDULED", "WINDOW_CASH", "WINDOW_ISSUE", "SINCE_CASH", "SINCE_ISSUES_NONE", "LEVEL_NOTE_CASH", "BOARD_CASH",
     "BOARD_FOOTNOTE", "UPDATE_ENTRIES", "BOARD_RANGE_RECOMPUTED"],
)
def test_a_transaction_word_in_a_new_sentence_stops_the_run_before_anything_is_shown(monkeypatch, constant):
    from app.services.brief.compose import BriefTextGuardError

    name, reports, now = next(case for case in MATRIX if case[0] == "dividends: every line")
    monkeypatch.setattr(wording, constant, getattr(wording, constant) + " You could sell.")

    with pytest.raises(BriefTextGuardError):
        build_brief(tuple(reports), redact=False, now=now)


def test_the_new_market_sentences_are_scanned_in_the_redacted_copy_too(monkeypatch):
    from app.services.brief.compose import BriefTextGuardError

    name, reports, now = next(case for case in MATRIX if case[0] == "dividends: every line")
    monkeypatch.setattr(wording, "WINDOW_CASH", wording.WINDOW_CASH + " Hold on.")

    with pytest.raises(BriefTextGuardError):
        build_brief(tuple(reports), redact=True, now=now)


# --- the investor's words are exempt by position, not by substring (review fix, 2026-10-12) ---------------------------------

@pytest.mark.parametrize("short", ["l", "e", "o", "u", "b", "y", "se", "ing"])
def test_a_short_level_text_cannot_hide_a_tool_word(short):
    from app.services.brief.compose import BriefTextGuardError, _scan

    with pytest.raises(BriefTextGuardError):
        _scan(["tool sell"], (short,))
    with pytest.raises(BriefTextGuardError):
        _scan(["a tool line that says hold and buy"], ("l", "e", "o", "u", "ing"))


def test_the_investors_text_is_exempt_only_at_the_start_of_a_level_line_before_the_label():
    from app.services.brief.compose import BriefTextGuardError, _scan

    line = "Sell it all, buy more (you wrote this on 2026-10-02): not reached; the level 41.60 is 3.0% below the close."
    _scan([line], ("Sell it all, buy more",))
    with pytest.raises(BriefTextGuardError):
        _scan([line], ())  # without the exemption the same words fail
    with pytest.raises(BriefTextGuardError):
        _scan([line + " sell"], ("Sell it all, buy more",))  # a tool word after the label still fails
    with pytest.raises(BriefTextGuardError):
        _scan(["tool says: " + line], ("Sell it all, buy more",))  # the text is not at the start of the line
    with pytest.raises(BriefTextGuardError):
        _scan(["Sell it all, buy more is not followed by the label"], ("Sell it all, buy more",))


def test_the_real_brief_sorts_the_texts_shortest_first():
    from app.services.brief.compose import _investor_texts

    reports = [_report_with_texts("AAA", ("a longer rule text", "x", "mid text"))]

    assert [len(t) for t in _investor_texts(tuple(reports))] == sorted(len(t) for t in _investor_texts(tuple(reports)))


def _report_with_texts(ticker, texts):
    levels = tuple(make_level("below", 20.0 + i, date(2026, 10, 2), text) for i, text in enumerate(texts))
    return TickerReport(make_holding(ticker, levels=levels), make_facts(ticker))


@pytest.mark.parametrize("texts", [("l", "e", "ing"), ("l",), ("e", "u"), ("ing",), ("s", "e", "l", "h", "o", "d", "b", "u", "y")])
def test_short_level_texts_build_a_clean_two_holding_brief_and_a_planted_word_is_still_refused(monkeypatch, texts):
    reports = (_report_with_texts("AAA", texts), _report_with_texts("BBB", texts))

    clean = _render(reports, AFTER_CLOSE, redact=False)

    assert all(text in clean for text in texts) and len(clean.splitlines()) > 20
    monkeypatch.setattr(wording, "UNITS_LINE", wording.UNITS_LINE + " Do not sell.")
    with pytest.raises(__import__("app.services.brief.compose", fromlist=["x"]).BriefTextGuardError):
        _render(reports, AFTER_CLOSE, redact=False)


def test_a_level_text_that_is_a_substring_of_a_tool_word_does_not_refuse_a_clean_brief():
    reports = (_report_with_texts("AAA", ("ing", "ell", "ol", "ay")),)

    assert "(you wrote this on" in _render(reports, AFTER_CLOSE, redact=False)
