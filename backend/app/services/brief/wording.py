"""Every fixed sentence of the brief, the number formatters, and plain wording for each status.

Fixed sentences are module constants so the guards (buy/sell/hold, judgement words, Confidence) can
scan them. The coverage sentence is derived from `coverage_phrase`, never typed, and the brief
disclaimer is a verbatim copy of the "Brief version" blockquote in `docs/DISCLAIMER.md`, guarded by
a test and by `disclaimer_for` at run time.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.services.range import coverage_phrase

# --- fixed sentences --------------------------------------------------------------------------------
HEADER_SENTENCE = "This brief does not update during the week. It does not predict direction."
UNITS_LINE = "Prices are per share in thousand VND."
WEEK_COMPARE_LIMIT = "Compared on stored prices, which may be adjusted for dividends and share issues."
FIRST_BRIEF = "first brief: no previous range"
FOOTER = (
    "These would make a re-read worthwhile: a registered sale or purchase by a major shareholder or insider, a share "
    "issue or capital change, or one of your levels appearing or being reached. Other new announcements are listed "
    "for information. Re-run this brief to refresh."
)
LEVELS_HEADING = "YOUR LEVELS (you wrote these; the brief only checks them against the close)"
LEVELS_CLOSING = "This brief does not place orders; what you do is your decision."
LEVELS_NONE = "none set"
LEVELS_NOT_CHECKED = "not checked: no stored close"
REDACTED_LEVELS_LINE = "not shown in the redacted copy"
REDACTED_NOTICE = "This is the redacted copy: it shows market figures only, not your holdings, costs or levels."
PROVISIONAL_WARNING = (
    "WARNING: today's bar is provisional. The market may still be open, so the closes, ranges and week moves "
    "below can change after the close. Run this brief again after the close."
)
PROVISIONAL_MARK = "provisional"
PROVISIONAL_ISSUE_NOTE = "(that range was issued from a provisional bar)"
TRIGGERS_PREFIX = "Re-read triggers this run:"
LEVELS_REACHED_LABEL = "your levels reached"
AS_ENTERED_LINE = (
    "Shares and cost are shown as entered; they are not adjusted for share issues or dividends in this version."
)
READJUSTED_LIMIT = "This note sees only adjustments that have reached the stored prices."
READJUSTED_LEVELS_NOTE = "Levels you set looking at the earlier price may be on the old price basis."
NOT_REFRESHED_LINE = "Prices were not refreshed this run (--no-refresh)."
REFRESHED_LINE = "Prices refreshed this run."
LAST_BAR_ALL = "Last bar for every holding is {date}."
WEEK_HEADING = "THE WEEK JUST ENDED"
NEXT_FIVE_HEADING = "NEXT 5 TRADING DAYS"
WEEK_UNAVAILABLE = "not enough stored closes to compare a 5-session week."
RANGE_LABEL = "Usual range (typical 5-session move)"
TITLE_NO_PRICES = "WEEKLY CHECK · no stored prices for any holding"

# --- dividends, ex-dates and share issues (`add-dividend-and-ex-date-lines`) -----------------------------
# Every feed-derived line names its source. Placeholders are filled by `dividend_lines*.py`.
FEED_LABEL = "company-announcement source"
DIVIDENDS_HEADING = "DIVIDENDS"
DIVIDENDS_HEADER = "DIVIDENDS (company-announcement source; events last fetched {time} UTC, {age}{failed})"
DIVIDENDS_HEADER_NO_FETCH = "DIVIDENDS (company-announcement source)"
ATTEMPT_FAILED = "; the latest attempt {time} UTC failed"
NOT_FETCHED = (
    "No dividend or share issue can be listed or checked for {ticker}: its events have never been fetched, "
    "which is not the same as none found. To fetch (run by hand; this brief does not run it): {command}"
)
NOT_FETCHED_OK = (
    "No dividend or share issue can be listed or checked for {ticker}: no fetch of its events has succeeded, "
    "which is not the same as none found. To fetch (run by hand; this brief does not run it): {command}"
)
NOT_READABLE = (
    "No dividend or share issue can be listed or checked for {ticker}: its stored events could not be read this run, "
    "which is not the same as none found or never fetched. Run the brief again; to fetch (run by hand; this brief does "
    "not run it): {command}"
)
UNREADABLE_ROWS = "{count} feed row(s) could not be read (company-announcement source)."
SCHEDULED = (
    "Scheduled (company-announcement source, events fetched {time} UTC; dated after the last bar, {last_bar}): {items}. "
    "An announcement made after the last fetch is not shown."
)
SCHEDULED_NONE = "none found"
SCHEDULED_MORE = "and {count} more"
SCHEDULED_CASH = "ex {ex}, {amount} a share{record}"
SCHEDULED_ISSUE = "ex {ex}, {ratio} new shares per 100 held"
SCHEDULED_RIGHTS = "rights offer, ex {ex}: read the notice; not calculated"
SCHEDULED_PENDING = "announced {date}, no ex-date yet: {what}{ratio} (not applied until an ex-date is set)"
OLDER_UNDATED = "{count} older announcement(s) with no ex-date are no longer shown."
WINDOW_CASH = (
    "Ex-date in the window (company-announcement source): ex-dividend {ex}, {amount} per share "
    "(within 7 calendar days of the last bar). {shift} {record}; payout {payout}."
)
WINDOW_SHIFT = "From that day the whole range moves down by the dividend: about {low} to {high}."
WINDOW_SHIFT_NOT_SHOWN = "From that day the whole range moves down by the dividend; the shifted range is not shown."
WINDOW_SHIFT_SEVERAL = "The range moves by more than one ex-date; the shifted range is not shown."
WINDOW_NO_RANGE = "The price moves down by the dividend from that day."
WINDOW_ISSUE = (
    "Share issue in the window (company-announcement source): ex {ex}, {ratio} new shares per 100 held. "
    "The board price is adjusted for the issue the same day{tail}"
)
WINDOW_RIGHTS = (
    "Rights offer in the window (company-announcement source): ex {ex}. Read the notice; not calculated. "
    "The board price may be adjusted the same day{tail}"
)
WINDOW_ISSUE_TAIL = ", so the range above does not apply from then."
WINDOW_RIGHTS_TAIL = ", so the range above may not apply from then."
WINDOW_TAIL_NO_RANGE = "."
RECORD_DATE = "Record date {date}"
RECORD_DATE_NONE = "Record date not announced"
PAYOUT_NONE = "not announced"
UPDATE_ENTRIES = "Your share count and cost per share change from {ex}; update your entries."
SINCE_CASH = "Cash, per share, ex-dates since your purchase date (company-announcement source, which covers from {oldest}): {items}."
SINCE_NONE = "none found"
SINCE_NO_SOURCE_DATE = "Cash, per share, ex-dates since your purchase date (company-announcement source, nothing stored): {items}."
INCOMPLETE = (
    "This list may be incomplete for ex-dates before {horizon}: the source returns a limited number of past "
    "announcements, the oldest stored is dated {oldest}, and an announcement can come up to {lag} days before its ex-date."
)
INCOMPLETE_NOTHING = (
    "This list is not shown as complete: the source holds no stored announcement for this ticker to count from."
)
NO_PURCHASE_DATE = (
    "Cash dividends and share issues since your purchase date: not listed, because no purchase date is entered for this holding."
)
SINCE_ISSUES = (
    "Share issues since your purchase date (company-announcement source; ratio not checked against your broker): "
    "{items}. They change your share count."
)
SINCE_ISSUES_NONE = (
    "Share issues since your purchase date (company-announcement source; ratio not checked against your broker): none."
)
SINCE_ISSUE_ITEM = "ex {ex}, {ratio} new shares per 100 held"
SINCE_RIGHTS = (
    "Rights offer to shareholders, ex {ex} (company-announcement source): read the notice; "
    "not calculated and not applied to your share count."
)
LEVEL_NOTE_CASH = (
    "  Note from the company-announcement source: a dividend of {amount} a share went ex on {ex}, after you "
    "entered this level on {entered}. The board price was adjusted down by about that amount that day, and this "
    "level was set before it. The brief does not change your level.{status}"
)
LEVEL_NOTE_ISSUE = (
    "  Note from the company-announcement source: a share issue of {ratio} new shares per 100 held went ex on "
    "{ex}, after you entered this level on {entered}. The board price was adjusted for it that day, and this "
    "level was set before it. The brief does not change your level.{status}"
)
STATUS_NOT_YET = " Stored history is not yet adjusted for it."
STATUS_UNCLEAR = " Whether stored history is adjusted for it yet could not be told."
BOARD_CASH = (
    "Board move: {board} ({raw} -> {last}); about {amount} of that is the dividend that went ex on {ex}. "
    "Excluding the dividend: {excluding} ({base} -> {last}).{range}"
)
BOARD_ISSUE = (
    "Board move: {board} ({raw} -> {last}); the price adjustment for the share issue ({ratio} new shares per "
    "100 held) that went ex on {ex} is about {adjustment} of the price. Excluding the issue: {excluding} "
    "({base} -> {last}).{range}"
)
BOARD_RANGE_ISSUED = " Last week's range was {band}: the move excluding {what} was {verdict} it."
BOARD_RANGE_RECOMPUTED = (
    " Range recomputed today from prices up to {date}; not an issued range: {band}: the move excluding {what} was {verdict} it."
)
BOARD_FOOTNOTE = (
    "Board figures are calculated from the dividend (company-announcement source, events fetched {time} UTC) and the "
    "stored closes; check your broker's figure."
)
BOARD_FOOTNOTE_ISSUE = (
    "Board figures are calculated from the share issue ratio (company-announcement source, events fetched {time} UTC) "
    "and the stored closes; check your broker's figure."
)
WEEK_EVENT_CASH = "Ex-dividend {ex} ({amount} a share) fell in this week (company-announcement source, events fetched {time} UTC)."
WEEK_EVENT_ISSUE = (
    "Share issue ex {ex} ({ratio} new shares per 100 held) fell in this week "
    "(company-announcement source, events fetched {time} UTC)."
)
WEEK_NOT_YET_CASH = "History is not yet adjusted for the {ex} dividend; the stored move includes it."
WEEK_NOT_YET_ISSUE = "History is not yet adjusted for the {ex} share issue; the stored move includes its effect on the price."
WEEK_UNCLEAR_CASH = (
    "Whether stored history is adjusted for the {ex} dividend yet cannot be told from the stored bars; "
    "the move shown may include or leave out the dividend."
)
WEEK_UNCLEAR_ISSUE = (
    "Whether stored history is adjusted for the {ex} share issue yet cannot be told from the stored bars; "
    "the move shown may include or leave out its effect on the price."
)
WEEK_SEVERAL = (
    "Ex-dates in this week (company-announcement source, events fetched {time} UTC): {dates}. A board move is not calculated for more than "
    "one. Adjustment status by date: {statuses}."
)
STATUS_WORDS = {"ADJUSTED": "adjusted", "NOT_YET_ADJUSTED": "not yet adjusted", "UNCLEAR": "could not be told"}
WEEK_UNKNOWN = "Whether an ex-date fell in this week is not known: no stored events are available for {ticker}."
WEEK_ONE = "Recomputed today from prices up to {date}; not an issued range: {band}. The week's move of {move} {verdict}"
WEEK_ONE_INSIDE = "was inside it."
WEEK_ONE_OUTSIDE = "was outside it."
WEEK_ONE_SUPPRESSED = "is not compared with it: {reason}."
WEEK_ONE_REASONS = {
    "unknown": "whether an ex-date fell in this week is not known",
    "several": "ex-dates fell in this week",
    "not_adjusted": "an ex-date fell in this week",
}
WEEK_ONE_SOURCE = " Ex-dates checked against the company-announcement source, events fetched {time} UTC."
WEEK_ONE_FAILED = "Last week's range could not be recomputed from the stored prices."
READJUSTED_EXPLAINS_CASH = (
    "The company-announcement source lists a dividend of {amount} a share ex {ex}, after {as_of}; "
    "the brief has not checked that it accounts for the difference."
)
READJUSTED_EXPLAINS_ISSUE = (
    "The company-announcement source lists a share issue of {ratio} new shares per 100 held ex {ex}, after {as_of}; "
    "the brief has not checked that it accounts for the difference."
)


def stale_behind_warning(last_bar: str) -> str:
    return f"WARNING: last bar {last_bar} is behind the other holdings'; this holding's figures are stale."


def stale_old_warning(last_bar: str, days: int) -> str:
    return (
        f"WARNING: last bar {last_bar} is more than {days} calendar days before this run; "
        "this holding's figures may be stale."
    )


STALE_REFRESH_WARNING = (
    "WARNING: this holding's prices may be stale: the refresh did not complete, so its last bar may not be the latest."
)
# Appendix K's brief disclaimer, verbatim from docs/DISCLAIMER.md "## Brief version".
BRIEF_DISCLAIMER = (
    'Technical observation, not investment advice. Figures can be wrong or incomplete. '
    '"About 2 weeks in 3" is an estimate from price history, not a promise.'
)
_NOMINAL_PHRASE = "about 2 in 3"


class DisclaimerCoverageMismatch(Exception):
    """The disclaimer says "About 2 weeks in 3" but the model's coverage is another level."""


