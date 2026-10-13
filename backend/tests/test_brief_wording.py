"""wording.py: every fixed sentence, the formatters, the coverage sentence and the triggers line."""

from __future__ import annotations

import re

import pytest

from app.services.range import coverage_phrase
from app.services.brief import wording
from app.services.brief.wording import TriggerCount

from .test_brief_support import brief_isolation  # noqa: F401


# --- formatters -----------------------------------------------------------------------------------

def test_prices_have_two_decimals():
    assert wording.fmt_price(42.9) == "42.90" and wording.fmt_price(41.7449) == "41.74"


def test_millions_of_vnd_carry_a_sign_when_asked_and_separators_when_large():
    assert wording.fmt_millions(42.9) == "42.90M VND"
    assert wording.fmt_signed_millions(1.1000000000000014) == "+1.10M VND"
    assert wording.fmt_signed_millions(-0.524) == "-0.52M VND"
    assert wording.fmt_millions(1234.567) == "1,234.57M VND"


def test_simple_percent_has_one_decimal_and_a_sign_and_never_minus_zero():
    assert wording.fmt_signed_pct(2.6315) == "+2.6%"
    assert wording.fmt_signed_pct(-7.65) == "-7.7%"
    assert wording.fmt_signed_pct(-0.04) == "+0.0%"


def test_weights_are_whole_percent_and_distances_one_decimal():
    assert wording.fmt_weight(59.6) == "60%"
    assert wording.fmt_distance_pct(3.0) == "3.0%"


def test_the_band_is_shown_as_the_half_width_without_trailing_zeros():
    assert wording.fmt_band(2.7) == "±2.7%" and wording.fmt_band(2.73) == "±2.73%" and wording.fmt_band(10.0) == "±10%"


# --- coverage sentence and disclaimer -------------------------------------------------------------

def test_the_two_in_three_sentence_is_built_through_coverage_phrase():
    assert coverage_phrase(0.68) == "about 2 in 3"
    assert wording.coverage_sentence(0.68) == (
        "About 2 weeks in 3 stay inside a range like this; about 1 in 3 is bigger, up or down."
    )
    assert wording.coverage_sentence(0.675) == wording.coverage_sentence(0.68)


def test_another_coverage_level_uses_the_phrase_it_gives():
    assert wording.coverage_sentence(0.80) == (
        "About 80% of weeks stay inside a range like this; the rest are bigger, up or down."
    )
    assert wording.coverage_sentence(0.9).startswith("About 90% of weeks")


def test_the_coverage_sentence_is_not_typed_independently(monkeypatch):
    monkeypatch.setattr(wording, "coverage_phrase", lambda c: "about 7 in 9")

    assert wording.coverage_sentence(0.68) == "About 7 in 9 of weeks stay inside a range like this; the rest are bigger, up or down."


def test_the_disclaimer_is_returned_only_for_the_nominal_coverage():
    assert wording.disclaimer_for(0.68) == wording.BRIEF_DISCLAIMER
    with pytest.raises(wording.DisclaimerCoverageMismatch):
        wording.disclaimer_for(0.80)


# --- plain wording for every status ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("code", "fragment"),
    [
        ("delisted", "delisted"),
        ("insufficient_history", "history"),
        ("stale", "out of date"),
        ("near_gap", "gap"),
        ("hard_quality_flag", "quality"),
    ],
)
def test_every_reason_code_has_a_plain_clause(code, fragment):
    assert fragment in wording.reason_clause(code)


def test_an_unknown_reason_prints_the_code():
    assert wording.reason_clause("odd_new_code") == "unrecognised reason `odd_new_code`"


def test_ineligible_gives_one_clause_per_reason():
    text = wording.no_range_text("ineligible", ("stale", "near_gap"), ticker="AAA")

    assert text.startswith("No range this week: ") and text.count(";") == 1
    assert wording.reason_clause("stale") in text and wording.reason_clause("near_gap") in text


def test_the_other_non_ok_statuses_have_their_own_wording():
    assert "volatility model file is missing or unusable" in wording.no_range_text("model_unavailable", (), ticker="AAA")
    out_of_bounds = wording.no_range_text("range_out_of_bounds", (), ticker="AAA")
    assert "abnormal" in out_of_bounds and "withheld" in out_of_bounds
    assert wording.no_range_text("no_prices", (), ticker="AAA") == "No stored prices for AAA."
    assert wording.no_range_text("error", (), ticker="AAA", error_class="KeyError") == (
        "This holding could not be computed (KeyError); see the log."
    )


