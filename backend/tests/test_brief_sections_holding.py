"""sections_holding.py: the position block, the range on the investor's shares, YOUR LEVELS and HOLDINGS LISTED."""

from __future__ import annotations

from datetime import date

from app.services.brief import sections_holding as sh
from app.services.brief import wording
from app.services.brief.levels import Readjusted, check_levels

from .test_brief_support import brief_isolation, make_facts, make_holding, make_level  # noqa: F401


def _text(lines):
    return "\n".join(lines)


# --- header and position ----------------------------------------------------------------------------

def test_the_header_shows_shares_cost_and_the_purchase_date():
    assert sh.ticker_header(make_holding("SAB", shares=1000, cost=41.80)) == (
        "--- SAB · 1,000 shares · cost 41.80 · bought 2025-06-10 ---",
    )


def test_a_missing_purchase_date_reads_not_entered():
    header = sh.ticker_header(make_holding(purchase_date=None))

    assert header[0].endswith("bought not entered ---")


def test_the_spec_gain_on_price():
    lines = sh.position_lines(make_holding(shares=1000, cost=41.80), make_facts(close=42.90))

    assert lines[0] == "Value 42.90M VND; gain/loss on price against your cost +1.10M VND (+2.6%)."


def test_a_loss_carries_minus_signs():
    lines = sh.position_lines(make_holding(shares=1000, cost=41.80), make_facts(close=40.80))

    assert "-1.00M VND (-2.4%)" in lines[0]


def test_the_as_entered_line_is_always_there_and_names_shares_as_of():
    plain = sh.position_lines(make_holding(), make_facts())
    dated = sh.position_lines(make_holding(shares_as_of=date(2025, 7, 1)), make_facts())

    assert plain[1] == wording.AS_ENTERED_LINE
    assert dated[1] == wording.AS_ENTERED_LINE + " Shares as of 2025-07-01."


def test_without_a_close_nothing_is_valued():
    lines = sh.position_lines(make_holding(), make_facts(close=None, last_bar=None, status="no_prices"))

    assert "no stored close" in lines[0] and "VND" not in lines[0]


def test_the_range_on_the_investors_shares():
    lines = sh.range_amount_lines(make_holding(shares=1000), make_facts(close=42.90, band_pct=2.7))

    assert lines == (f"On your 1,000 shares: about ±{1000 * 42.90 * 2.7 / 100 / 1000:,.2f}M VND.",)
    assert lines[0] == "On your 1,000 shares: about ±1.16M VND."


def test_no_amount_without_a_band():
    assert sh.range_amount_lines(make_holding(), make_facts(band_pct=None, band_lo=None, band_hi=None, status="ineligible")) == ()


def test_the_readjusted_levels_sentence_only_for_a_holding_with_levels():
    facts = make_facts(readjusted=Readjusted("2026-07-23", 43.60, 46.60))

    assert sh.readjusted_levels_lines(make_holding(levels=(make_level(),)), facts) == (wording.READJUSTED_LEVELS_NOTE,)
    assert sh.readjusted_levels_lines(make_holding(), facts) == ()
    assert sh.readjusted_levels_lines(make_holding(levels=(make_level(),)), make_facts()) == ()


# --- YOUR LEVELS ----------------------------------------------------------------------------------

def _levels(holding, close):
    return sh.levels_lines(check_levels(holding.levels, close), close)


def test_a_reached_level_reads_exactly_as_the_spec_says():
    holding = make_holding(levels=(make_level("below", 41.60, date(2026, 10, 2), "Trim 300 shares if the close is below 41.60"),))

    lines = _levels(holding, 41.20)

    assert lines[0] == wording.LEVELS_HEADING and lines[-1] == wording.LEVELS_CLOSING
    assert lines[1] == (
        "Trim 300 shares if the close is below 41.60 (you wrote this on 2026-10-02): "
        "REACHED. The last close, 41.20, is below it, by 1.0%."
    )


def test_a_level_not_reached_reads_exactly_as_the_spec_says():
    holding = make_holding(levels=(make_level("below", 41.60, date(2026, 10, 2), "my note"),))

    assert _levels(holding, 42.90)[1] == (
        "my note (you wrote this on 2026-10-02): not reached; the level 41.60 is 3.0% below the close."
    )


def test_an_above_level_says_above():
    holding = make_holding(levels=(make_level("above", 44.00, date(2026, 10, 2), "n"),))

    assert _levels(holding, 43.12)[1].endswith("the level 44.00 is 2.0% above the close.")
    assert _levels(holding, 44.88)[1].endswith("is above it, by 2.0%.")


def test_equal_is_not_reached_with_zero_distance():
    holding = make_holding(levels=(make_level("below", 41.60, date(2026, 10, 2), "n"),))

    assert "not reached; the level 41.60 is 0.0% below the close." in _levels(holding, 41.60)[1]


def test_no_levels_reads_none_set():
    lines = _levels(make_holding(), 42.90)

    assert wording.LEVELS_NONE in lines and lines[-1] == wording.LEVELS_CLOSING


