## ADDED Requirements

### Requirement: The brief is produced by a hand-run script and calls no language model
The system SHALL provide `backend/scripts/weekly_brief.py`, a thin entry point over the package `backend/app/services/brief/`, that the owner starts by hand after the market close. No route, startup hook, scheduler, debate hook or API call SHALL start it, expose its output or read its inputs. Neither the script nor the package SHALL import or call a language-model client, and the brief SHALL contain no language-model text. The package SHALL NOT reference the company feed (`test_company_feed_isolation.py` stays unchanged and passing). Each section SHALL be a pure function from frozen data to a tuple of lines, and the brief SHALL be assembled from an ordered list of such functions, so that later changes add sections without rewriting existing ones.

#### Scenario: A language-model client is never loaded
- **WHEN** a fresh interpreter imports the brief's run module and the script module
- **THEN** none of `anthropic`, `openai`, `google.generativeai`, `claude_agent_sdk`, `app.services.debate.llm_client`, `app.services.debate.engine`, `.runner`, `.synthesiser` or `.news` is in `sys.modules`

#### Scenario: No route exposes the brief
- **WHEN** the FastAPI app's routes are listed
- **THEN** no path or endpoint module refers to the brief or to holdings

#### Scenario: The package does not mention the feed
- **WHEN** the sources under `backend/app/services/brief/` are searched
- **THEN** none contains the text the feed isolation test forbids outside the feed package

#### Scenario: A later change adds a section
- **WHEN** a section function is added to the ordered list
- **THEN** no existing section function or its test changes

### Requirement: Holdings live in a TOML file outside the repository and are read only when private
The system SHALL read holdings from a TOML file (standard-library `tomllib`) whose default path is `stock-foresight/holdings.toml` under `XDG_CONFIG_HOME` or, if unset, `~/.config`, overridable with `--holdings`. Each `[[holdings]]` entry SHALL have `ticker` (`[A-Z0-9]{1,12}`), `shares` (positive integer) and `cost` (positive number, per share, in the stored price unit), and MAY have `purchase_date` and `shares_as_of` (defaulting to `purchase_date`) and `[[holdings.levels]]` entries each with `comparator` (`below` or `above`), `price` (positive), `entered` (a date) and `text` (one line, at most 300 characters). The script SHALL refuse, with exit code 1, a message that names the problem and never prints a share count or cost, and before any vendor call, when the file is missing, is not a regular file, is owned by another user, has any group or world permission bit set, resolves to a path inside the repository, is larger than 256 KiB, sits in a directory that group or others can write to, fails validation (including an unknown field, more than 200 holdings, more than 50 levels in a holding, more than 10^12 shares, or a level text containing a control, format, separator or unassigned character), lists a ticker twice or lists no holding. The file SHALL be opened once without following a symbolic link at its final component and read from that descriptor after the checks. A parent directory that is group- or world-readable, or a git working tree above it, SHALL give a warning, not a refusal. Holdings SHALL NOT be stored in `app.db` or any database and SHALL NOT pass through any API route.

#### Scenario: A private file is read
- **WHEN** the holdings file has mode 600 (or 400), is owned by the user and lies outside the repository
- **THEN** it is parsed and the run continues

#### Scenario: A readable file is refused
- **WHEN** the holdings file has mode 644, 640 or 604
- **THEN** the script exits 1 with a message that asks for mode 600, and no ticker is refreshed

#### Scenario: A file inside the repository is refused
- **WHEN** `--holdings` points to a path inside the repository root
- **THEN** the script exits 1 before reading it

#### Scenario: A missing file
- **WHEN** the default holdings file does not exist
- **THEN** the script exits 1, names the expected path, and makes no vendor or database call

#### Scenario: Invalid entries
- **WHEN** an entry has `shares = 0`, a level with comparator `near`, a level without `entered`, a future `purchase_date`, a ticker `sab`, or the same ticker twice
- **THEN** the script exits 1 naming the entry and the field, without echoing `shares` or `cost`