def disclaimer_for(range_coverage: float) -> str:
    if coverage_phrase(range_coverage) != _NOMINAL_PHRASE:
        raise DisclaimerCoverageMismatch(
            f"the brief disclaimer says 'About 2 weeks in 3' but the model's range coverage is "
            f"{range_coverage:g} ({coverage_phrase(range_coverage)}); update docs/DISCLAIMER.md and the copy together"
        )
    return BRIEF_DISCLAIMER


def coverage_sentence(range_coverage: float) -> str:
    """Derived from `coverage_phrase`, so a retrain at another level cannot leave a wrong sentence."""
    phrase = coverage_phrase(range_coverage)
    if phrase == _NOMINAL_PHRASE:
        return "About 2 weeks in 3 stay inside a range like this; about 1 in 3 is bigger, up or down."
    return f"{phrase[0].upper()}{phrase[1:]} of weeks stay inside a range like this; the rest are bigger, up or down."


def not_measured(ticker: str) -> str:
    return (
        f"How often a range like this holds has not been measured for {ticker}: "
        "it is outside the set the range was calibrated on."
    )


# --- number formatters ------------------------------------------------------------------------------
def fmt_price(value: float) -> str:
    return f"{value:.2f}"


def fmt_millions(value: float) -> str:
    return f"{value:,.2f}M VND"