def test_uncalibrated_has_a_not_measured_sentence():
    assert wording.not_measured("AAA") == (
        "How often a range like this holds has not been measured for AAA: "
        "it is outside the set the range was calibrated on."
    )


def test_an_unknown_status_still_has_wording():
    assert "zzz" in wording.no_range_text("zzz", (), ticker="AAA")


@pytest.mark.parametrize(
    "status", ["ineligible", "model_unavailable", "range_out_of_bounds", "no_prices", "error", "mystery"],
)
def test_logged_statuses_have_a_plain_phrase(status):
    assert wording.status_phrase(status)


# --- the fixed sentences exist exactly as the spec quotes them -------------------------------------

def test_the_fixed_sentences_are_quoted_exactly():
    assert wording.HEADER_SENTENCE == "This brief does not update during the week. It does not predict direction."
    assert wording.UNITS_LINE == "Prices are per share in thousand VND."
    assert wording.WEEK_COMPARE_LIMIT == "Compared on stored prices, which may be adjusted for dividends and share issues."
    assert wording.FIRST_BRIEF == "first brief: no previous range"
    assert wording.FOOTER == (
        "These would make a re-read worthwhile: a registered sale or purchase by a major shareholder or insider, a share issue "
        "or capital change, or one of your levels appearing or being reached. Other new announcements are listed for "
        "information. Re-run this brief to refresh."
    )
    assert wording.LEVELS_CLOSING == "This brief does not place orders; what you do is your decision."
    assert wording.LEVELS_HEADING == "YOUR LEVELS (you wrote these; the brief only checks them against the close)"
    assert wording.REDACTED_LEVELS_LINE == "not shown in the redacted copy"
    assert wording.PROVISIONAL_WARNING == (
        "WARNING: today's bar is provisional. The market may still be open, so the closes, ranges and week moves "
        "below can change after the close. Run this brief again after the close."
    )
    assert wording.TRIGGERS_PREFIX == "Re-read triggers this run:"
    assert wording.LEVELS_REACHED_LABEL == "your levels reached"


def test_every_fixed_sentence_is_listed_for_the_guards():
    listed = wording.fixed_sentences()

    assert wording.HEADER_SENTENCE in listed and wording.BRIEF_DISCLAIMER in listed
    assert wording.TITLE_NO_PRICES in listed and wording.PROVISIONAL_MARK in listed
    assert all(isinstance(text, str) and text for text in listed)


def test_the_list_is_every_string_constant_in_the_module():
    constants = {
        v for k, v in vars(wording).items() if k.isupper() and not k.startswith("_") and isinstance(v, str)
    }

    assert constants <= set(wording.fixed_sentences())


def test_the_strings_inside_an_upper_case_dict_are_scanned_too():
    dict_strings = {
        v for k, d in vars(wording).items() if k.isupper() and not k.startswith("_") and isinstance(d, dict)
        for v in d.values() if isinstance(v, str)
    }

    assert dict_strings and dict_strings <= set(wording.fixed_sentences())
    assert wording.STATUS_WORDS["NOT_YET_ADJUSTED"] in wording.fixed_sentences()


def test_a_later_module_registers_its_own_sentence(monkeypatch):
    monkeypatch.setattr(wording, "_registered_sentences", [])

    wording.register_fixed_sentences("a later module's sentence")

    assert "a later module's sentence" in wording.fixed_sentences()


def test_the_brief_never_calls_anything_confidence():
    assert not any("confidence" in text.lower() for text in wording.fixed_sentences())


@pytest.mark.parametrize(
    "text", ["Buy now", "SELL", "hold it", "Confidence 90%", "Market Sentiment", "market\u00a0sentiment", "ｓｅｌｌ", "b\u200buy", "s\u00adell"],
)
def test_the_tool_text_scan_sees_through_lookalikes_and_zero_width_characters(text):
    assert wording.tool_text_violations(text)


