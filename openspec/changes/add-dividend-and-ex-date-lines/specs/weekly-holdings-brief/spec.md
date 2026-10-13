## ADDED Requirements

<!-- Sync order: `add-weekly-holdings-brief` (N1) first, then this change. If this change is synced while
     `openspec/specs/weekly-holdings-brief/` does not exist, this file creates the capability holding
     only these requirements, and N1's requirements are added to it afterwards. The names below are
     chosen not to collide with N1's. Examples use hypothetical holdings only. -->

### Requirement: The brief reads the company feed through one adapter and never starts a snapshot
Exactly one brief file, `backend/app/services/brief/feed_source.py`, SHALL reference the company feed. It SHALL read events through the existing read-only `latest_items` and `last_fetch` and SHALL import nothing from the company feed package except its store module. It SHALL provide the text of the snapshot command (so that no other brief file contains the package name). The brief SHALL NOT run, import, schedule or shell out to the snapshot; it MAY print the snapshot command for the owner to run by hand.

#### Scenario: The command is printed, not run
- **WHEN** the feed has never been fetched for a held ticker `ABC`
- **THEN** the brief prints `python backend/scripts/snapshot_company_feed.py --tickers ABC` as text for the owner to run by hand, and no process is started and no network call is made

#### Scenario: Only the adapter names the feed
- **WHEN** the files of `backend/app/services/brief/` and `backend/scripts/weekly_brief.py` are scanned
- **THEN** only `feed_source.py` contains `company_feed`, and no brief file contains `subprocess`, `os.system` or an import of the snapshot

### Requirement: Feed events are typed and unreadable rows are counted
The adapter SHALL return each stored event as a typed value with `event_code`, `exright_date`, `record_date`, `payout_date`, `value_per_share` (VND), `exercise_ratio`, `published_at` and, for event code `ISS` only, an `issue_class` (see the issue-class requirement), with dates parsed from the first ten characters of the stored text. A stored row whose event code is missing or whose date text does not parse SHALL be counted, not guessed, and the brief SHALL say how many feed rows could not be read when the count is above zero. The event SHALL carry no stored title or other free text; the issue class is the only value derived from a title and the title itself SHALL NOT leave the adapter.

#### Scenario: Mixed date forms
- **WHEN** a stored event has `exright_date` `2026-07-28`, `payout_date` `2026-08-28T00:00:00` and `published_at` `2026-05-08T00:00:00`
- **THEN** the event holds the dates 2026-07-28, 2026-08-28 and 2026-05-08

#### Scenario: A row that cannot be read
- **WHEN** a stored event has `exright_date` `soon`
- **THEN** its ex-date is none, the unreadable count is 1 and the brief says one feed row could not be read

### Requirement: The dividend list shows cash dividends since the purchase date, per share, never added up
For a holding with a purchase date, the DIVIDENDS block SHALL list each cash dividend (event code `DIV`, a non-null ex-date, a positive `value_per_share`) whose ex-date is after the purchase date and on or before the last bar date, ascending by ex-date, as VND per share with its ex-date, and SHALL state "source covers from <date>", where the date is the oldest published date among all stored events of the ticker. A dividend whose ex-date equals the purchase date SHALL NOT be listed. Two events with the same ex-date and amount SHALL be listed once. The list SHALL NOT be summed, multiplied by a share count or turned into a yield, and the block SHALL carry no total. A holding without a purchase date SHALL get a sentence saying the list is not shown because no purchase date is entered.

#### Scenario: A list since a hypothetical purchase
- **WHEN** a hypothetical holding of `SAB` has purchase date 2025-06-10 and the last bar is 2026-10-09, with the stored SAB dividends
- **THEN** the block lists 3,000 VND (ex 2025-06-30), 2,000 VND (ex 2026-01-12) and 3,000 VND (ex 2026-07-28), states that the source covers from 2017-05-15, and shows no total

#### Scenario: Purchase on the ex-date
- **WHEN** the purchase date is 2026-07-28 and a stored dividend has ex-date 2026-07-28
- **THEN** that dividend is not listed

#### Scenario: Ex-date after the last bar
- **WHEN** a stored dividend has an ex-date after the last bar
- **THEN** it is not in the list and appears on the Scheduled line

#### Scenario: No purchase date
- **WHEN** a holding has no purchase date
- **THEN** the block says cash dividends since purchase are not listed because no purchase date is entered, and the ex-date window lines and level notes are still produced

### Requirement: The dividend list states whether it is complete
A holding's dividend list SHALL be complete if and only if its purchase date is on or after the oldest stored event published date plus `MAX_LAG_DAYS`, a named module constant (120 days at the time of writing) whose comment states the observed announcement-to-ex-date lags (44 cash dividends in 9 tickers: maximum 85 days, SAB, the next 81, also SAB; every other ticker 21 days or fewer) and that the value is a margin over an observed maximum, not a proven bound. When the list is not complete, the block SHALL say it may be incomplete for ex-dates before that horizon date, print the horizon date, the oldest stored date and the lag it assumes, and SHALL NOT call the list wrong. When the feed holds no events for the ticker, the list SHALL NOT be presented as complete. The completeness rule SHALL NOT assume that a fetch returning fewer than 50 events holds the full history.