#### Scenario: Optional fields
- **WHEN** an entry has no `purchase_date` and no `shares_as_of`
- **THEN** it loads, `shares_as_of` is null and the position header says the purchase date is "not entered"

#### Scenario: The ignore patterns and the new files
- **WHEN** `git check-ignore` is asked about `holdings.toml`, `holdings_issued.jsonl` and `holdings_share_counts.json` at the repository root and under `backend/`
- **THEN** all are ignored (patterns `holdings*.toml`, `holdings*.jsonl`, `holdings*.json`), and no file added by this change under `backend/app/services/brief/`, `backend/scripts/` or `backend/tests/` is ignored

#### Scenario: Unknown field
- **WHEN** an entry or a level has a field the format does not define (for example `share_count`)
- **THEN** the script exits 1 naming the entry and the field name, never its value

#### Scenario: shares_as_of defaults to the purchase date
- **WHEN** an entry has `purchase_date` and no `shares_as_of`
- **THEN** `shares_as_of` equals the purchase date

#### Scenario: A directory others can write to
- **WHEN** the holdings file sits in a directory with a group or world write bit
- **THEN** the script exits 1 asking for chmod 700, before any vendor call

#### Scenario: Hostile or oversized input
- **WHEN** the file is larger than 256 KiB, deeply nested, or not UTF-8
- **THEN** the script exits 1 with a plain message and no traceback