def test_levels_without_a_close_list_each_text_unchecked():
    holding = make_holding(levels=(make_level(text="first"), make_level(text="second")))

    lines = _levels(holding, None)

    assert sum("not checked: no stored close" in line for line in lines) == 2
    assert "first" in _text(lines) and "second" in _text(lines)


def test_the_investors_text_is_verbatim_even_with_transaction_words():
    holding = make_holding(levels=(make_level(text="Sell everything if it hurts; buy more, hold the rest"),))

    assert "Sell everything if it hurts; buy more, hold the rest (you wrote this on" in _levels(holding, 42.90)[1]


def test_control_characters_in_a_text_become_spaces_on_one_line():
    holding = make_holding(levels=(make_level(text="a\nb\tc\x07d"),))

    line = _levels(holding, 42.90)[1]

    assert line.startswith("a b c d (you wrote this on") and "\n" not in line


def test_the_tool_adds_no_instruction_or_direction_words():
    holding = make_holding(levels=(make_level(text="x"), make_level("above", 50.0, text="y")))

    tool_text = _text(_levels(holding, 42.90)).replace("x (", "(").replace("y (", "(")
    assert not any(word in tool_text.lower() for word in ("approach", "should", "consider", "recommend"))


# --- HOLDINGS LISTED -------------------------------------------------------------------------------

def _pair(ticker, shares, close, band):
    holding = make_holding(ticker, shares=shares)
    nulls = dict(band_pct=None, band_lo=None, band_hi=None, status="ineligible") if band is None else {}
    facts = make_facts(ticker, close=close, **({"band_pct": band} if band is not None else nulls))
    return holding, facts


def test_two_holdings_weights_and_the_upper_bound():
    pairs = (_pair("AAA", 600, 10.0, 2.0), _pair("BBB", 400, 10.0, 4.0))  # values 6000 and 4000: 60% / 40%

    lines = sh.holdings_listed_lines(pairs)

    assert lines[0] == "HOLDINGS LISTED (2): AAA 60%, BBB 40%"
    assert lines[1] == (
        "If every holding moved to the edge of its own range in the same direction, the listed holdings would move "
        "about 2.8% (an upper bound for the usual ranges, not a forecast; larger moves are possible)."
    )
    assert len(lines) == 2


def test_a_holding_without_a_range_is_listed_and_left_out_of_the_figure():
    pairs = (_pair("AAA", 600, 10.0, 2.0), _pair("BBB", 400, 10.0, 4.0), _pair("CCC", 100, 10.0, None))

    lines = sh.holdings_listed_lines(pairs)

    assert "CCC" in lines[0] and lines[-1] == "1 listed holding has no range and is left out of this figure."
    # weights are over all three values (6000, 4000, 1000): 0.6/1.1 * 2 + 0.4/1.1 * 4
    assert f"about {(6 / 11) * 2 + (4 / 11) * 4:.1f}%" in lines[1]


def test_several_left_out_use_the_plural():
    pairs = (_pair("AAA", 600, 10.0, 2.0), _pair("BBB", 400, 10.0, None), _pair("CCC", 100, 10.0, None))

    assert sh.holdings_listed_lines(pairs)[-1] == "2 listed holdings have no range and are left out of this figure."


def test_a_holding_without_a_close_has_no_weight_and_no_range():
    pairs = (_pair("AAA", 600, 10.0, 2.0), (make_holding("BBB"), make_facts("BBB", close=None, last_bar=None, status="no_prices", band_pct=None, band_lo=None, band_hi=None)))

    lines = sh.holdings_listed_lines(pairs)

    assert "BBB no weight (no stored close)" in lines[0] and "AAA 100%" in lines[0]
    assert lines[-1].startswith("1 listed holding has no range")


def test_when_no_holding_has_a_range_no_figure_is_made_up():
    pairs = (_pair("AAA", 600, 10.0, None), _pair("BBB", 400, 10.0, None))

    text = _text(sh.holdings_listed_lines(pairs))

    assert "would move about" not in text and "no listed holding has a range" in text


def test_one_holding_prints_no_block():
    assert sh.holdings_listed_lines((_pair("AAA", 600, 10.0, 2.0),)) == ()


def test_an_uncalibrated_range_is_left_out_of_the_figure_and_says_so():
    pairs = (_pair("AAA", 600, 10.0, 2.0), (make_holding("BBB", shares=400), make_facts("BBB", close=10.0, band_pct=9.0, calibrated=False, range_coverage=None, status="uncalibrated")))

    lines = sh.holdings_listed_lines(pairs)

    assert "about 2.0%" not in lines[1] and "about 1.2%" in lines[1]  # 0.6/1.0 weight x 2.0, the 9.0 band is not used
    assert lines[-1] == "1 listed holding has a range whose reliability has not been measured and is left out of this figure."


def test_zero_total_value_does_not_divide_by_zero():
    pairs = (_pair("AAA", 600, 0.0, None), _pair("BBB", 400, 0.0, None))

    lines = sh.holdings_listed_lines(pairs)

    assert lines[0].startswith("HOLDINGS LISTED (2)") and "no weight" in lines[0]


def test_one_line_replaces_control_characters():
    assert sh.one_line("a\nb\x07c") == "a b c"