#### Scenario: Purchase after the horizon
- **WHEN** the oldest stored event is dated 2017-05-15 and the purchase date is 2025-06-10
- **THEN** the list is complete and carries no incomplete sentence

#### Scenario: Purchase on the horizon date
- **WHEN** the oldest stored event is dated 2022-07-19 and the purchase date is 2022-11-16 (120 days later)
- **THEN** the list is complete; for a purchase date of 2022-11-15 it is not, and the block says it may be incomplete for ex-dates before 2022-11-16

#### Scenario: Oldest event is taken across all codes
- **WHEN** the oldest stored event of a ticker is an insider-trade event dated 2022-07-19 and its oldest dividend is dated 2023-10-20
- **THEN** the covered-from date and the horizon use 2022-07-19

#### Scenario: Nothing stored
- **WHEN** the feed holds no event for the ticker
- **THEN** no list is shown as complete

### Requirement: An issue class is derived inside the adapter from the title, and only the class leaves it
For each stored event with event code `ISS` the adapter SHALL derive an `issue_class` from keywords in the stored title (Unicode NFC, casefolded; first match in this order): `STOCK_DIVIDEND` ("Trả Cổ tức bằng Cổ phiếu"), `BONUS` ("Cổ phiếu thưởng"), `RIGHTS_OFFER` ("Quyền mua"), `PRIVATE_PLACEMENT` ("riêng lẻ"), `EMPLOYEE` ("CBCNV"), and `OTHER` when none matches or the title is missing. Only the enumeration value SHALL reach the rest of the brief; no title SHALL be displayed, logged or carried. The enumeration names SHALL be exactly these six, because later changes reuse them.

#### Scenario: Each stored wording maps to one class
- **WHEN** the adapter reads ISS events whose titles are "Cổ phiếu thưởng tỉ lệ 15.0%", "Trả Cổ tức bằng Cổ phiếu tỉ lệ 26.0%", "Quyền mua CP cho Cổ đông hiện hữu tỉ lệ 20.0%", "Phát hành riêng lẻ tỉ lệ 32.6%", "Phát hành cho CBCNV tỉ lệ 0.5%" and "Điều chỉnh khác"
- **THEN** their classes are BONUS, STOCK_DIVIDEND, RIGHTS_OFFER, PRIVATE_PLACEMENT, EMPLOYEE and OTHER

#### Scenario: A title that matches two keywords
- **WHEN** a title contains both "riêng lẻ" and "CBCNV"
- **THEN** the class is the first match in the stated order, and the keyword-accuracy check over the stored rows reports any such title

#### Scenario: No title
- **WHEN** an ISS event has no title
- **THEN** its class is OTHER

#### Scenario: The title does not leave the adapter
- **WHEN** an event is built from an ISS row
- **THEN** no attribute of the event holds the title text

### Requirement: Count-changing share issues are identified by one pure rule
The brief SHALL provide one pure helper that selects the share issues that change an investor's share count: `issue_class` BONUS or STOCK_DIVIDEND, a non-null ex-date and an `exercise_ratio` greater than zero. It SHALL return the issues in ascending ex-date order, de-duplicated on ex-date and ratio, and, for a date range, their cumulative factor as the product of one plus each ratio. RIGHTS_OFFER, PRIVATE_PLACEMENT, EMPLOYEE and OTHER events, and BONUS or STOCK_DIVIDEND events with no ex-date, SHALL NOT be returned and SHALL NOT enter the factor. Its documentation SHALL state that the factor is calculated and that any display of it SHALL carry "calculated, check with your broker". Later changes (N3 and N2b) SHALL use this helper and SHALL NOT restate the rule.

#### Scenario: The stored issues are separated by class
- **WHEN** the helper is run over fixtures built from the stored rows: SAB bonus 100% ex 2023-09-14, VPB stock dividend 26.04% ex 2026-09-24, FPT bonus 15% ex 2025-07-21, an FPT employee issue with an ex-date, KBC's private placement ex 2025-06-24 (ratio 0.3257), SSI's rights offer ex 2025-12-08 (ratio 0.2), VCB's bonus with no ex-date and VPB's placement with no ex-date
- **THEN** it returns exactly the SAB, VPB and FPT bonus or stock-dividend issues

#### Scenario: A cumulative factor
- **WHEN** the helper is asked for the issues of VPB after 2022-01-01 up to 2026-10-09 over fixtures of its 50% bonus ex 2022-09-28 and its 26.04% stock dividend ex 2026-09-24
- **THEN** it returns both and a factor of 1.5 × 1.2604104, and nothing in the brief displays that factor

#### Scenario: A repeated issue
- **WHEN** two events have the same ex-date and ratio
- **THEN** the helper returns one issue

### Requirement: Share issues since the purchase date are listed separately and change no figure
The DIVIDENDS block SHALL list, apart from the dividends, the count-changing share issues whose ex-date is after the purchase date and on or before the last bar date, with the ex-date and the ratio as "new shares per 100 held", labelled as from the source and not checked against the broker, followed by "They change your share count." or "none". A RIGHTS_OFFER whose ex-date is after the purchase date and on or before the last bar SHALL be listed on its own line as a rights offer to shareholders, "read the notice; not calculated and not applied to your share count". BONUS or STOCK_DIVIDEND events with no ex-date SHALL NOT be listed here; they appear on the Scheduled line. PRIVATE_PLACEMENT, EMPLOYEE and OTHER events SHALL NOT be listed as share issues for the investor. No share count, cost per share, multiplier, entitlement or amount SHALL be computed from any issue in this change.