### Requirement: Every held ticker is refreshed before computing, and a failed refresh degrades
The script SHALL call `load_ticker` once per held ticker before computing any range, unless `--no-refresh` is given, spacing calls at the rate `bulk_ingestion` uses. A `SystemExit` for which `_is_rate_limit_exit` is true SHALL be caught, the ticker marked failed and the remaining tickers marked not attempted; any other `SystemExit` SHALL propagate; any other `Exception` SHALL mark the ticker failed. A returned status other than `ok` SHALL mark the ticker failed. Text the refresh prints to stdout (the vendor library's notices) SHALL go to stderr, never into the brief. A failed or skipped refresh SHALL NOT stop the run: the holding SHALL be computed from stored prices and shown as "refresh failed; last bar <date>" (or "no stored prices" when there is no bar) with a per-holding stale warning. A holding SHALL be called stale when its last bar is earlier than the newest last bar among the holdings or more than 5 calendar days before the run date, and the warning SHALL say "calendar days".

#### Scenario: The vendor limiter ends one call
- **WHEN** the loader for the second of three tickers raises `SystemExit` with a rate-limit message
- **THEN** the first ticker is refreshed, the second is failed, the third is not attempted, all three appear in the brief, and the run completes with exit code 0

#### Scenario: A genuine exit is honoured
- **WHEN** the loader raises `SystemExit("interpreter is going down")`
- **THEN** the exception propagates and the brief is not produced

#### Scenario: A refresh error on one ticker
- **WHEN** the loader raises `RuntimeError` for one ticker
- **THEN** that holding reads "refresh failed; last bar <date>" and carries a stale warning, and the others are unaffected

#### Scenario: Not refreshed on request
- **WHEN** `--no-refresh` is given
- **THEN** the loader is never called and the header says prices were not refreshed this run

#### Scenario: Run before the close
- **WHEN** a holding's last bar is today's date (ICT, UTC+7) and the time is before 15:15 ICT
- **THEN** that bar is provisional and the requirement "The top of the brief warns of a provisional bar and counts re-read triggers" applies; the run is not refused

### Requirement: Dates are anchored on the last bar, never on a calendar week (Rule 1)
The brief SHALL state the horizon as "the 5 sessions after <last bar date>" and SHALL NOT name weekdays as the covered period. THE WEEK JUST ENDED SHALL be the last 5 stored sessions, printed as the first and last of those bar dates, and the previous range SHALL be the one issued for the bar 5 sessions before the last (`dates[-6]`). The header SHALL show the newest last bar and, when holdings differ, each differing holding's own last bar.

#### Scenario: Header and horizon
- **WHEN** the newest last bar is 2026-10-09
- **THEN** the title line names 2026-10-09 and says it covers the 5 sessions after that date, with no Monday-to-Friday wording

#### Scenario: Holdings with different last bars
- **WHEN** one holding's last bar is two sessions older than another's
- **THEN** the header does not claim a single last bar for every holding and the older holding carries its own stale warning

### Requirement: The position block states price-only gain or loss, as entered
For each holding with a stored close the brief SHALL show the close and its date, the value (`shares × close`, in millions of VND), and the gain or loss on price against the investor's cost, in millions of VND and as a simple percentage (`close / cost − 1`), plus one fixed line that shares and cost are shown as entered, with the `shares_as_of` date when present, and are not adjusted for share issues or dividends in this version. The header line SHALL show shares, cost and the purchase date (or "not entered"). Prices SHALL be shown in the stored unit with one fixed line stating they are per share in thousand VND. No raw log return SHALL be shown (Rule 2).

#### Scenario: Provisional close
- **WHEN** the holding's last bar is provisional
- **THEN** the close reads "Close <close> (<date>, provisional)", in the redacted copy too

#### Scenario: Gain on price
- **WHEN** a hypothetical holding has 1,000 shares, cost 41.80 and a last close of 42.90
- **THEN** the block shows value 42.90M VND and gain +1.10M VND (+2.6%)

#### Scenario: Loss on price
- **WHEN** the close is below cost
- **THEN** the amount and the percentage carry a minus sign

#### Scenario: No log return is shown
- **WHEN** any brief is rendered
- **THEN** every percentage on a price move is `close ratio − 1` or the band's half-width, and no figure is labelled as a log return

### Requirement: The next-5-sessions range is shown in VND with a derived coverage sentence (Rules 1, 4)
For a holding whose range status is `ok`, the brief SHALL show, labelled "Usual range (typical 5-session move)", the low and high per share as `close × exp(∓range_5s_pct / 100)`, the band as "±<range_5s_pct>%", and the amount on the investor's shares (`shares × close × range_5s_pct / 100`, in millions of VND), followed by a coverage sentence built from `coverage_phrase(range_coverage)`: for the 0.68 level, "About 2 weeks in 3 stay inside a range like this; about 1 in 3 is bigger, up or down."; for any other level, "<phrase> of weeks stay inside a range like this; the rest are bigger, up or down." The sentence SHALL NOT be typed independently of `coverage_phrase`. `sigma_daily_pct` SHALL NOT be shown. Nothing SHALL be called Confidence.

#### Scenario: Calibrated ticker
- **WHEN** the range is `ok` with `range_5s_pct` 2.7, `range_coverage` 0.68 and close 42.90
- **THEN** the low is 42.90 × exp(−0.027) and the high 42.90 × exp(0.027), each to two decimals, the band reads ±2.7%, and the 2-weeks-in-3 sentence follows

#### Scenario: Another coverage level
- **WHEN** the model's `range_coverage` is 0.80
- **THEN** the sentence reads "About 80% of weeks stay inside a range like this; the rest are bigger, up or down." (the run is stopped by the disclaimer guard before it is printed; the function is tested directly)

### Requirement: Every non-ok range status has plain wording and no holding vanishes
For each holding the brief SHALL print a block, a log entry SHALL be written, and HOLDINGS LISTED SHALL count it, whatever its status. The brief SHALL print: for `ineligible`, "No range this week:" followed by one plain clause for each reason among `delisted`, `insufficient_history`, `stale`, `near_gap` and `hard_quality_flag` (an unknown code prints as an unrecognised reason with the code); for `model_unavailable`, that the volatility model file is missing or unusable; for `range_out_of_bounds`, that recent prices look abnormal and the range is withheld, with no sigma figure; for `uncalibrated`, the band and VND range with, in place of the coverage sentence, that how often such a range holds has not been measured for the ticker; for a ticker with no stored bars or `TickerNotLoaded`, that there are no stored prices; for any other exception while gathering, the exception class name and that the error is logged. Close and position SHALL still be shown whenever a stored close exists.

#### Scenario: Each ineligible reason
- **WHEN** a holding is `ineligible` with reasons `["stale", "near_gap"]`
- **THEN** the block says no range this week and gives one plain clause for each reason, and shows the stored close

#### Scenario: Model file missing
- **WHEN** the model artifact is unavailable
- **THEN** every holding reads "No range this week" with the model-file wording and the brief is otherwise complete

#### Scenario: Out of bounds
- **WHEN** the status is `range_out_of_bounds`
- **THEN** no band, no VND range and no sigma figure is printed

#### Scenario: Uncalibrated
- **WHEN** the status is `uncalibrated`
- **THEN** the band and VND range are shown and the 2-weeks-in-3 sentence is not, replaced by the not-measured sentence

#### Scenario: Unexpected error for one holding
- **WHEN** gathering facts for one holding raises an unexpected exception
- **THEN** that holding's block says it could not be computed, the other holdings are rendered normally, and the log has an entry with status `error`

### Requirement: THE WEEK JUST ENDED compares the close with the range that was actually issued
For each holding with at least 6 stored closes the brief SHALL print the move over the last 5 stored sessions as a simple percentage with the two closes, and the previous range found in the issued-brief log with exact match on `as_of == dates[-6]`. Only log entries issued for a bar strictly before the last bar SHALL be read, so a re-run on the same bar says what the first run said; among entries for `dates[-6]` the one with a band is preferred, then a post-close one, then the later line. It SHALL say the close was inside the range when `|ln(close[-1] / close[-6])| × 100 <= band_pct` and outside otherwise, computed on stored closes. The sentences SHALL be: "first brief: no previous range" when the log has no entry for the ticker; "no range was issued for the week starting after <date>; the latest one on file is for <date>" when entries exist but none matches; "last week's brief gave no range" with the plain status wording when the matched entry has no band; and "Last week's range was ±<b>% (<lo> to <hi>): the close was inside it" or "outside it" otherwise. One fixed sentence SHALL state that the comparison uses stored prices, which may be adjusted for dividends and share issues, and that this version does not say whether one fell in the week. The brief SHALL NOT recompute a past range.

#### Scenario: First brief
- **WHEN** the log file does not exist
- **THEN** each holding's week block reads "first brief: no previous range" and no recomputed range appears

#### Scenario: Inside
- **WHEN** the matched entry has `band_pct` 2.7 and the week's `|ln(close ratio)|` is 1.1%
- **THEN** the close is reported inside the range, with the issued low and high

#### Scenario: Outside
- **WHEN** the week's `|ln(close ratio)|` is 3.4% and the matched band is 2.7
- **THEN** the close is reported outside the range

#### Scenario: A week was skipped
- **WHEN** the log has an entry for the ticker dated two weeks back and none for `dates[-6]`
- **THEN** the brief says no range was issued for the week starting after that date and names the latest entry

#### Scenario: Same-day re-run
- **WHEN** two entries share `as_of == dates[-6]`
- **THEN** the later one is used

#### Scenario: Range issued from a provisional bar
- **WHEN** the only matching entry is marked provisional
- **THEN** the sentence appends "(that range was issued from a provisional bar)"

#### Scenario: Re-run on the same bar
- **WHEN** a brief is produced, then produced again on the same last bar (for example redacted with `--no-refresh`)
- **THEN** the first-brief or previous-range wording and the re-adjusted-close note are the same in both runs, because the first run's own entries are not read

#### Scenario: A degraded re-run
- **WHEN** a later entry for the same bar has no band and an earlier one has
- **THEN** the entry with the band is the one used

#### Scenario: Corrupt line
- **WHEN** the log contains a line that is not valid JSON
- **THEN** it is skipped with a count on stderr and the brief is still produced

### Requirement: The issued-brief log records what was issued, privately
Each run SHALL, after the brief has been written to stdout or to `--out` (and not otherwise), append one JSON line per holding to `holdings_issued.jsonl` in the same directory as the holdings file, created with mode 600, written in one `write` and flushed to disk, containing `schema`, `issued_at` (UTC), `ticker`, `as_of` (last bar date), `close` (as printed), `status`, `provisional`, `band_pct`, `band_lo` and `band_hi` (thousand VND; null when no range), `calibrated`, `model_version` (null without a model) and `refreshed`. It SHALL NOT contain shares, cost, purchase date, or any level (price, text, reached state or distance). It SHALL NOT be under `reports/` or in the repository, including through a symbolic link, and SHALL be opened without following a symbolic link, as a regular file owned by the current user, and made mode 600. A reader SHALL split the file on newline bytes only, decode each line independently, ignore unknown keys, skip a line that is not valid or whose text fields do not match their expected shape, and count it. An append SHALL start a new line if the file does not end with one. If the append fails after the brief was shown, the script SHALL report it on stderr and exit 1. A holding with the same ticker and bar and a provisional flag keeps its own entry, and a re-run without a band does not replace an earlier entry with one.

#### Scenario: One entry per holding per run
- **WHEN** a run with three holdings completes
- **THEN** three lines are appended, one per ticker, each valid JSON with the keys above

#### Scenario: Private file
- **WHEN** the log is created by a run, or already exists with a looser mode
- **THEN** its mode is 600

#### Scenario: Holdings and levels are not logged
- **WHEN** a log line is parsed
- **THEN** it has no key and no value equal to the holding's shares, cost or purchase date, and no level price, text or state

#### Scenario: Nothing is logged when rendering fails
- **WHEN** the disclaimer guard or the final text scan aborts the run
- **THEN** no line is appended

#### Scenario: Nothing is logged for a brief that was not shown
- **WHEN** writing to stdout fails (for example a closed pipe) or the run is interrupted, or `--out` cannot be written
- **THEN** no line is appended and the script exits 1 (or is interrupted)

#### Scenario: Odd bytes in the log
- **WHEN** the log holds a line with an invalid UTF-8 byte, a U+2028 or U+0085 character inside a value, or a torn last line
- **THEN** only that line is skipped and counted, and the next append starts on a new line

### Requirement: YOUR LEVELS reports the investor's own levels verbatim and neutrally (Rules 5, 6)
Under a heading stating that the investor wrote these and that the brief only checks them against the close, each level SHALL be printed with the investor's text verbatim, "you wrote this on <entered>", and the tool's words limited to reached or not reached and the distance. `below` is reached when `close < price`, `above` when `close > price`; equal is not reached. The line SHALL be "<text> (you wrote this on <entered>): REACHED. The last close, <close>, is <below|above> it, by <d>%." or "<text> (you wrote this on <entered>): not reached; the level <price> is <d>% <below|above> the close.", where `d = |close − price| / close × 100` to one decimal. The block SHALL end with "This brief does not place orders; what you do is your decision." A holding with no levels SHALL read "none set", and a holding with levels but no stored close SHALL list each text with "not checked: no stored close". The tool SHALL add no instruction, no direction claim and no threshold of its own (Rule 3). The text SHALL be printed on one line with control characters replaced.

#### Scenario: Level reached
- **WHEN** a `below` level of 41.60 is checked against a close of 41.20
- **THEN** the line carries the investor's text, the entry date, "REACHED", the close and a distance of 1.0%

#### Scenario: Level not reached
- **WHEN** a `below` level of 41.60 is checked against a close of 42.90
- **THEN** the line says not reached and that the level 41.60 is 3.0% below the close

#### Scenario: Equal is not reached
- **WHEN** the close equals the level price
- **THEN** the level is reported not reached with a distance of 0.0%

#### Scenario: The investor's words may contain a transaction verb
- **WHEN** a level's text is "Trim 300 shares if the close is below 41.60"
- **THEN** it is printed verbatim, labelled as the investor's own with its entry date

### Requirement: A re-adjusted stored close is flagged against the close that was issued
When the most recent earlier log entry for a ticker (issued for a bar strictly before the last bar, or a provisional entry for the last bar itself) has an `as_of` date still in the stored closes and the stored close for that date differs from the logged `close` by more than 0.005, the brief SHALL print a note naming the date, the stored close and the issued close, saying stored prices may have been re-adjusted, and, for a holding with levels in an unredacted brief, that levels set looking at the earlier price may be on the old price basis. The note SHALL state that it sees only adjustments that have reached the stored prices. When the two agree, or there is no earlier entry, no note SHALL be printed.

#### Scenario: Close revised
- **WHEN** the log holds a close of 46.60 for 2026-07-23 and the stored close for that date is now 43.60
- **THEN** the note is printed with both figures and the old-price-basis sentence for a holding with levels

#### Scenario: No change
- **WHEN** the stored close equals the logged close
- **THEN** no note is printed

#### Scenario: No earlier entry
- **WHEN** the log is empty
- **THEN** no note is printed

### Requirement: The top of the brief warns of a provisional bar and counts re-read triggers
The first lines of the brief SHALL be, in order: the title line; when any holding's last bar is provisional (its date is today in ICT, UTC+7, and the time is before 15:15 ICT), a warning line stating that today's bar is provisional, that the closes, ranges and week moves can change after the close, and that the brief should be run again after the close; the line "Re-read triggers this run: <label>: <n>." (further counts, added by later changes, are appended as "; <label>: <n>"); then the refresh and last-bar line. A provisional run SHALL NOT be refused: it SHALL produce the brief, append log entries marked provisional and exit 0. The triggers line SHALL be printed even when every count is 0, SHALL count only the investor's own levels reached in this version (levels checked against a stored close and reached, across all holdings), SHALL contain no judgement word, no direction word and no instruction, and SHALL be absent from the redacted copy. When levels could not be checked for lack of a stored close, the line SHALL append the number of those levels with the reason. The ordered list of trigger counters SHALL be extendable by a later change without editing the line's format. A trigger label SHALL contain only lowercase letters, spaces and hyphens, and a note only a fixed set of shapes.

#### Scenario: Provisional run
- **WHEN** the run happens at 11:00 ICT on a date that is the last bar's date
- **THEN** the second line of the brief is the provisional warning, the position line marks the close "provisional", the log entries have `provisional: true`, and the exit code is 0

#### Scenario: Run after the close
- **WHEN** the run happens at 16:00 ICT on the last bar's date
- **THEN** no provisional warning and no provisional mark appear

#### Scenario: Triggers line with no level reached
- **WHEN** no level is reached, or no holding has levels
- **THEN** the line reads "Re-read triggers this run: your levels reached: 0."

#### Scenario: Triggers line counts levels across holdings
- **WHEN** two holdings have one reached level each and a third has an unreached level
- **THEN** the line reads "Re-read triggers this run: your levels reached: 2."

#### Scenario: Levels that could not be checked
- **WHEN** one level could not be checked because its holding has no stored close
- **THEN** the line states that count with the reason, and the level's own line in YOUR LEVELS says it was not checked

#### Scenario: No judgement words
- **WHEN** the triggers line is rendered for any count
- **THEN** it matches the fixed format and contains none of these whole words, matched case-insensitively and never as substrings: attention, important, urgent, alert, critical, should, must, review, action, act, risk, opportunity, recommend, consider

#### Scenario: The word guard matches whole words
- **WHEN** the guard is applied to the strings "exact", "contact" and "Re-read triggers this run"
- **THEN** none is rejected, and "act", "Review" and "please consider" are rejected

#### Scenario: A later change adds a count
- **WHEN** a further trigger count is appended to the ordered list
- **THEN** the line gains "; <label>: <n>" and no existing test of the format changes

### Requirement: HOLDINGS LISTED appears only with two or more holdings
With two or more holdings in the file the brief SHALL print each holding's ticker and its weight (value over the total value of holdings that have a close, to the whole percent) and the sentence "If every holding moved to the edge of its own range in the same direction, the listed holdings would move about <y>% (an upper bound for the usual ranges, not a forecast; larger moves are possible)", where `y = Σ weight × band_pct` over holdings with a band, to one decimal, and, when any listed holding has no band, or a band whose hit-rate was not measured (uncalibrated), how many are left out of the figure and why. A holding block that cannot be built SHALL print a visible line naming the error class, and the other holdings and the log are unaffected. With one holding the block SHALL NOT appear.

#### Scenario: Two holdings
- **WHEN** two hypothetical holdings have weights 60% and 40% and bands 2.0 and 4.0
- **THEN** the block lists both with their weights and the figure is 2.8%

#### Scenario: A holding without a range
- **WHEN** one of three holdings has status `ineligible`
- **THEN** it is listed and the block says one holding is left out of the figure

#### Scenario: One holding
- **WHEN** the file holds a single holding
- **THEN** no HOLDINGS LISTED block is printed

### Requirement: Fixed sentences, footer and the brief disclaimer are guarded
Every brief SHALL contain "This brief does not update during the week. It does not predict direction.", the re-read triggers line (unredacted copy only; see its own requirement), a footer that mentions only the investor's own levels ("One of your levels appearing or being reached would make a re-read worthwhile. Re-run this brief to refresh."), and the brief disclaimer from `docs/DISCLAIMER.md`, section "Brief version", verbatim. The brief SHALL NOT contain announcement wording, the optional biggest-weekly-move line, a DIVIDENDS or COMPANY block, a net line, or the full or inline disclaimer. A test SHALL compare the code's copy with the blockquote under "## Brief version" after whitespace normalisation, and SHALL require `coverage_phrase` of the served model's `range_coverage` to be "about 2 in 3" while the copy says "About 2 weeks in 3". At run time, if the loaded model's coverage does not round to 0.68, the script SHALL exit 1 before any vendor call and print no brief, and the brief builder SHALL itself refuse any facts that carry another coverage. Before a brief is shown, every line the tool wrote (the investor's own words removed) SHALL pass one final scan, after NFKC normalisation and removal of format characters, for buy, sell, hold, confidence and market sentiment, and the triggers line for the banned judgement words and their stem forms; a failure SHALL stop the run with the line number only.

#### Scenario: The copy equals the source
- **WHEN** the code's disclaimer and the "Brief version" blockquote are whitespace-normalised
- **THEN** they are equal

#### Scenario: The source changes
- **WHEN** `docs/DISCLAIMER.md`'s brief text is edited and the code is not
- **THEN** the guard test fails

#### Scenario: A retrain at another coverage
- **WHEN** the model's `range_coverage` is 0.80
- **THEN** the script exits 1 with a message naming the mismatch, makes no vendor call and prints no brief

#### Scenario: No announcement or dividend section in this version
- **WHEN** any brief is rendered
- **THEN** it contains no "announcement" or "insider" wording, no DIVIDENDS or COMPANY heading and no net line

### Requirement: The brief's own text never carries a buy, sell or hold word (Rule 6)
A guard test SHALL render the brief in full and redacted forms across every status in this spec, with and without levels, with reached and not-reached levels, with a provisional run, with the triggers line at 0 and above 0, and SHALL fail if `\b(buy|sell|hold)\b` (case-insensitive) matches anywhere after every investor-written string has been removed, and SHALL apply the same pattern to the fixed-sentence constants. The investor's own level texts in that test SHALL contain those words so that the removal step is exercised, and a check inside the test SHALL show that the match occurs when the removal is skipped. The existing `TRANSACTION_VERBS` test over the debate export SHALL remain unchanged.

#### Scenario: Tool text is clean
- **WHEN** the full and redacted briefs are rendered for the matrix and the investor's strings are removed
- **THEN** no transaction verb remains

#### Scenario: The guard is live
- **WHEN** the removal of investor strings is skipped on a brief whose level text contains "sell"
- **THEN** the pattern matches

### Requirement: --redact removes everything derived from holdings and keeps tickers (Rule 5)
With `--redact` the brief SHALL contain only market-derived content: tickers, closes, last-bar dates, the week move and its two closes, the range in percent and VND per share, status wording, refresh and staleness notes, the re-adjusted-close note without its levels sentence, the provisional warning and the provisional mark, the fixed sentences and the disclaimer. It SHALL NOT contain anything read from the issued log other than the re-adjusted-close note (no first-brief sentence, no previous range, no verdict, no comparison sentence), the re-read triggers line, shares, `shares_as_of`, cost, purchase date, value, gain or loss in VND or percent, the amount on the shares, weights, the upper-bound figure, any level price, text, entry date, reached state or distance, or the as-entered note. It SHALL carry one fixed line saying so, and YOUR LEVELS SHALL be one fixed line "not shown in the redacted copy" printed whether or not levels exist. The section that renders market facts SHALL take no holdings data as input.

#### Scenario: No holdings-derived number survives
- **WHEN** the redacted brief is rendered for hypothetical holdings with distinctive shares, cost, purchase date, level prices and level texts
- **THEN** every number token in the output is in an allow-list built from the market facts and the fixed sentences, and none of the holdings values appears in any common format

#### Scenario: Gain percent would reveal cost
- **WHEN** the redacted brief is rendered
- **THEN** it contains no gain or loss percentage and no distance from a level

#### Scenario: No log-derived week text
- **WHEN** the redacted brief is rendered after any number of earlier runs
- **THEN** it shows the week move but none of the first-brief, previous-range, no-range-issued or comparison sentences, because they would show how long a ticker has been in the investor's briefs; the tickers themselves are still shown (accepted)

#### Scenario: Triggers line dropped
- **WHEN** the redacted brief is rendered for holdings with reached levels
- **THEN** it contains no "Re-read triggers" line and no count of levels

#### Scenario: Levels line is constant
- **WHEN** one holding has levels and another has none
- **THEN** both show the same "not shown in the redacted copy" line

#### Scenario: The market section cannot see holdings
- **WHEN** the source of every market-sections module (matched by glob) is searched for `shares`, `cost`, `purchase`, `Holding` and `Level`
- **THEN** none is found, and each of its functions reads only fields of the market facts

### Requirement: Output location and file modes
The brief SHALL be printed to stdout by default. With `--out PATH` the script SHALL write the file with mode 600, never through a symbolic link, completing partial writes, and SHALL refuse any path inside the repository (redacted or not; `reports/` is for uploads), and the holdings file or the issued log (including by hard link). The script SHALL NOT write the brief to `reports/` by default or under any condition. When stdout is a regular file that others can read, or that lies inside the repository, a warning SHALL go to stderr.

#### Scenario: Refused under reports
- **WHEN** `--out` points into the repository's `reports/` directory, redacted or not
- **THEN** the script exits 1 and writes nothing

#### Scenario: Any brief inside the repository
- **WHEN** `--out` points elsewhere inside the repository, with or without `--redact`
- **THEN** the script exits 1

#### Scenario: The holdings file or the log as the target
- **WHEN** `--out` is the holdings file or the issued log, or a link to either
- **THEN** the script exits 1 and the file is untouched

#### Scenario: Redacted file elsewhere
- **WHEN** `--redact --out` names a path outside the repository
- **THEN** the file is created with mode 600

### Requirement: Tests never touch the real database, the vendor or the owner's files
The brief's tests SHALL run against injected paths and temporary databases, SHALL replace the loader so no vendor call is possible, and SHALL include a fixture that points `app.db.connection.DB_PATH` at a temporary file and fails the test if `load_ticker` is called unexpectedly. No test SHALL read the owner's real holdings file or issued-brief log, and all holdings in tests SHALL be hypothetical.

#### Scenario: A forgotten injection
- **WHEN** a test runs a brief without injecting a loader and `load_ticker` is called
- **THEN** the test fails instead of reaching the vendor

#### Scenario: The real database
- **WHEN** the brief tests run
- **THEN** every connection opened through `get_connection` is to the temporary file
