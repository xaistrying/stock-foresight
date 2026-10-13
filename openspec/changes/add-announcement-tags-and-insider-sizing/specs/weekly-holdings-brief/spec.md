## ADDED Requirements

### Requirement: The COMPANY block separates what needs a look from what is for information
For each held ticker the brief SHALL print a COMPANY block with three parts: "Needs a look since the last brief", "For information" and "Scheduled". An announcement SHALL be listed when its date is after the last-bar date of the previous issued brief for that ticker, or when it was first seen after that date and did not arrive in the ticker's first fetch. With no previous issued brief it SHALL list the last 14 calendar days and say so. "Needs a look" SHALL hold only insider or major-shareholder trades and share issues or capital changes that are not small (see the small-issues requirement) and are not additional-listing (`AIS`) events, which SHALL appear under "For information", and SHALL show the newest 10 items and state how many more exist, while the re-read triggers line counts every item listed (not only the ones shown); an insider trade whose window has not ended SHALL also be listed when it is not new, marked "listed again: window still open". "For information" SHALL show the newest 10 items and state how many more exist. The block SHALL read "none" only after a successful fetch of the announcement source and SHALL read "not checked" when the source was never fetched. The block's data SHALL come only through the brief's one feed adapter. Rule 5 applies: the block names its source for what it reads and labels third-party text.

#### Scenario: A new insider registration
- **WHEN** an insider-trade event is dated after the previous brief's last-bar date
- **THEN** it appears under "Needs a look since the last brief" and not under "For information"

#### Scenario: A late snapshot
- **WHEN** an item is dated before the previous brief's last-bar date but was first seen after it, in a fetch that was not the ticker's first
- **THEN** it is listed

#### Scenario: A registration still open
- **WHEN** an insider trade from last week has a window ending after the brief's last-bar date
- **THEN** it is listed again and marked "listed again: window still open"

#### Scenario: First brief
- **WHEN** there is no previous issued brief for the ticker
- **THEN** items from the 14 calendar days before the last bar are listed and the block says it is listing the last 14 days

#### Scenario: Many items under needs a look
- **WHEN** 14 registered trades qualify for "Needs a look"
- **THEN** the newest 10 are shown, the block says 4 more items under that heading exist, and the triggers line counts all 14

#### Scenario: Many items for information
- **WHEN** 14 items qualify for "For information"
- **THEN** the newest 10 are shown and the block says 4 more exist

#### Scenario: Nothing found versus not checked
- **WHEN** the source has answered and no item qualifies
- **THEN** the parts read "none found in what the source returned"
- **WHEN** the source has never been fetched for the ticker
- **THEN** the parts read "not checked" and no part reads "none"

### Requirement: Announcements carry a type tag and a basis, and no tag says routine
Each listed announcement SHALL carry exactly one tag from: insider or major-shareholder trade; share issue or capital change; dividend; shareholder meeting; results; personnel or disclosure officer; and "Other announcement, not classified; the title gives no amount". No tag, heading or sentence SHALL call an announcement routine, minor or administrative. Each tag SHALL show its basis, "(event record)" or "(title keyword)". Event-record tags SHALL come from the event code only: `DDIND`, `DDINS` and `DDRP` to insider trade; `ISS` and `AIS` to share issue or capital change; `DIV` to dividend; `AGME` and `EGME` to meeting; any other code to the unclassified tag. Keyword tags SHALL apply only to news titles that start with the held ticker and a colon. A news title that does not start that way SHALL be shown as "Press item (may concern another company; not classified)" under "For information". When a title matches the share-issue or capital-change keyword class it SHALL take that class; otherwise exactly one matching class SHALL be used; two or more matching classes SHALL give the unclassified tag. A board-resolution title alone, a bond issue or buy-back, a penalty notice and a transfer-restriction notice SHALL NOT match any class. An unclassified item SHALL be followed by "The title does not give the amount; the notice does." The titles SHALL be shown in their original language.

#### Scenario: Insider code gives the tag without keywords
- **WHEN** an event has code `DDIND` and a title with no keyword the classifier knows
- **THEN** it is tagged "Insider or major-shareholder trade (event record)"

#### Scenario: A board resolution is not routine
- **WHEN** a company filing's title is only a board resolution notice
- **THEN** it is tagged "Other announcement, not classified; the title gives no amount" and the word routine appears nowhere in the block