#### Scenario: A stock dividend since purchase
- **WHEN** a hypothetical holding of `VPB` was bought on 2026-09-01 and the last bar is 2026-10-09
- **THEN** the block lists "ex 2026-09-24, 26.04 new shares per 100 held", says the ratio is from the source and not checked against the broker, and shows no new share count

#### Scenario: Placements and employee issues
- **WHEN** the only issues since purchase are a private placement with an ex-date (KBC-style, ratio 0.3257) and an employee issue with an ex-date
- **THEN** the issues line reads "none" and neither is listed

#### Scenario: A rights offer
- **WHEN** a rights offer has ex-date 2025-12-08 and the purchase date is 2025-11-01
- **THEN** the block lists it as a rights offer to shareholders, read the notice, not calculated and not applied, and no ratio-based count appears

### Requirement: Announced issues without an ex-date and rights offers appear on the Scheduled line
The Scheduled line SHALL list, in addition to dated cash dividends and count-changing issues after the last bar, rights offers with an ex-date after the last bar ("read the notice; not calculated"), and BONUS or STOCK_DIVIDEND events with no ex-date as "announced <date>, no ex-date yet" with the ratio if stored, "not applied until an ex-date is set", only when their announcement date is within `PENDING_ANNOUNCEMENT_DAYS` (365) days of the last bar. Such a row SHALL NOT enter the count-changing helper or its factor.

#### Scenario: A bonus announced without an ex-date
- **WHEN** a bonus with ratio 0.1279 was announced 2026-04-28 with no ex-date and the last bar is 2026-10-09
- **THEN** the Scheduled line reads "announced 2026-04-28, no ex-date yet: bonus shares, 12.79 new shares per 100 held" and the helper returns nothing for it

#### Scenario: A stale undated announcement
- **WHEN** a bonus was announced 2019-04-26 with no ex-date
- **THEN** it is not shown

#### Scenario: The ex-date is set later
- **WHEN** the feed later stores a new version of that bonus with an ex-date
- **THEN** it is a dated issue and appears once, not as pending

### Requirement: Older undated announcements are counted, not silently dropped
When BONUS or STOCK_DIVIDEND events with no ex-date are older than `PENDING_ANNOUNCEMENT_DAYS` (365) days before the last bar, the Scheduled area SHALL end with one fixed line, "<n> older announcement(s) with no ex-date are no longer shown.", where n counts them. The line SHALL be printed only when n is above zero and the events feed was fetched, SHALL NOT say whether the announcements lapsed or were cancelled, and SHALL appear in a `--redact` copy (it is market-derived).

#### Scenario: VCB-shaped history
- **WHEN** fixtures hold a bonus announced 2026-04-28 with no ex-date, a bonus announced 2019-04-26 with no ex-date and a stock dividend announced 2020-06-26 with no ex-date, and the last bar is 2026-10-09
- **THEN** the 2026-04-28 bonus is shown as "announced 2026-04-28, no ex-date yet" and the line reads "2 older announcement(s) with no ex-date are no longer shown."

#### Scenario: Nothing is older
- **WHEN** every undated bonus or stock dividend is within 365 days, or none exists
- **THEN** no such line is printed

#### Scenario: Feed never fetched
- **WHEN** events for the ticker have never been fetched
- **THEN** the line is not printed (the never-fetched sentence is)

#### Scenario: A dated issue is not counted
- **WHEN** an old announcement later received an ex-date (a new version of the same item)
- **THEN** it is a dated issue and is not counted as undated

### Requirement: Every feed-derived line states when the feed was last fetched, and never fetched is not none found
The brief SHALL state, in the header of the DIVIDENDS block and wherever the feed decides a line (the Scheduled line, the week notes, the footnote of the combined week line, the week-1 fallback), the time of the last successful fetch of events for that ticker, and SHALL say when the latest attempt failed. When events for a ticker have never been fetched, or no fetch has succeeded, the brief SHALL NOT print "none found" for it: it SHALL say that no dividend or share issue can be listed or checked, that this is not the same as none found, and print the snapshot command. "None found" SHALL be printed only after a successful fetch. The Scheduled line SHALL end by saying an announcement made after the last fetch is not shown. No staleness threshold SHALL be applied; the time and its age against the last bar are printed.

#### Scenario: Never fetched
- **WHEN** the feed log has no row for `ZZZ` (a hypothetical ticker never passed to the snapshot) and `events`
- **THEN** the block says ZZZ's events have never been fetched and prints the snapshot command; it prints no list, no Scheduled line and no "none found"

#### Scenario: Fetched, nothing dated
- **WHEN** the latest fetch of `SAB` events is `ok` or `empty` and no event is dated after the last bar
- **THEN** the Scheduled line reads "none found" and the header states the last fetch time