@pytest.mark.parametrize("text", ["holdings", "withheld", "household", "confident", "shold"])
def test_the_tool_text_scan_is_whole_word(text):
    assert wording.tool_text_violations(text) == []


def test_an_ineligible_status_with_no_reasons_has_a_generic_clause():
    assert wording.no_range_text("ineligible", (), ticker="AAA") == (
        "No range this week: the ticker is not eligible for a range."
    )


# --- 5.2a: the triggers line and its guard ---------------------------------------------------------

def test_the_triggers_line_is_printed_at_zero():
    assert wording.triggers_line((TriggerCount("your levels reached", 0),)) == (
        "Re-read triggers this run: your levels reached: 0."
    )


def test_the_triggers_line_appends_a_note_for_unchecked_levels():
    line = wording.triggers_line((TriggerCount("your levels reached", 1, wording.unchecked_levels_note(2)),))

    assert line == (
        "Re-read triggers this run: your levels reached: 1 (2 levels could not be checked: no stored close)."
    )
    assert wording.unchecked_levels_note(1) == "1 level could not be checked: no stored close"


def test_a_later_change_adds_a_count_without_touching_the_format():
    line = wording.triggers_line(
        (TriggerCount("your levels reached", 2), TriggerCount("registered insider trades", 1)),
    )

    assert line == "Re-read triggers this run: your levels reached: 2; registered insider trades: 1."
    assert wording.TRIGGERS_FORMAT.match(line)


@pytest.mark.parametrize(
    "text", ["exact", "contact", "Re-read triggers this run", "interact", "reaction", "reactive", "actor"],
)
def test_the_judgement_guard_lets_whole_word_lookalikes_pass(text):
    assert wording.judgement_words_in(text) == []


@pytest.mark.parametrize(
    ("text", "found"),
    [("act", ["act"]), ("Review", ["review"]), ("please consider", ["consider"]), ("Important: ALERT!", ["important", "alert"])],
)
def test_the_judgement_guard_rejects_whole_words_in_any_case(text, found):
    assert wording.judgement_words_in(text) == found


def test_the_judgement_list_is_the_one_in_the_design():
    assert set(wording.JUDGEMENT_WORDS) >= {
        "attention", "important", "urgent", "alert", "critical", "should", "must", "review", "action", "act",
        "risk", "opportunity", "recommend", "consider",
    }
    assert {"risks", "risky", "recommended", "recommendation", "considered"} <= set(wording.JUDGEMENT_WORDS)


def test_a_label_with_a_judgement_word_cannot_build_a_line():
    for label in ("needs attention", "risks seen", "considered", "recommended items"):
        with pytest.raises(ValueError, match="judgement"):
            wording.triggers_line((TriggerCount(label, 1),))


@pytest.mark.parametrize("label", ["Bad Label!", "UPPER", "digits 3", "it's", "", "semi;colon", "new\nline", "-dash"])
def test_a_label_outside_lowercase_letters_spaces_and_hyphens_is_refused(label):
    with pytest.raises(ValueError, match="format"):
        TriggerCount(label, 1)


@pytest.mark.parametrize("count", [-1, True, 1.5, "2"])
def test_a_count_must_be_a_non_negative_whole_number(count):
    with pytest.raises(ValueError, match="count"):
        TriggerCount("your levels reached", count)


@pytest.mark.parametrize("note", ["free text", "1 level could not be checked: no stored close; act now", "0 levels could not be checked"])
def test_a_note_outside_the_fixed_set_is_refused(note):
    with pytest.raises(ValueError, match="fixed set"):
        TriggerCount("your levels reached", 1, note)


def test_a_later_change_may_add_a_note_pattern(monkeypatch):
    import re

    monkeypatch.setattr(wording, "TRIGGER_NOTE_PATTERNS", [*wording.TRIGGER_NOTE_PATTERNS, re.compile(r"\d+ items could not be read")])

    assert TriggerCount("registered trades", 1, "2 items could not be read").note


def test_the_format_pattern_is_the_design_one():
    assert wording.TRIGGERS_FORMAT.pattern == r"^Re-read triggers this run: [a-z' -]+: \d+( \(.*\))?(; [a-z' -]+: \d+)*\.$"
    assert re.match(wording.TRIGGERS_FORMAT, "Re-read triggers this run: your levels reached: 0.")