#### Scenario: A press item
- **WHEN** a news title does not begin with the ticker and a colon
- **THEN** it is shown as a press item, is not classified, and is listed under "For information"

#### Scenario: Two non-capital classes match
- **WHEN** a company filing's title matches the results class and the personnel class
- **THEN** it is tagged unclassified

#### Scenario: Capital class wins
- **WHEN** a company filing's title matches both the dividend class and the share-issue or capital-change class
- **THEN** it takes the share-issue or capital-change tag and appears under "Needs a look"

#### Scenario: A bond buy-back
- **WHEN** a title announces an early buy-back of bonds
- **THEN** it is not tagged as a share issue or capital change

### Requirement: Keyword classes are enabled only after a labelled accuracy check
Each keyword class SHALL be disabled in code until a labelled check on stored titles shows that every title the class claims is correctly labelled and that it claims at least 3. Disabled classes SHALL leave their titles unclassified. The check SHALL be a read-only script over the stored feed, its labels SHALL be kept outside the repository, and the counts per class (claimed, correct, missed) SHALL be recorded in the change's design with no title text. The check SHALL also list unclassified titles containing a share or capital word for human review.

#### Scenario: No class is enabled yet
- **WHEN** the brief is built before the check has been run
- **THEN** every news title of a company filing is tagged unclassified, and event-record tags are unaffected

#### Scenario: A class fails the check
- **WHEN** the labelled sample shows the results class claimed one title that was not a results notice
- **THEN** the results class stays disabled and its titles are tagged unclassified

#### Scenario: A class is enabled in tests only by parameter
- **WHEN** a test needs a keyword class
- **THEN** it passes the class in explicitly and the module-level default stays empty

### Requirement: A source-health line states when the source answered and how old its newest item is
Each COMPANY block SHALL open with a line naming the source and giving, for news and for corporate events separately, the date of the last successful answer, the number of items returned and the date of the newest item, in the form "announcement source answered <date>; <n> items returned; newest <date>". When the items returned equal the source's limit per call it SHALL say so. When the newest item is older than the last bar it SHALL print the number of days and "nothing newer was returned", and SHALL NOT apply an age threshold or the word stale. It SHALL always print the age of the last answer in days against the last bar and the sentence "An announcement made after the last fetch is not shown.", SHALL apply no staleness threshold, and SHALL print the snapshot command the adapter provides when a fetch is missing or failed; the brief SHALL NOT run it. When the latest attempt failed it SHALL name the date and error class and the last successful answer. When the source was never fetched or no fetch has succeeded it SHALL say so and the block's parts SHALL read "not checked".

#### Scenario: Answered, newest item old
- **WHEN** the source answered on 2026-10-10 with 50 items and the newest is dated 2026-08-28
- **THEN** the line shows both dates, the count, the limit remark, the number of days between the newest item and the last bar, and "nothing newer was returned"

#### Scenario: Latest attempt failed
- **WHEN** the latest fetch was rate-limited after an earlier successful one
- **THEN** the line names the failed attempt's date and error class and the last successful answer's date

#### Scenario: Never fetched
- **WHEN** no fetch exists for the ticker
- **THEN** the line says the source was never fetched, the parts read "not checked", and the snapshot command is printed but not run

#### Scenario: Snapshot is old
- **WHEN** the last answer is 5 days before the last bar
- **THEN** the line prints that age and "An announcement made after the last fetch is not shown." and applies no stale label

### Requirement: An insider or major-shareholder trade line states what the record says, and where its window stands
A trade line SHALL read "<name> filed a notice of a sale of <quantity> <TICKER> shares (window <start> to <end>; status: not started | under way | ended)", or "a purchase of" for a purchase, where the name is the text before " - Đăng kí" in the title, shown as third-party text inside the sanitiser's quotes. The line SHALL also carry the original-language title as third-party text and the date of the record. The word for the direction SHALL be taken from the record's action field through a closed set (Sell to "sale", Buy to "purchase") and SHALL be used only when it agrees with the title's Mua or Bán and the title's ticker matches the record's ticker; otherwise the line SHALL read "filed a notice (direction or quantity could not be read from the title)" and show the sanitised title. The tool's own text SHALL NOT contain the words buy, sell or hold. The status SHALL be computed against the brief's last-bar date: "not started" when the start is after it; "under way" when the start is on or before it and the end is on or after it, followed by "the record does not say how much has been carried out"; "ended" when the end is before it, followed by "the record does not say whether it was carried out"; "window not given in the record" when a date is missing. When the end is more than 7 calendar days after the last bar, the line SHALL add "The window runs <n> weeks; this brief covers one." with n the window length in weeks rounded up. When no quantity is in the title the line SHALL say so and give the read-the-notice checklist. The line SHALL NOT state the event code's class (individual, institution, related person). Every such item SHALL end with "The usual range is built from past prices only. It does not account for this announcement, so the real swing could be larger."