#### Scenario: The latest attempt failed
- **WHEN** the latest fetch row is `rate_limited` after an earlier `ok`
- **THEN** the header gives the earlier success time and says the latest attempt failed

#### Scenario: No log file
- **WHEN** the feed log file does not exist
- **THEN** every held ticker reads as never fetched and the brief still completes

### Requirement: Ex-date and share-issue lines appear for the next 5 trading days by calendar-day approximation
There being no trading calendar, an event SHALL be treated as in the window when its ex-date is after the last bar date and no more than `WINDOW_CALENDAR_DAYS` (7) calendar days after it, and the exact ex-date SHALL be printed with a statement that it is within 7 calendar days of the last bar. This approximation SHALL only select which feed dates are printed; the range itself SHALL remain the model's 5-session band. For a cash dividend the line SHALL state the ex-date and the per-share amount, that from that day the whole range moves down by the dividend, the shifted range, the record date and the payout date or "not announced". The shifted range SHALL be the displayed range in thousand VND less the dividend converted from VND to thousand VND, rounded like the range, and SHALL NOT be shown when more than one ex-date is in the window or when its lower end is not positive. For a count-changing share issue the market line SHALL state the ex-date, the ratio, and that the board price is adjusted the same day so the range does not apply from then; it SHALL show no shifted range. A separate line from the holding section SHALL state that the investor's share count and cost per share change from that day and that the investor should update the entries. A RIGHTS_OFFER whose ex-date is in the window SHALL get a line saying to read the notice, that nothing is calculated, and that the board price may be adjusted the same day so the range above may not apply from then. Ex-dates after the window SHALL appear only on the Scheduled line with their exact dates.

#### Scenario: A dividend in the window
- **WHEN** the last bar is 2026-07-23, the displayed range is 45.69 to 48.30 and a stored dividend of 3,000 VND has ex-date 2026-07-28
- **THEN** the line states ex-dividend 2026-07-28, 3,000 VND per share, and a shifted range of about 42.69 to 45.30, with the record date 2026-07-29 and payout 2026-08-28

#### Scenario: Units
- **WHEN** a dividend of 2,000 VND is in the window and the range is 41.74 to 44.06 (thousand VND)
- **THEN** the shifted range is 39.74 to 42.06

#### Scenario: An issue in the window
- **WHEN** a stock dividend with ratio 0.2604104 has an ex-date inside the window
- **THEN** the market line states the ex-date and "26.04 new shares per 100 held", says the range does not apply from that day, and shows no shifted range, and a holding line tells the investor to update the entries

#### Scenario: Just beyond the window
- **WHEN** an ex-date is 9 calendar days after the last bar
- **THEN** it is not an ex-date-in-the-window line and it appears on the Scheduled line with its exact date

#### Scenario: A rights offer in the window
- **WHEN** a rights offer has an ex-date inside the window
- **THEN** the line says to read the notice, nothing is calculated and the range may not apply from then, and no shifted range is shown

#### Scenario: Payout not announced
- **WHEN** the stored event has no payout date
- **THEN** the line says payout "not announced"

### Requirement: A level set before an ex-date gets a separate note and is never adjusted
For each level the investor entered, and each cash dividend or count-changing issue (BONUS or STOCK_DIVIDEND) whose ex-date is after the level's entry date and on or before the last bar date, the brief SHALL print one note line beneath the level's own line, labelled with its source ("company-announcement source"), stating the event and its ex-date, the level's entry date, that the board price was adjusted down by about the dividend (or was adjusted for the issue) that day and that the level was set before it, and that the brief does not change the level, followed by the adjustment-status clause: for NOT_YET_ADJUSTED "Stored history is not yet adjusted for it.", for UNCLEAR "Whether stored history is adjusted for it yet could not be told.", for ADJUSTED nothing. The note SHALL be a separate line: the level line's own words SHALL stay limited to reached or not reached and the distance (Rule 6). The brief SHALL NOT adjust, move, re-date or re-word the investor's level or its text, and SHALL NOT suggest doing so.

#### Scenario: A dividend after the level was entered
- **WHEN** a hypothetical level was entered on 2026-07-15 and a 3,000 VND dividend went ex on 2026-07-28, with the last bar after that date
- **THEN** a note beneath the level says a dividend of 3,000 VND a share went ex on 2026-07-28, after the level was entered on 2026-07-15, that the board price was adjusted down by about that amount that day and that the level was set before it

#### Scenario: History not yet adjusted
- **WHEN** the event's adjustment status is NOT_YET_ADJUSTED
- **THEN** the note ends with "Stored history is not yet adjusted for it."

#### Scenario: Level entered after the ex-date
- **WHEN** the level was entered on 2026-08-01
- **THEN** no note is printed for the 2026-07-28 dividend

#### Scenario: The level line is unchanged
- **WHEN** a note is printed
- **THEN** the level line is identical to what it would be without the note, and the level's price and text are not altered

