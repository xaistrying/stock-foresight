"""Every fixed sentence of the COMPANY block and its trigger labels (`add-announcement-tags-and-insider-sizing`).

Fixed sentences are UPPER_CASE module constants, registered with `wording.register_fixed_sentences` so the guards that
scan `wording.py` scan these too. None contains a buy, sell or hold word, the word routine, or either of the two
quotation marks that delimit third-party text (U+201C and U+201D): those characters come only from
`third_party_text.third_party()`, and the run-time scan exempts only what sits between them (Rule 6). A registered trade
is worded with the nouns "sale" and "purchase". Nothing here predicts direction or says what to do.
"""

from __future__ import annotations

from app.services.brief import wording

# --- the block and its parts ------------------------------------------------------------------------------
COMPANY_HEADING = (
    "COMPANY (company-announcement source from VCI; text in curly quotes is third-party text, shown as the source "
    "gave it, not written or checked by this brief)"
)
COMPANY_HEADING_REDACTED = (
    "COMPANY (company-announcement source from VCI; the redacted copy shows no title and no counterparty name, "
    "because they are third-party text)"
)
TITLE_OMITTED = "Title and name: not shown in the redacted copy; read the notice."
NEEDS_SINCE = "Needs a look since the last brief:"
NEEDS_FIRST = "Needs a look, last 14 days (there is no earlier brief for this ticker, so the last 14 calendar days are listed):"
NEEDS_FIXED = "Needs a look, last 14 days before the last bar:"
INFORMATION = "For information:"
PART_NONE = "none found in what the source returned"
PART_NOT_CHECKED = "not checked"
PART_PARTIAL = "none found in what the source returned ({unchecked} not checked)"
NEEDS_MORE = "{count} more item(s) under this heading exist and are not shown (the newest {shown} are shown)."
INFORMATION_MORE = "{count} more item(s) for information exist and are not shown (the newest {shown} are shown)."
COMPANY_FAILED = "COMPANY: could not build this block ({error}); the other lines for this ticker are unaffected."
SMALL_ISSUES = "{count} small share issue(s), each under 1% of the shares ({classes}), not listed."
SMALL_ISSUES_UNSTATED = "{count} small share issue(s), each under 1% of the shares or of unstated size ({classes}), not listed."

# --- source health ----------------------------------------------------------------------------------------
LABEL_NEWS = "announcement source"
LABEL_EVENTS = "corporate events"
HEALTH_NEWS = "announcement source answered {answered}; {count} returned; newest {newest}{limit}{old}{age}"
HEALTH_EVENTS = "corporate events: answered {answered}; {count} returned; newest {newest}{limit}{old}{age}"
HEALTH_NO_ITEM = "no item stored"
HEALTH_LIMIT = " (the source's limit per call; older items are not retrievable)"
HEALTH_OLD = ", {days} before the last bar; nothing newer was returned"
HEALTH_AGE = "; the last answer was {age}"
HEALTH_FAILED = "{label}: the latest attempt {when} UTC failed ({error}); last answer {answered}"
HEALTH_NEVER = "{label}: never fetched for {ticker}; announcements not checked"
HEALTH_NEVER_SUCCEEDED = "{label}: no fetch has succeeded yet for {ticker}; announcements not checked"
HEALTH_UNREADABLE = "{label}: the stored items could not be read this run, which is not the same as none found or never fetched"
HEALTH_UNREADABLE_ROWS = "{count} stored announcement row(s) could not be read (company-announcement source)."
HEALTH_AFTER_FETCH = "An announcement made after the last fetch is not shown."
HEALTH_COMMAND = "To fetch (run by hand; this brief does not run it): {command}"

# --- tags -------------------------------------------------------------------------------------------------
TAG_TRADE = "Insider or major-shareholder trade"
TAG_CAPITAL = "Share issue or capital change"
TAG_DIVIDEND = "Dividend"
TAG_MEETING = "Shareholder meeting"
TAG_RESULTS = "Results"
TAG_PERSONNEL = "Personnel or disclosure officer"
TAG_UNCLASSIFIED = "Other announcement, not classified; the title gives no amount"
TAG_PRESS = "Press item (may concern another company; not classified)"
BASIS_RECORD = " (event record)"
BASIS_KEYWORD = " (title keyword)"
MARK_RELISTED = "; listed again: window still open"
UNCLASSIFIED_NOTE = "The title does not give the amount; the notice does."
TITLE_LABEL = "Title (third-party text): {title}"
ISSUE_FACTS = "From the event record: {kind}; {ratio}{dates}."
ISSUE_RATIO = "{ratio} new shares per 100 held"
ISSUE_RATIO_NONE = "ratio not stated"
ISSUE_DATES = "; ex-date {ex}"
ISSUE_RECORD = "; record date {record}"
ISSUE_KINDS = {
    "BONUS": "bonus shares", "STOCK_DIVIDEND": "stock dividend", "RIGHTS_OFFER": "rights offer",
    "PRIVATE_PLACEMENT": "private placement", "EMPLOYEE": "employee issue", "OTHER": "issue of another kind",
}
ISSUE_PLURALS = {
    "BONUS": "bonus issues", "STOCK_DIVIDEND": "stock dividends", "RIGHTS_OFFER": "rights offers",
    "PRIVATE_PLACEMENT": "private placements", "EMPLOYEE": "employee issues", "OTHER": "issues of another kind",
}