def fmt_signed_millions(value: float) -> str:
    return f"{_no_negative_zero(value, 2):+,.2f}M VND"


def fmt_signed_pct(value: float) -> str:
    return f"{_no_negative_zero(value, 1):+.1f}%"


def fmt_distance_pct(value: float) -> str:
    return f"{value:.1f}%"


def fmt_weight(value: float) -> str:
    return f"{value:.0f}%"


def fmt_band(band_pct: float) -> str:
    return f"±{round(band_pct, 2):g}%"


def fmt_vnd(value: float) -> str:
    return f"{value:,.0f} VND"


def fmt_new_shares(ratio: float) -> str:
    """A ratio as "new shares per 100 held" without trailing zeros: 0.2604104 -> 26.04, 0.1 -> 10, 1.0 -> 100."""
    return f"{ratio * 100:.2f}".rstrip("0").rstrip(".")


def _no_negative_zero(value: float, digits: int) -> float:
    rounded = round(value, digits)
    return 0.0 if rounded == 0 else value


# --- plain wording for each status and reason -------------------------------------------------------
_REASON_CLAUSES = {
    "delisted": "the stock appears to be delisted",
    "insufficient_history": "there is not enough price history",
    "stale": "stored prices are out of date",
    "near_gap": "there is a gap in recent prices",
    "hard_quality_flag": "a recent price failed a data quality check",
}