### Requirement: Adjustment status is checked from the stored bars at run time, not assumed
For each cash dividend or count-changing issue whose ex-date is on or before the last bar date, the brief SHALL classify the stored history as `ADJUSTED`, `NOT_YET_ADJUSTED` or `UNCLEAR` from the stored ex-day open and the previous stored close, with no vendor call. The observed gap is `open / previous close - 1`. The expected gap if history were not adjusted is `-D / P` for a cash dividend (D in the stored price unit, P the previous stored close) and `-r / (1 + r)` for a stock issue of ratio r. The status SHALL be `UNCLEAR` when either stored bar is missing or not positive, when the daily sigma of the ticker from the public volatility function cannot be computed, or when the expected gap is within `UNCLEAR_GAP_SIGMAS` (2.0) daily sigmas of the ticker (a floor relative to the ticker's own volatility, Rule 3); otherwise `NOT_YET_ADJUSTED` when the observed gap is at or below half the expected gap, and `ADJUSTED` otherwise. The brief SHALL NOT assume any vendor adjustment lag, and any statement of the lag SHALL say that only an upper bound (at most 3 sessions on one observed case) is known and no lower bound.

#### Scenario: Adjusted history
- **WHEN** the previous close is 43.60, the ex-day open is 43.00 and a 3,000 VND dividend (3.00) went ex, for a ticker whose daily sigma is about 1%
- **THEN** the expected gap is -6.9%, the observed gap is -1.4% and the status is ADJUSTED

#### Scenario: Raw history
- **WHEN** the previous close is 46.60, the ex-day open is 43.60 and the dividend is 3.00
- **THEN** the observed gap is -6.4%, the expected -6.4%, and the status is NOT_YET_ADJUSTED

#### Scenario: A stock issue
- **WHEN** a bonus of ratio 0.10 went ex, the expected gap is -9.1%, the previous close is 30.00 and the ex-day open is 27.30
- **THEN** the status is NOT_YET_ADJUSTED, and with an open of 29.80 it is ADJUSTED

#### Scenario: A small dividend
- **WHEN** a 500 VND dividend goes ex on a 22.90 price, so the expected gap is -2.2%, for a ticker with daily sigma 1.5%
- **THEN** the status is UNCLEAR

#### Scenario: Missing bar or no sigma
- **WHEN** the ex-date has no stored bar, or fewer than 61 closes precede it
- **THEN** the status is UNCLEAR

#### Scenario: No vendor call
- **WHEN** the status is computed
- **THEN** only the stored bars, the feed events and the loaded model are read, and no network call is made

### Requirement: The week just ended shows the board move and the move excluding the event in one line
The week just ended is the last five stored sessions, so an event is in it when its ex-date is after the date of the sixth-last stored bar and on or before the date of the last bar (no calendar approximation). Only cash dividends and count-changing issues (BONUS or STOCK_DIVIDEND) count; rights offers SHALL NOT produce a week note. Let `s` be the stored close at the sixth-last bar, `c` the stored close at the last bar, `eve` the stored close on the last session before the ex-date, D the dividend in thousand VND and r the issue ratio.

When exactly one such event is in the week and its adjustment status is ADJUSTED, the brief SHALL print one combined line, labelled by source, that replaces the move line and the inside or outside sentence of `add-weekly-holdings-brief`. For a cash dividend the line SHALL begin "Board move: <b>% (<raw prior close> -> <c>); about <D in VND> VND of that is the dividend that went ex on <date>. Excluding the dividend: <x>% (<s> -> <c>)." and, when a range is available, end "Last week's range was ±<y>%: the move excluding the dividend was inside | outside it." For an issue the first sentence names the share issue, its ratio as new shares per 100 held, its ex-date and that its price adjustment is about r / (1 + r) of the price, and the second sentence reads "Excluding the issue: ...". The raw prior close SHALL be `s * (eve + D) / eve` for a dividend and `s * (1 + r)` for an issue, rounded to two decimals for display; the board move SHALL be `(c - raw prior close) / raw prior close` computed from the displayed figure, and the move excluding the event `(c - s) / s`, both shown as simple percentages to one decimal. The range clause SHALL be percent only, SHALL use the issued band when an entry exists with a band (otherwise the recomputed band of the week-1 requirement, labelled as not issued), and the inside or outside test SHALL be `|ln(c / s)| * 100` at or below the band. A footnote sentence SHALL say the board figures are calculated and to check the broker's figure. In a `--redact` copy the combined line SHALL be printed without its range clause (the clause depends on what the issued-brief log holds), so that the copy shows the board move, the dividend or issue, the move excluding it and the footnote, and nothing read from the log.

When the status is NOT_YET_ADJUSTED the brief SHALL print, after the move and range sentences of `add-weekly-holdings-brief`, "History is not yet adjusted for the <ex-date> dividend; the stored move includes it." (or its issue form) and no board move. When UNCLEAR it SHALL say that whether stored history is adjusted yet cannot be told and that the move shown may include or leave out the event, with no board move. With more than one such event it SHALL list the ex-dates with the status of each and compute no board move. When the events feed has never been fetched for the ticker it SHALL say that whether an ex-date fell in the week is not known.

#### Scenario: The measured SAB week
- **WHEN** the stored closes are 43.97 (2026-07-23), 43.51, 43.60 (2026-07-27, the session before the ex-date), 43.15, 43.00 and 43.40 (2026-07-30), a 3,000 VND dividend went ex on 2026-07-28, the status is ADJUSTED and the issued band is 2.8%
- **THEN** the line reads "Board move: -7.7% (47.00 -> 43.40); about 3,000 VND of that is the dividend that went ex on 2026-07-28. Excluding the dividend: -1.3% (43.97 -> 43.40). Last week's range was ±2.8%: the move excluding the dividend was inside it."

#### Scenario: Board move first
- **WHEN** the combined line is printed
- **THEN** the dividend is named in the same sentence as the board move, before any other figure

#### Scenario: An issue in the week
- **WHEN** a count-changing issue with ratio 0.2604104 went ex inside the week, `s` is 40.00 and `c` is 35.00, and the status is ADJUSTED
- **THEN** the raw prior close is 50.42, the board move is -30.6% (50.42 -> 35.00), the adjustment is about 20.7% of the price, the move excluding the issue is -12.5% (40.00 -> 35.00)

#### Scenario: No issued band
- **WHEN** the issued entry has no band
- **THEN** the combined line has no range clause and the issued-brief sentence about the missing range stays

#### Scenario: No issued entry
- **WHEN** the log has no entry for the week
- **THEN** the range clause reads "Range recomputed today from prices up to <date>; not an issued range: ±<y>%: the move excluding the dividend was inside | outside it."

#### Scenario: History not yet adjusted
- **WHEN** the stored closes show a raw (unadjusted) drop on the ex-date and the status is NOT_YET_ADJUSTED
- **THEN** the note says history is not yet adjusted for the 2026-07-28 dividend and that the stored move includes it, and shows no board move

#### Scenario: The redacted copy of the measured week
- **WHEN** the measured SAB week is rendered with `--redact`
- **THEN** the line reads "Board move: -7.7% (47.00 -> 43.40); about 3,000 VND of that is the dividend that went ex on 2026-07-28. Excluding the dividend: -1.3% (43.97 -> 43.40)." followed by the footnote, with no "Last week's range", no "Move:" line and no comparison sentence

#### Scenario: Two ex-dates in the week
- **WHEN** two events went ex inside the week
- **THEN** both ex-dates are listed with their status and no board move is shown

#### Scenario: No ex-date in the week
- **WHEN** no stored event has an ex-date in the week and the feed was fetched
- **THEN** the brief adds no ex-date note to the week block

#### Scenario: Feed never fetched
- **WHEN** events for the ticker have never been fetched
- **THEN** the week block says whether an ex-date fell in the week is not known and why

### Requirement: A holding with no issued range gets a labelled recomputed percentage, never logged
When the issued-brief log has no entry for the ticker, or has entries but none with `as_of` equal to the sixth-last stored bar date (the two cases in which `add-weekly-holdings-brief` prints no previous range), the week block SHALL print, after that sentence, a range recomputed today: the band percentage from `sigma_daily_pct_from_closes` over the closes up to the sixth-last stored bar and `band_from_sigma`, using the model the brief already loaded, shown as a percentage only (no VND range), labelled "recomputed today from prices up to <date>; not an issued range", with the week's move compared to it in log space as the model's own hit test does and shown as a simple percentage. It SHALL use the public functions of the volatility module and SHALL NOT import `_window_hits`. It SHALL NOT be written to the issued-brief log. It SHALL NOT compare the move with the band, and SHALL say why, when the events feed has never been fetched for the ticker, when two or more events fell in the week, or when the one event's adjustment status is not ADJUSTED; when exactly one event fell in the week and its status is ADJUSTED, the comparison SHALL be made on the move excluding the event inside the combined line of the week requirement. When fewer than the closes the model needs are available it SHALL say the range could not be recomputed. It SHALL add no reliability figure. Because its presence depends on what the issued-brief log holds, it SHALL be printed only in the unredacted copy and SHALL be identical across a run and a re-run on the same bar.

#### Scenario: First brief, no ex-date
- **WHEN** a holding has no issued entry, 70 stored closes, and no ex-date in the last five sessions
- **THEN** the week block keeps "first brief: no previous range" and then shows the recomputed band as a percentage, the label "recomputed today from prices up to <sixth-last bar date>; not an issued range", and whether the move was inside or outside it

#### Scenario: Ex-date in the week, not yet adjusted
- **WHEN** the same holding has a dividend ex-date inside the week and its status is NOT_YET_ADJUSTED
- **THEN** the band and the move are shown, no inside or outside is stated, and the line says an ex-date fell in the week

#### Scenario: Ex-date in the week, adjusted
- **WHEN** the same holding has one dividend ex-date inside the week and its status is ADJUSTED
- **THEN** the recomputed band appears in the combined line, and the verdict is for the move excluding the dividend

#### Scenario: Not in the redacted copy
- **WHEN** a holding with no issued entry is rendered with `--redact`
- **THEN** no recomputed line, no recomputed band and no "first brief" sentence appears

#### Scenario: Never written
- **WHEN** the fallback is produced against a temporary issued-brief log directory
- **THEN** the log file is not created or changed

#### Scenario: The issued brief gave no range
- **WHEN** the matched issued entry has no band
- **THEN** no recomputed range is shown, only the issued-brief sentence about the missing range

#### Scenario: Too few closes
- **WHEN** fewer than 61 closes exist before the sixth-last bar
- **THEN** the block says last week's range could not be recomputed

### Requirement: A redacted copy keeps the market-derived lines and drops the purchase-, level- and log-derived ones
The market-derived lines of this capability (the DIVIDENDS header and its Scheduled and older-announcements lines, the feed-state sentences, the ex-date and share-issue window lines with their shifted range, the week's combined line without its range clause, the week notes for an unadjusted, unclear or multiple ex-dates and for an unknown feed, and the explanation line of the re-adjusted-close note) SHALL be produced from the market facts alone (which carry the feed events and the adjustment statuses), SHALL NOT use the holdings entry, and SHALL appear in a `--redact` copy. The holding-derived lines (the dividend list and share-issue list since the purchase date, the completeness sentence, the "no purchase date" sentence, the investor's "update your entries" sentence and every level note) SHALL be produced only by the holding section and SHALL NOT appear in a `--redact` copy, because which dividends are listed reveals the purchase date and a level note reveals a level. The log-derived lines (the combined line's range clause, the week-1 recomputed line and the line saying a comparison is suppressed for a holding with no issued range) SHALL NOT appear in a `--redact` copy either. The number tokens these lines print SHALL be in the redaction test's allow-list built from the market facts, so an unexpected number fails the test.

#### Scenario: Redacted copy of a holding with a purchase date
- **WHEN** a hypothetical holding with purchase date 2025-06-10 is rendered with `--redact`
- **THEN** the copy contains the DIVIDENDS header and the Scheduled line, but no "since your purchase date" line and no date that would reveal the purchase date

#### Scenario: Redacted copy and a level
- **WHEN** a hypothetical level entered on 2026-07-15 precedes a dividend ex-date
- **THEN** the redacted copy contains no level note and no level date

#### Scenario: Redacted copy and the issued log
- **WHEN** a holding with no issued entry and a one-event ADJUSTED week is rendered with `--redact`
- **THEN** the copy shows the board move and the move excluding the dividend but no recomputed range, no "first brief" sentence and no comparison sentence

### Requirement: A re-adjusted close that an ex-date explains says so
When the re-adjusted-close note of `add-weekly-holdings-brief` is printed and the feed lists a cash dividend or count-changing issue whose ex-date is after the logged `as_of` date and on or before the last bar date, the note SHALL be followed by one line, labelled by source, naming that event and ex-date as listed after that date, and saying the brief has not checked that it accounts for the difference. When the feed lists none, or has never been fetched, the note SHALL be left as it is and no explanation SHALL be claimed.

#### Scenario: A dividend is listed after the logged date
- **WHEN** the log holds a close of 46.60 for 2026-07-23, the stored close is now 43.60 and a 3,000 VND dividend went ex on 2026-07-28
- **THEN** the note is followed by a line naming the dividend ex 2026-07-28 and saying the brief has not checked that it accounts for the difference

#### Scenario: No explaining event
- **WHEN** the feed lists no event between the logged date and the last bar
- **THEN** the note is printed without an explanation line

### Requirement: The new fixed sentences contain no instruction and no advice
Every fixed sentence this capability adds (the DIVIDENDS block, the window lines, the level note, the week notes, the week-1 line, the not-fetched sentence) SHALL be a constant in the brief's `wording.py` and SHALL contain no buy, sell, hold or other instruction word and no direction claim, other than the owner-approved "update your entries" for a share issue, SHALL name its source, and SHALL be covered by the brief's tool-text guard test and by N1's final runtime scan, which every rendered line (the investor's own words removed) passes before the brief is shown. The guard test SHALL iterate the constants of `wording.py` (so a new constant is scanned without a list being edited) and SHALL render the new lines in full and redacted forms.

#### Scenario: A guard over the new sentences
- **WHEN** the new fixed sentences are rendered for every state in these requirements, in full and redacted forms, and scanned by the tool-text guard of `add-weekly-holdings-brief`
- **THEN** no banned word is found

### Requirement: No dividend arithmetic on the investor's shares is added
This capability SHALL NOT compute a dividend total, a net line, a dividend amount on the investor's share count, a share count after an issue, a cost per share after an issue, a yield, a tax or a fee figure. It SHALL NOT use `shares` or `shares_as_of` from the holdings entry.

#### Scenario: A holding with dividends and an issue
- **WHEN** a hypothetical holding of 1,000 shares has two listed dividends and one listed issue
- **THEN** the DIVIDENDS block shows per-share figures and the issue ratio only, with no amount on 1,000 shares, no total and no new share count

## MODIFIED Requirements

<!-- These three blocks are copies of requirements in `add-weekly-holdings-brief` as they stand after its review fixes of 2026-10-12 (re-diffed in task 1.1, design "Re-diff against N1 final 2026-10-12"), with the edits of this change applied. They can only be synced after that change is synced. -->

### Requirement: The brief is produced by a hand-run script and calls no language model
The system SHALL provide `backend/scripts/weekly_brief.py`, a thin entry point over the package `backend/app/services/brief/`, that the owner starts by hand after the market close. No route, startup hook, scheduler, debate hook or API call SHALL start it, expose its output or read its inputs. Neither the script nor the package SHALL import or call a language-model client, and the brief SHALL contain no language-model text. The package SHALL NOT reference the company feed except through its one adapter, `feed_source.py` (`test_company_feed_isolation.py` allows exactly that file). Each section SHALL be a pure function from frozen data to a tuple of lines, and the brief SHALL be assembled from an ordered list of such functions, so that later changes add sections without rewriting existing ones.

#### Scenario: A language-model client is never loaded
- **WHEN** a fresh interpreter imports the brief's run module and the script module
- **THEN** none of `anthropic`, `openai`, `google.generativeai`, `claude_agent_sdk`, `app.services.debate.llm_client`, `app.services.debate.engine`, `.runner`, `.synthesiser` or `.news` is in `sys.modules`

#### Scenario: No route exposes the brief
- **WHEN** the FastAPI app's routes are listed
- **THEN** no path or endpoint module refers to the brief or to holdings

#### Scenario: Only the adapter mentions the feed
- **WHEN** the sources under `backend/app/services/brief/` are searched
- **THEN** only `feed_source.py` contains the text the feed isolation test forbids outside the feed package

#### Scenario: A later change adds a section
- **WHEN** a section function is added to the ordered list
- **THEN** no existing section function or its test changes

### Requirement: THE WEEK JUST ENDED compares the close with the range that was actually issued
For each holding with at least 6 stored closes the brief SHALL print the move over the last 5 stored sessions as a simple percentage with the two closes, and the previous range found in the issued-brief log with exact match on `as_of == dates[-6]`. Only log entries issued for a bar strictly before the last bar SHALL be read, so a re-run on the same bar says what the first run said; among entries for `dates[-6]` the one with a band is preferred, then a post-close one, then the later line. It SHALL say the close was inside the range when `|ln(close[-1] / close[-6])| × 100 <= band_pct` and outside otherwise, computed on stored closes. The sentences SHALL be: "first brief: no previous range" when the log has no entry for the ticker; "no range was issued for the week starting after <date>; the latest one on file is for <date>" when entries exist but none matches; "last week's brief gave no range" with the plain status wording when the matched entry has no band; and "Last week's range was ±<b>% (<lo> to <hi>): the close was inside it" or "outside it" otherwise. One fixed sentence SHALL state that the comparison uses stored prices, which may be adjusted for dividends and share issues; whether an ex-date fell in the week is stated by the notes of `add-dividend-and-ex-date-lines`. The brief SHALL NOT recompute a past range except in that change's labelled, percent-only, unredacted-copy fallback, and SHALL NOT write a recomputed range to the issued-brief log. When exactly one cash dividend or count-changing issue with an ADJUSTED status went ex inside the week, the combined line of `add-dividend-and-ex-date-lines` replaces the move line and, in the unredacted copy, the inside or outside sentence.

#### Scenario: First brief
- **WHEN** the log file does not exist
- **THEN** each holding's week block reads "first brief: no previous range" followed by the labelled recomputed percentage of `add-dividend-and-ex-date-lines`, and nothing is written to the log by the recompute

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

### Requirement: Fixed sentences, footer and the brief disclaimer are guarded
Every brief SHALL contain "This brief does not update during the week. It does not predict direction.", the re-read triggers line (unredacted copy only; see its own requirement), a footer that mentions only the investor's own levels ("One of your levels appearing or being reached would make a re-read worthwhile. Re-run this brief to refresh."), and the brief disclaimer from `docs/DISCLAIMER.md`, section "Brief version", verbatim. The brief SHALL NOT contain announcement tags, insider wording, the optional biggest-weekly-move line, a COMPANY block, a net line, or the full or inline disclaimer; its only dividend content is the DIVIDENDS block of `add-dividend-and-ex-date-lines`, which carries no total and whose announcement wording is limited to event dates and numbers labelled by their source. A test SHALL compare the code's copy with the blockquote under "## Brief version" after whitespace normalisation, and SHALL require `coverage_phrase` of the served model's `range_coverage` to be "about 2 in 3" while the copy says "About 2 weeks in 3". At run time, if the loaded model's coverage does not round to 0.68, the script SHALL exit 1 before any vendor call and print no brief, and the brief builder SHALL itself refuse any facts that carry another coverage. Before a brief is shown, every line the tool wrote (the investor's own words removed) SHALL pass one final scan, after NFKC normalisation and removal of format characters, for buy, sell, hold, confidence and market sentiment, and the triggers line for the banned judgement words and their stem forms; a failure SHALL stop the run with the line number only.

#### Scenario: The copy equals the source
- **WHEN** the code's disclaimer and the "Brief version" blockquote are whitespace-normalised
- **THEN** they are equal

#### Scenario: The source changes
- **WHEN** `docs/DISCLAIMER.md`'s brief text is edited and the code is not
- **THEN** the guard test fails

#### Scenario: A retrain at another coverage
- **WHEN** the model's `range_coverage` is 0.80
- **THEN** the script exits 1 with a message naming the mismatch, makes no vendor call and prints no brief

#### Scenario: No announcement tag, insider, company or net line
- **WHEN** any brief is rendered
- **THEN** it contains no "insider" wording, no COMPANY heading and no net line, any DIVIDENDS block carries no total, and a brief for facts without a feed snapshot has no DIVIDENDS block