#### Scenario: A registration not yet started
- **WHEN** the window starts after the last bar
- **THEN** the line reads "filed a notice of a sale of <quantity> <TICKER> shares" with the window dates and "status: not started"

#### Scenario: A registration published after its window ended
- **WHEN** the window ended before the last bar
- **THEN** the line reads "status: ended" and says the record does not say whether it was carried out, and does not say not started or planned

#### Scenario: A window longer than the brief
- **WHEN** the window runs 12 days and ends 10 days after the last bar
- **THEN** the line says the window runs 2 weeks and the brief covers one

#### Scenario: No quantity in the title
- **WHEN** a title reads "<name> - Đăng kí Bán <TICKER>" with no number
- **THEN** the line reads "filed a notice of a sale of <TICKER> shares" with "quantity not stated in the title" and gives the checklist, and no size is shown

#### Scenario: Direction disagrees
- **WHEN** the title says Mua and the action field says Sell
- **THEN** the line reads "filed a notice (direction or quantity could not be read from the title)", shows the sanitised title, and contains neither sale nor purchase

#### Scenario: No event-code class
- **WHEN** a trade line is rendered for a record with code `DDINS`
- **THEN** the line does not say institution or any class derived from the code

### Requirement: Third-party text is labelled, bounded and sanitised
Every announcement title and counterparty name SHALL be passed through one function that applies the existing `_clean`, removes the characters U+201C and U+201D, replaces `|` with `/`, a backtick with an apostrophe, `<` and `>` with `‹` and `›` and `[` and `]` with `(` and `)`, replaces any `http://` or `https://` run with "(link removed)", removes the characters that survive the cleaner but render as nothing (the combining grapheme joiner, the Hangul and Khmer fillers, the Mongolian free variation selectors, the braille blank, the variation selectors and their supplement), replaces look-alike quotation marks (ASCII `"`, U+201E, U+201F, U+2033, U+FF02, U+00AB, U+00BB and the CJK corner brackets U+300C to U+300F) with a plain apostrophe, collapses whitespace and caps the length at 200 characters for a title and 120 for a name with an ellipsis. The result SHALL be shown inside U+201C and U+201D quotes under a header or label that says it is third-party text. No third-party text SHALL be translated, summarised or reworded and no language model SHALL be called. Rule 5 applies.

#### Scenario: Markup and links in a title
- **WHEN** a stored title contains an unclosed `<`, `[text](https://example.invalid)` and a `|`
- **THEN** the displayed title contains none of those characters, shows "(link removed)", and the output has no table separator, link or tag from it

#### Scenario: A title tries to close its own quote
- **WHEN** a title contains U+201D followed by further text
- **THEN** the displayed span contains no U+201D inside it and one closing quote at its end

#### Scenario: A long title
- **WHEN** a title is 500 characters
- **THEN** the displayed title is at most 200 characters plus the ellipsis

#### Scenario: Invisible characters and look-alike quotes
- **WHEN** a title contains U+034F, U+3164, a variation selector, or a straight, guillemet or CJK quotation mark
- **THEN** the invisible characters are gone, each quotation mark is a plain apostrophe, and the output is exactly one well-formed span; a sweep of every code point leaves no invisible or delimiter character inside a span

#### Scenario: The language is kept
- **WHEN** a title is Vietnamese
- **THEN** the displayed text is that Vietnamese text, with its diacritics