def reason_clause(code: str) -> str:
    return _REASON_CLAUSES.get(code, f"unrecognised reason `{code}`")


def no_range_text(status: str, reasons: tuple[str, ...], *, ticker: str, error_class: str | None = None) -> str:
    """The sentence for a holding that has no range this week."""
    if status == "ineligible":
        clauses = "; ".join(reason_clause(code) for code in reasons) or "the ticker is not eligible for a range"
        return f"No range this week: {clauses}."
    if status == "model_unavailable":
        return "No range this week: the volatility model file is missing or unusable."
    if status == "range_out_of_bounds":
        return "No range this week: recent prices look abnormal, so the range is withheld rather than shown."
    if status == "no_prices":
        return f"No stored prices for {ticker}."
    if status == "error":
        return f"This holding could not be computed ({error_class or 'unknown error'}); see the log."
    return f"No range this week (status {status})."


_STATUS_PHRASES = {
    "ineligible": "the ticker was not eligible for a range",
    "model_unavailable": "the volatility model file was missing or unusable",
    "range_out_of_bounds": "recent prices looked abnormal",
    "no_prices": "there were no stored prices",
    "error": "it could not be computed",
}


def status_phrase(status: str) -> str:
    return _STATUS_PHRASES.get(status, f"status {status}")