# --- the trade line (no direction word: "sale" and "purchase" come from a closed set) -----------------------
TRADE = "{name} filed a notice of a {noun} of {quantity}{ticker} shares ({inside})."
TRADE_NAMELESS = "A notice of a {noun} of {quantity}{ticker} shares was filed ({inside})."
TRADE_UNREADABLE = "Registered trade record, filed a notice (direction or quantity could not be read from the title)."
TRADE_WINDOW = "window {start} to {end}; status: {status}"
TRADE_WINDOW_MISSING = "window not given in the record"
TRADE_NO_QUANTITY = "quantity not stated in the title"
TRADE_UNDER_WAY = "The record does not say how much has been carried out."
TRADE_ENDED = "The record does not say whether it was carried out."
TRADE_WEEKS = "The window runs {weeks} {unit}; this brief covers one."
RANGE_SENTENCE = (
    "The usual range is built from past prices only. It does not account for this announcement, so the real swing "
    "could be larger."
)

# --- size and benchmark -----------------------------------------------------------------------------------
CHECKLIST = (
    "To size it, read the notice: who filed it, whether it is a sale or a purchase, how many shares in total against "
    "the shares outstanding, how it will be done, and the window."
)
SIZE_SHOWN = (
    "Size: {percent}% of the shares outstanding (the vendor's count is {count}: VCI share count via vnstock, "
    "latest-quarter row {year}-Q{quarter}, fetched {fetched})."
)
SIZE_UNREADABLE = (
    "Size: not calculated, because the title could not be read. Read the notice for who filed it, how many shares in "
    "total against the shares outstanding, how it will be done, and the window."
)
SIZE_IMPLAUSIBLE = (
    "Size: not calculated, because the quantity in the title is larger than the vendor's share count. Read the notice "
    "for the quantity."
)
SIZE_NO_QUANTITY = "Size: not calculated, because the title gives no quantity. {checklist}"
SIZE_CHANGING = "Size: size not shown, because the share count is changing (issue on {date}). {checklist}"
SIZE_DISAGREE = "Size: size not shown, because the vendor's two share counts disagree. {checklist}"
SIZE_UNAVAILABLE = "Size: size not shown, because the vendor's share count could not be read this run. {checklist}"
SIZE_OFF = "Size: size not shown, because sizing is off (--no-sizing). {checklist}"
BENCHMARK = (
    "Earlier registrations of this kind in the source ({count} {nouns} with a stated quantity, {year} onward): "
    "{larger}{others} Each is measured against the share count at its own date, estimated from today's count and "
    "the share issues with a ratio in the source."
)
BENCHMARK_LARGER_NONE = "none was larger"
BENCHMARK_LARGER = "{count} {verb} larger than this one"
BENCHMARK_OTHERS = "; the largest of the others was {percent}% of the shares then."
BENCHMARK_NO_OTHERS = "."
BENCHMARK_NONE = (
    "No comparison shown: only {count} earlier registrations with a stated quantity in the comparable period."
)
NOUN_PLURALS = {"sale": "sales", "purchase": "purchases"}

# --- Scheduled (the one Scheduled line of the brief) ---------------------------------------------------------
SCHEDULED_MEETING = "{kind}, source dates: {dates}"
SCHEDULED_NOT_CHECKED = (
    "Scheduled (company-announcement source): not checked, because its events were not fetched or could not be read this run."
)
MEETING_KINDS = {"AGME": "shareholder meeting event", "EGME": "extraordinary shareholder meeting event"}

# --- the re-read triggers line: labels are lowercase letters, spaces and hyphens, and counts only ----------------
TRIGGER_TRADES_LABEL = "registered sales or purchases by a major shareholder or insider since the last brief"
TRIGGER_ISSUES_LABEL = "share issues or capital changes since the last brief"
TRIGGER_UNCHECKED_LABEL = "holdings whose announcements were not checked"

def own_sentences() -> tuple[str, ...]:
    """Every string constant of this module (and the strings inside its UPPER_CASE dicts)."""
    found: list[str] = []
    for name, value in globals().items():
        if not name.isupper() or name.startswith("_"):
            continue
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, dict):
            found += [v for v in value.values() if isinstance(v, str)]
    return tuple(found)


wording.register_fixed_sentences(*own_sentences())