### Requirement: The Rule 6 guard exempts one thing, quoted third-party text, besides the investor's own block
The guard over the brief's tool-originated text (the requirement "The brief's own text never carries a buy, sell or hold word (Rule 6)" created by `add-weekly-holdings-brief`, which SHALL be modified accordingly when both are synced) SHALL continue to fail on the words buy, sell and hold, SHALL scan the COMPANY constants as it scans the other fixed sentences, and SHALL strip before scanning only: (1) the investor's verbatim rule block (that requirement, now applied by position: only at the start of a level line and before the level label " (you wrote this on ", never by substring, so a short level text cannot hide a tool word); and (2) third-party spans, meaning text inside U+201C and U+201D produced by the sanitiser. The run-time scan of every line the tool wrote SHALL strip the spans the same way and SHALL fail when a line still holds U+201C or U+201D after the spans are removed. No frame or other form containing a guarded word SHALL be exempt. No constant tool string SHALL contain U+201C or U+201D. A registered trade SHALL be worded with the nouns "sale" and "purchase". Rule 6 text in `CLAUDE.md` and `openspec/config.yaml` SHALL NOT be edited by this change.

#### Scenario: A tool sentence uses a guarded word
- **WHEN** a tool-originated string contains "SELL", "buy" or "hold"
- **THEN** the guard test fails

#### Scenario: A third-party span is exempt
- **WHEN** a quoted third-party title contains an English word "hold"
- **THEN** the guard test passes for that span and still fails for the same word outside quotes

#### Scenario: Other quotes are not exempt
- **WHEN** a tool string contains the word "sell" inside straight quotes
- **THEN** the guard test fails

#### Scenario: A span cannot close early
- **WHEN** a title contains U+201D followed by the word "sell"
- **THEN** the sanitiser removes the character and the word is inside the span, or the test shows the span closed only at its end

#### Scenario: A short level text hides nothing
- **WHEN** the investor's level texts are "l", "e" and "ing" and a tool sentence contains "sell"
- **THEN** the guard fails on that sentence, and a clean brief with those level texts passes

#### Scenario: Holdings is not a hit
- **WHEN** the output contains the header "HOLDINGS LISTED"
- **THEN** the guard test passes

#### Scenario: A trade line has no direction word
- **WHEN** a trade line for a registered sale and one for a purchase are rendered
- **THEN** each contains "sale" or "purchase" and no buy, sell or hold word outside its quoted spans

### Requirement: Shares outstanding come from one vendor field, cross-checked, cached and fetched only when needed
The system SHALL read a held ticker's share count from the vendor's `ratio_summary()` (`Company(source="vci", symbol=S)`): the latest row whose `ratio_type` is `RATIO_TTM`, chosen by the integer columns `year_report` and `quarter` and never by the string column `year`, field `number_of_shares_mkt_cap`. It SHALL cross-check that count against the four `issue_share` values of `overview()`, read by position. The count SHALL be used only when it equals every one of the four; a missing field, a zero, NaN or non-integer count, no `RATIO_TTM` row, or any difference SHALL make the count unavailable for that run. The new module that imports `vnstock` SHALL call `app.vnstock_guard.install()` before that import, SHALL validate the ticker as upper-case letters and digits, SHALL turn any `SystemExit` raised inside the call (vnai's rate limit, recognised by the repository's `_is_rate_limit_exit`, or another exit of the library) into an ordinary exception so nothing ends the brief before it is written, SHALL NOT catch `KeyboardInterrupt`, SHALL treat an integer too large for a float as an unusable value, and SHALL NOT wait or retry. After the first failed share-count call of a run (not a disagreement of the two counts) no further share-count call SHALL be made in that run. The vendor SHALL be called only when a trade line (in either copy) has a stated quantity, sizing is on and the cached value for the ticker is missing or older than 7 days. A cross-checked value SHALL be cached with its period (`year_report`, `quarter`) and fetch time in a file named with the `holdings` prefix beside the holdings file, with the permissions and refusal rules the holdings file has, written atomically, outside the repository and outside any database. A disagreeing value SHALL NOT be cached. If a fetch fails and a cached value exists, the cached value SHALL be used with its fetch date. Sizing SHALL be on by default; the option `--no-sizing` SHALL make no vendor call for a share count. Rule 5 applies: the count is labelled as the vendor's, as the latest-quarter row of that period, with its fetch date, and SHALL NOT be described as the count "as of" a quarter.

#### Scenario: The counts agree
- **WHEN** the latest `RATIO_TTM` row and all four `issue_share` values show the same count
- **THEN** the count is used, cached with its period and fetch time, and labelled as the VCI latest-quarter row with its period and fetch date

#### Scenario: The counts disagree in the VPB shape
- **WHEN** the latest `RATIO_TTM` row shows 10,000,000,000 and the four `issue_share` values are [10,000,000,000, 7,933,923,601, 10,000,000,000, 7,933,923,601]
- **THEN** the count is unavailable, nothing is cached, and the size is not shown

#### Scenario: An annual row is last
- **WHEN** the frame's last rows by `year_report` and `quarter` are annual rows (`RATIO_YEAR`, quarter 5)
- **THEN** the count is read from the latest `RATIO_TTM` row

#### Scenario: The string year column is not used
- **WHEN** the frame's `year` column sorts differently from (`year_report`, `quarter`)
- **THEN** the period is chosen by the integer columns

#### Scenario: The overview columns are duplicated
- **WHEN** `overview()` returns four columns all named `issue_share`
- **THEN** the four values are read by position and none is looked up by label

#### Scenario: Cached value is fresh
- **WHEN** a cached value is 3 days old
- **THEN** no vendor call is made

#### Scenario: The limiter exits the process
- **WHEN** the vendor call raises the limiter's `SystemExit`
- **THEN** the brief continues with the cached value if there is one, otherwise with the fallback, and the process does not exit

#### Scenario: Any other exit inside the call is also an unavailable count
- **WHEN** the call raises a `SystemExit` that is not the limiter's
- **THEN** the count is unavailable, the brief is still written, and a `KeyboardInterrupt` still interrupts

#### Scenario: One failure closes the gate for the run
- **WHEN** the share-count call fails for one held ticker
- **THEN** no further share-count call is made for the other tickers of that run, and their lines say the count could not be read

#### Scenario: The cache cannot be read
- **WHEN** reading the cache raises an input error
- **THEN** the brief goes on with no cache, says so on stderr, and does not overwrite the file

#### Scenario: A cached value is stamped in the future
- **WHEN** the cached fetch time is later than the run
- **THEN** the value is not used and a note says so

#### Scenario: Sizing is on by default
- **WHEN** the script is run without `--no-sizing` and a trade line has a stated quantity and no fresh cached value
- **THEN** the share count is fetched

#### Scenario: Sizing is off
- **WHEN** the script is run with `--no-sizing`
- **THEN** no share-count vendor call is made and trade lines show the fallback

#### Scenario: Nothing needs sizing
- **WHEN** no trade line has a stated quantity
- **THEN** no share-count vendor call is made

#### Scenario: The guard test covers the new module
- **WHEN** `test_every_vnstock_importer_installs_the_guard_first` runs
- **THEN** the new module is in its scan with the guard import first, and no brief module imports `vnstock`

#### Scenario: The cache file is unsafe
- **WHEN** the cache file is group- or world-readable
- **THEN** it is refused as the holdings file is and the brief uses the fallback

### Requirement: A size is shown only when the share count is safe, and the fallback is complete without it
The trade line SHALL show the quantity as a percentage of shares outstanding with at most two significant figures, with the vendor count, its period and its fetch date, only when a quantity is stated, a cross-checked count is available and no recent issue makes the count unsafe. The count SHALL be withheld when an issue event that changes the company's share count by at least `ISSUE_MATERIAL_RATIO` (1%) has a date after the cached value's fetch time or within `SETTLING_DAYS` (30) days before the run date. The event's date SHALL be its ex-rights date, else its record date, else its publication date. The rule SHALL apply to every issue class in N2a's issue-class enum (bonus, stock dividend, rights offer, private placement, other) at a ratio of at least 1%, SHALL ignore employee issues under 1%, and SHALL treat a non-employee issue with a missing or zero ratio as material. It SHALL NOT use additional-listing events, a quarter end, or N2a's investor count-changing rule. When the size cannot be shown the line SHALL give the reason and the checklist "To size it, read the notice: who filed it, whether it is a sale or a purchase, how many shares in total against the shares outstanding, how it will be done, and the window.", and for an issue the reason SHALL read "size not shown, because the share count is changing (issue on <date>)", for a disagreement "size not shown, because the vendor's two share counts disagree". The fallback line SHALL carry the same counterparty, direction, quantity or its absence, window state and range sentence as the sized line. `ISSUE_MATERIAL_RATIO` and `SETTLING_DAYS` are policy constants that rest on one example and SHALL be named constants with a comment stating that.

#### Scenario: A sized registration
- **WHEN** a registration of 30,000,000 shares is read against an agreed count of 1,282,562,372 fetched on the run date, with no material issue in the last 30 days
- **THEN** the line shows 2.3% with the count, its period and its fetch date

#### Scenario: A stock dividend inside the settling window
- **WHEN** a stock-dividend issue of 26% has ex-rights date 2026-09-24 and the run date is 2026-10-12
- **THEN** the line shows "size not shown, because the share count is changing (issue on 2026-09-24)" and the checklist, and no percentage, even if the two vendor counts agree

#### Scenario: The same issue after the settling window
- **WHEN** the same issue is 31 days or more before the run date, the cached value was fetched after it, and the two counts agree
- **THEN** the size is shown

#### Scenario: An issue after the cached fetch
- **WHEN** a cached value is 4 days old and a 12.8% bonus has an ex-date after that fetch time
- **THEN** the size is not shown and the line names the issue date

#### Scenario: An employee issue is ignored
- **WHEN** an employee issue of 0.4% is dated 5 days before the run date
- **THEN** the size is not withheld for it

#### Scenario: A private placement counts
- **WHEN** a private placement of 6% with no ex-rights date was published 10 days before the run date
- **THEN** the size is not shown and the line names the publication date

#### Scenario: A placement of unknown size
- **WHEN** a non-employee issue stored with ratio 0.0 is dated 10 days before the run date
- **THEN** the size is not shown

#### Scenario: Disagreeing counts
- **WHEN** the two vendor counts disagree and no issue is in the window
- **THEN** the line says the vendor's two share counts disagree and gives the checklist

#### Scenario: The fallback is complete
- **WHEN** sizing is off
- **THEN** the line still names the counterparty, direction, quantity, window state and the range sentence, and gives the checklist

### Requirement: The size carries a benchmark with its stated basis, or none
When a size is shown, the line SHALL add a comparison with earlier registrations of the same direction, published before this one, with a stated quantity, in the comparable period, each measured against the share count at its own date: the vendor count divided by the cumulative factor of count-changing issues dated after that record. The comparable period SHALL begin at the latest stored issue event that changes the company's count by at least 1% (or has an unknown size and is not an employee issue) and is not covered by N2a's factor (a rights offer, a private placement, another class, or a bonus or stock dividend without an ex-date), or cover the whole stored history if there is none; employee issues under 1% SHALL be ignored. The sentence SHALL give the number compared and its first year, how many were larger than this one, the percentage of the largest of the others, and the basis ("Each is measured against the share count at its own date, estimated from today's count and the share issues with a ratio in the source."). With fewer than 5 comparable records it SHALL say no comparison is shown and how many there were. It SHALL NOT be shown when the size is not shown. The registration being described SHALL NOT be in its own comparison set.

#### Scenario: Comparison with an earlier bonus issue
- **WHEN** a fixture holds 14 earlier sell registrations with a quantity, one of them before a 100% bonus issue and larger than the current one against the count at its own date
- **THEN** the sentence says 1 was larger, gives the largest of the others, and states its basis

#### Scenario: Too few records
- **WHEN** only 3 comparable records exist
- **THEN** the line says no comparison is shown and that 3 were found

#### Scenario: A placement truncates the history
- **WHEN** a private placement of 6% is the latest issue not covered by the factor and only 1 record follows it
- **THEN** no comparison is shown

#### Scenario: The current record is excluded
- **WHEN** the current registration is also among the stored rows
- **THEN** it is not counted among the earlier ones

#### Scenario: No size, no benchmark
- **WHEN** the size is not shown because the count is changing
- **THEN** no benchmark sentence is printed

### Requirement: One Scheduled line, in the COMPANY block, lists dated events by the dates the source gives
The "Scheduled" part SHALL be the only Scheduled line in the brief; the DIVIDENDS block SHALL NOT print one. It SHALL list the scheduled cash-dividend ex-dates and count-changing share issues that the dividend lines provide, and meeting events (`AGME`, `EGME`) that have a non-null `record_date`, `exright_date` or `issue_date` after the last bar and within 7 calendar days of it, printing each meeting date with the source's field name and SHALL NOT state which of them is the meeting date. It SHALL end with "An announcement made after the last fetch is not shown." and SHALL read "none found" only after a successful fetch and "not checked" otherwise.

#### Scenario: A meeting with dates in the window
- **WHEN** a meeting event has a record date 3 days after the last bar
- **THEN** the line shows the record date with its field name and no meeting date claim

#### Scenario: A dividend ex-date is scheduled
- **WHEN** a cash dividend has an ex-date 4 days after the last bar
- **THEN** it appears once, on the COMPANY block's Scheduled line, and the DIVIDENDS block has no Scheduled line

#### Scenario: Nothing scheduled
- **WHEN** the source answered and nothing is dated in the window
- **THEN** the part reads "none found"

### Requirement: The footer names what makes a re-read worthwhile
The brief's footer SHALL read: "These would make a re-read worthwhile: a registered sale or purchase by a major shareholder or insider, a share issue or capital change, or one of your levels appearing or being reached. Other new announcements are listed for information. Re-run this brief to refresh." This SHALL replace the footer that mentions only the investor's levels and SHALL lift the clause that the brief has no announcement wording and no COMPANY block (both are clauses of the requirement "Fixed sentences, footer and the brief disclaimer are guarded" created by `add-weekly-holdings-brief`, which SHALL be modified accordingly when both are synced). The short brief disclaimer from `docs/DISCLAIMER.md` SHALL remain, and the other guards of that requirement SHALL continue to apply to the new footer and to every COMPANY constant.

#### Scenario: Footer text
- **WHEN** a brief is rendered
- **THEN** the footer is exactly the sentence above followed by the short brief disclaimer

#### Scenario: Footer contains no instruction word
- **WHEN** the Rule 6 guard runs over the footer
- **THEN** it passes without exemption

### Requirement: Small share issues are summarised on one quiet line, not listed
Share issue events below `ISSUE_MATERIAL_RATIO` (1%) SHALL NOT be listed individually. An issue SHALL be small when its ratio is known, above 0 and below 1% in any class, or when it is an employee issue with a missing or zero ratio. An issue of 1% or more, and a non-employee issue of unknown size, SHALL be material and listed. When at least one small issue falls within the listing rule's period and the source has been checked, the COMPANY block SHALL print one line at the end of "For information": "<n> small share issue(s), each under 1% of the shares (<classes>), not listed.", with the classes present named, and "each under 1% of the shares or of unstated size" when a counted issue has no stated ratio. The line SHALL carry counts and class names only, no title and no date, and SHALL NOT be printed when the count is 0 or the source was not checked.

#### Scenario: Employee issues are summarised
- **WHEN** three employee issues of 0.1%, 0.3% and 0.5% fall in the period
- **THEN** none is listed and the line reads "3 small share issue(s), each under 1% of the shares (employee issues), not listed."

#### Scenario: A material issue is listed
- **WHEN** a bonus issue of 10% falls in the period
- **THEN** it is listed under "Needs a look" and is not counted in the summary

#### Scenario: Unstated ratio
- **WHEN** an employee issue is stored with ratio 0.0
- **THEN** it is counted in the summary and the line says "or of unstated size"

#### Scenario: Nothing small
- **WHEN** no small issue is in the period
- **THEN** no summary line is printed

#### Scenario: Source not checked
- **WHEN** the source was never fetched
- **THEN** no summary line is printed and the parts read "not checked"

### Requirement: The re-read triggers line carries the announcement counts as further entries
The counts-only line `Re-read triggers this run: <label>: <n>[; <label>: <n>].` (requirement "The top of the brief warns of a provisional bar and counts re-read triggers", created by `add-weekly-holdings-brief`) SHALL be extended only by appending entries to its ordered list of trigger counts, after the investor's levels entry, without changing the line's format, position, zero rule or word guard and without a second triggers line. The entries SHALL be "registered sales or purchases by a major shareholder or insider since the last brief" and "share issues or capital changes since the last brief", each printed even at 0, counted over the held tickers as the items listed under "Needs a look" that are new since the last brief. Items listed again only because their window is still open, small share issues and additional-listing events SHALL NOT be counted. When announcements were not checked for k holdings (k above 0; a holding is not checked when its events were never fetched successfully or it has no stored price to date them against) a last entry "holdings whose announcements were not checked: <k>" SHALL be appended, and no parenthetical suffix SHALL be added by this change. Every label SHALL match the base pattern `[a-z' -]+` and SHALL pass the base line's banned-word check unchanged, which is whole-word and case-insensitive and is the base line's rule (its list: attention, important, urgent, alert, critical, should, must, review, action, act, risk, opportunity, recommend, consider). The labels SHALL be constants. No announcement count SHALL appear in the redacted copy, where the base line is absent.

#### Scenario: Counts
- **WHEN** one registered trade and no capital change are new for the held tickers and no level is reached
- **THEN** the line reads "Re-read triggers this run: your levels reached: 0; registered sales or purchases by a major shareholder or insider since the last brief: 1; share issues or capital changes since the last brief: 0."

#### Scenario: A listed-again item is not counted
- **WHEN** the only trade is listed again because its window is still open
- **THEN** its entry count is 0

#### Scenario: Small issues and listings are not counted
- **WHEN** the only new share events are employee issues below 1% and an additional-listing event
- **THEN** the capital-change entry is 0

#### Scenario: Not checked
- **WHEN** announcements were not checked for one of two holdings
- **THEN** the line ends with the entry "holdings whose announcements were not checked: 1" and no parenthetical is added

#### Scenario: All checked
- **WHEN** announcements were checked for every holding
- **THEN** the line has no "holdings whose announcements were not checked" entry

#### Scenario: Base format and word guard hold
- **WHEN** the line is rendered with the announcement entries
- **THEN** it matches the base line's pattern, none of the banned words appears in it, and the base line's guard test passes unchanged

#### Scenario: Redacted copy
- **WHEN** the redacted brief is rendered
- **THEN** it has no triggers line and no announcement count

### Requirement: A redacted copy keeps the COMPANY block without third-party text and without anything derived from the issued log or the holdings
The COMPANY block SHALL appear in the redacted copy because nothing in it derives from the investor's holdings: its source-health lines, tags, trade lines, share count, size, benchmark and Scheduled line come from the feed, the stored bars and the vendor. The redacted copy goes to a language model, and a stored title or counterparty name is third-party text that can carry instructions, so the redacted copy SHALL show no title and no counterparty name: each item SHALL keep its date, tag, window state, quantity, size and the read-the-notice fallback, SHALL say that the title and name are not shown in the redacted copy, and the trade line SHALL read "A notice of a sale | purchase of <quantity> <TICKER> shares was filed (...)" without a name. Titles and names remain in the full copy, sanitised, quoted and labelled (owner decision 15, relayed 2026-10-13). What the issued-brief log decides SHALL NOT appear in the redacted copy: it SHALL list announcements from the 14 calendar days before the last bar, SHALL NOT say "since the last brief" or that it lists the last 14 days because there is no previous brief, and SHALL NOT mark an item "listed again" for being older than the previous brief (an open window still keeps an insider trade listed). The size lines of the redacted copy SHALL NOT depend on the issued log: the share count SHALL be resolved when either copy would list a trade with a stated quantity. No investor-entered value, no share count held and no level SHALL appear in the block in either copy.

#### Scenario: Log-derived wording is absent
- **WHEN** the redacted brief is rendered for a ticker that has an earlier issued brief and for one that has none
- **THEN** the COMPANY blocks are the same except for what the feed itself changes, and neither says "since the last brief" or "first brief"

#### Scenario: No third-party text in the redacted copy
- **WHEN** the redacted brief is rendered for a registration whose counterparty name and a news title read like instructions
- **THEN** neither the name nor the title appears, no U+201C or U+201D appears, and the date, tag, window state, quantity and the fallback sentence do

#### Scenario: The full copy keeps them
- **WHEN** the same brief is rendered unredacted
- **THEN** the name and the title appear sanitised inside quotes under the third-party label

#### Scenario: No holdings value reaches the block
- **WHEN** the redacted and the full brief are rendered for a holding with distinctive shares, cost and level values
- **THEN** none of those values appears in the COMPANY block, and every number in the redacted COMPANY block is in an allow-list built from the announcements, the share count and the fixed sentences

#### Scenario: The size does not reveal the log
- **WHEN** a trade is inside the redacted copy's 14 days but not listed by the full copy after an earlier brief
- **THEN** the share count is still resolved and the redacted size line is identical with and without an earlier brief

### Requirement: The change's tests use synthetic rows and never the network or real holdings
Tests for the COMPANY block, the trade line, sizing and the benchmark SHALL use fixtures of synthetic rows shaped like stored ones (fictional tickers and counterparties, stored title patterns, stored field names), SHALL inject the adapter output, the cache path and the vendor fetch function, SHALL make no network call, and SHALL read neither the real holdings file nor `backend/data/app.db` nor real stored titles. The fixtures SHALL include a record published after its window, a title with no quantity, several filers on one date, a placement with ratio 0 and a count that disagrees between the two vendor fields.

#### Scenario: Offline run
- **WHEN** the new tests run with the network blocked
- **THEN** they pass and open no database under `backend/data/`

#### Scenario: Fixtures carry no real data
- **WHEN** the fixtures are scanned
- **THEN** they contain no real holding, no real counterparty name and no title copied from the stored feed