# --- the re-read triggers line (design D16) -----------------------------------------------------------
JUDGEMENT_WORDS = (
    "attention", "important", "urgent", "alert", "critical", "should", "must", "review", "action", "act",
    "risk", "opportunity", "recommend", "consider",
    # stem forms, so a plural or a past tense cannot slip past a whole-word match
    "risks", "risky", "recommended", "recommendation", "considered",
)
_JUDGEMENT_RE = re.compile(r"\b(" + "|".join(JUDGEMENT_WORDS) + r")\b", re.IGNORECASE)
TRIGGERS_FORMAT = re.compile(r"^Re-read triggers this run: [a-z' -]+: \d+( \(.*\))?(; [a-z' -]+: \d+)*\.$")
TRIGGER_LABEL = re.compile(r"[a-z][a-z -]*")
# Notes are facts about a count and come only from this fixed set; a later change adds its own pattern here.
TRIGGER_NOTE_PATTERNS: list[re.Pattern] = [re.compile(r"\d+ levels? could not be checked: no stored close")]


@dataclass(frozen=True)
class TriggerCount:
    label: str
    count: int
    note: str = ""  # a plain fact about the count, for example levels that could not be checked

    def __post_init__(self) -> None:
        if TRIGGER_LABEL.fullmatch(self.label) is None:
            raise ValueError("a trigger label must match the allowed format: lowercase letters, spaces and hyphens")
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 0:
            raise ValueError("a trigger count must be a non-negative whole number")
        if self.note and not any(pattern.fullmatch(self.note) for pattern in TRIGGER_NOTE_PATTERNS):
            raise ValueError("a trigger note must come from the fixed set of notes")


def judgement_words_in(text: str) -> list[str]:
    """Whole-word, case-insensitive matches of the banned judgement words, in order of appearance."""
    return [match.lower() for match in _JUDGEMENT_RE.findall(text)]


def unchecked_levels_note(count: int) -> str:
    return f"{count} level{'s' if count != 1 else ''} could not be checked: no stored close"


def triggers_line(counts: tuple[TriggerCount, ...]) -> str:
    """`Re-read triggers this run: <label>: <n>[; <label>: <n>].`, validated against the design's guard."""
    parts = [f"{c.label}: {c.count}" + (f" ({c.note})" if c.note else "") for c in counts]
    line = f"{TRIGGERS_PREFIX} " + "; ".join(parts) + "."
    if judgement_words_in(line):
        raise ValueError(f"the triggers line contains a judgement word: {judgement_words_in(line)}")
    if not TRIGGERS_FORMAT.match(line):
        raise ValueError(f"the triggers line does not match its format: {line}")
    return line


# --- the scan every non-investor line passes before the brief is shown (Rules 4 and 6) -----------------
_TOOL_TEXT_BANNED = re.compile(r"\b(buy|sell|hold|confidence)\b|market\s+sentiment", re.IGNORECASE)


def normalise_for_scan(text: str) -> str:
    """NFKC, with zero-width and other format characters removed, so a lookalike cannot hide a word."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text) if unicodedata.category(ch) != "Cf")


def tool_text_violations(text: str) -> list[str]:
    """Banned words found in tool-written text (never call this on the investor's own words)."""
    return [m.group(0).lower() for m in _TOOL_TEXT_BANNED.finditer(normalise_for_scan(text))]


_registered_sentences: list[str] = []


def register_fixed_sentences(*sentences: str) -> None:
    """A later module adds its own fixed text so the guards scan it too."""
    _registered_sentences.extend(sentences)


def fixed_sentences() -> tuple[str, ...]:
    """Every string constant in this module (UPPER_CASE names, and the strings inside an UPPER_CASE dict of
    strings) and every registered sentence."""
    constants: list[str] = []
    for name, value in globals().items():
        if not name.isupper() or name.startswith("_"):
            continue
        if isinstance(value, str):
            constants.append(value)
        elif isinstance(value, dict):
            constants += [v for v in value.values() if isinstance(v, str)]
    return (*constants, *_registered_sentences)
