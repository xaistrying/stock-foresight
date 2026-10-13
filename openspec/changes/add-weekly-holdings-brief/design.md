## Context

The v5.3 brief (Appendix K of `docs/DISCUSSION_purpose_and_weekly_brief.md`) is the template; the status record and the "N1 and N2 shaping session" at the end of that file say which parts belong here. This change builds the parts that need only data already in the repo: stored OHLCV, the HAR-RV range from `compute_range`, the holdings the owner types, and a log of what earlier briefs said. Everything about dividends, announcements and share counts after an issue is N2a, N2b and N3.

What the code gives us today (read 2026-10-12):

- `compute_range(ticker)` (`backend/app/services/range.py`) returns a frozen `RangeResult` with status `ok | uncalibrated | ineligible | range_out_of_bounds | model_unavailable`. It raises `TickerNotLoaded` for a ticker with no rows. `range_5s_pct` is the half-width of the typical 5-session move in percent; the model is fitted so the band contains `|ln(close[t+5]/close[t])| × 100` with `range_coverage` (0.68). `coverage_phrase(c)` returns "about 2 in 3" or "about N%". `uncalibrated` has a band but `range_coverage` is `None`.
- `read_recent_closes(ticker, limit)` (`app/ml/volatility.py`) returns dates and positive closes, ascending, from `ohlcv`. Closes are stored in thousand VND (SAB 42.90) and, for SAB, are dividend-adjusted back in time (measured 2026-10-11).
- `load_ticker(ticker)` refetches the full history and upserts every fetched row (`ON CONFLICT DO UPDATE`), so a refresh can re-adjust old rows. It catches `RateLimitError`, but vnai's limiter `sys.exit`s, so `bulk_ingestion._is_rate_limit_exit` exists to recognise that `SystemExit`.
- `snapshot_company_feed.py` is the layout to copy: a long docstring, a thin `main(argv)`, logic in a package.
- `test_company_feed_isolation.py` fails if any module under `app/` outside the feed package contains the substring `company_feed`, and if any non-test file outside it imports it. **The brief package must therefore not mention the feed at all, not even in a comment**, until N2a amends that test.
- `docs/DISCLAIMER.md` has a "Brief version" section (the `domain-rules` spec calls it the "Brief disclaimer" section; same text, see Open Questions). The copy this change creates needs its own guard test.

Constraints: Rules 1 to 6 (honored as listed in `proposal.md`); `backend/data/app.db` is rebuildable, pytest's `TestClient` lifespan runs against the real file, and the API has no auth, so holdings can never live there. The venv is Python 3.14 (`tomllib` is in the standard library). No new dependency.

## Goals / Non-Goals

**Goals:**
- A weekly brief for a handful of holdings: honest on every failure path (refresh failed, no model, ineligible, out of bounds, uncalibrated), private by construction (holdings outside the repo, never in a DB or the API, a redacted copy that cannot leak), and extensible by later changes without rewriting this one.
- Guards in tests for each promise the specs make about text and imports.

**Non-Goals:**
- Dividends, ex-dates, share issues, the net line, announcements, the recompute fallback, foreign flow, verdict, model text, Fibonacci, 52-week levels, yield, tax and fees, scoreboard, frontend, a scheduler, an HTML or PDF output.
- Narrowing `TRANSACTION_VERBS` (see D12).
- Any change to a domain rule, an existing spec, `docs/`, or the company feed.

## Decisions

### D1. A thin script over a package of small modules, sections are pure functions

`backend/scripts/weekly_brief.py` parses arguments and calls `app.services.brief.run`. Modules (each aimed at 200 to 400 lines, the soft ceiling is 800), all dataclasses `@dataclass(frozen=True)`, tuples not lists:

| Module | Holds |
|---|---|
| `holdings.py` | `Level`, `Holding`; `load_holdings(path, *, repo_root)`; default path; permission, owner and location refusals; validation |
| `issued_log.py` | `IssuedEntry`; tolerant JSONL read; append with mode 600 |
| `refresh.py` | `refresh_tickers(...)` wrapping `load_ticker`, pacing, outcome per ticker |
| `facts.py` | `MarketFacts` (everything derived from prices and the model) and `LevelCheck`; `gather_market_facts(...)` |
| `week.py`, `levels.py` | pure functions: the week just ended and inside/outside; level reached / not reached and distance; re-adjusted-close detector |
| `wording.py` | every fixed sentence, plain wording for each status and reason, `coverage_sentence`, number formatters, `BRIEF_DISCLAIMER`, `disclaimer_for(range_coverage)` |
| `sections_market.py` | header, per-ticker header, close line, THE WEEK JUST ENDED, NEXT 5 TRADING DAYS, notes; take `MarketFacts` only |
| `sections_holding.py` | position block, YOUR LEVELS, HOLDINGS LISTED; take a `Holding` and `MarketFacts` |
| `compose.py` | the ordered section list; `build_brief(reports, *, redact, now)` returns a `tuple[str, ...]` of lines |
| `run.py` | orchestration (D3) and `RunResult` |

Each section is `def section(...) -> tuple[str, ...]`. `compose` holds an ordered tuple of section functions; N2a inserts DIVIDENDS and the ex-date lines, N3 inserts COMPANY, each by adding a module and one entry. Nothing in N1 is rewritten for that. The package `__init__.py` is a one-line comment, so importing one module does not drag in the rest.

*Alternative: one 800-line module, or sections as methods on a report class.* Rejected: the file-size rule, and pure functions over frozen data are what the tests and the later changes need.

### D2. Holdings file: TOML outside the repo, refused unless private

Default path: `<config dir>/stock-foresight/holdings.toml`, where `<config dir>` is `XDG_CONFIG_HOME` if set, else `~/.config`. `--holdings PATH` overrides. Hypothetical example (the real file is the owner's and is never read by a test):

```toml
[[holdings]]
ticker = "AAA"
shares = 1000
shares_as_of = 2025-06-10      # optional; defaults to purchase_date
cost = 41.80                   # per share, thousand VND, as on the board
purchase_date = 2025-06-10     # optional ("not entered")

  [[holdings.levels]]
  comparator = "below"         # or "above"
  price = 41.60                # thousand VND
  entered = 2026-10-02
  text = "Trim 300 shares if the close is below 41.60"
```

Validation (a `HoldingsError` with a message naming the entry and field, never the value of `shares` or `cost`): `ticker` matches `[A-Z0-9]{1,12}` (the same rule as the feed's parser; a test keeps them equal without the brief importing the feed); `shares` a positive integer; `cost` a positive number; dates are TOML dates or ISO strings, not in the future; `comparator` one of `below`, `above`; `price` positive; `text` non-empty, at most 300 characters, one line (control characters rejected); no duplicate tickers; at least one holding. A level needs all four fields.

Refusals, all before any vendor call: file missing (the message names the expected path and nothing else); not a regular file; owned by another user; any group or world permission bit set (`mode & 0o077`); resolved path inside the repository root. A group- or world-accessible parent directory is a warning on stderr, not a refusal. `weekly_brief.py` creates the log directory with mode 700 when it creates it.

*Alternatives:* a `holdings` table in `app.db` (rejected: rebuildable, the pytest lifespan runs against the real file, the API is unauthenticated); an environment variable (rejected: leaks to child processes and shell history); JSON or YAML (rejected: `tomllib` is stdlib, TOML has dates and comments); CSV (rejected: levels are nested).

**`.gitignore`.** Three narrow patterns: `holdings*.toml`, `holdings*.jsonl`, `holdings*.json` (the last also covers the share-count cache `holdings_share_counts.json` that N3 adds). A bare `holdings*` was rejected because it would silently untrack any source file whose name starts with `holdings` (such as the module `holdings.py`). A test runs `git check-ignore` over every file this change adds under the package, scripts and tests and fails if any is ignored, so the patterns cannot start hiding code later.

On WSL, a holdings file on a Windows drive (`/mnt/c`) reports mode 777 and will be refused; keep it on the Linux filesystem. Stated in the script docstring.

### D3. Run order

1. Parse arguments; load and validate holdings (D2); refuse early.
2. Read the issued-brief log (D5). A missing file is the first-brief case; unparseable lines are skipped and counted.
3. Load the model once; if loaded, check `BRIEF_DISCLAIMER` against its coverage (D9). A mismatch aborts with exit 1 **before** any vendor call.
4. Refresh every held ticker (D4), unless `--no-refresh`.
5. Per holding, gather `MarketFacts` inside a `try`: any exception becomes a degraded holding, never a missing one (D6).
6. Render with `compose.build_brief(..., redact=args.redact)`.
7. Print to stdout, or write to `--out` (D10).
8. Append one log entry per holding (D5). If this fails after the brief was shown, print the failure on stderr and exit 1: a brief that is not logged breaks next week's comparison and the owner must know.

Exit codes: 0 brief produced (degraded holdings are described in the text, they do not change the code); 1 a refusal or write failure; 2 usage error. Mirrors `snapshot_company_feed.py` where it can.

Options: `--holdings PATH`, `--redact`, `--out PATH`, `--no-refresh`. `--no-refresh` exists so a redacted copy can be made after the real run without a second vendor call and a second round of vnai analytics on the held tickers.

### D4. Refresh wrapper

`refresh_tickers(tickers, *, loader=load_ticker, sleep=time.sleep)` calls the loader once per ticker and returns a frozen `RefreshOutcome(ticker, state, detail)` with state `ok | failed | not_attempted`:

- the loader returns status `ok`: `ok`. Any other returned status (`rate_limited`, `no_data`, `invalid_symbol`): `failed`.
- `SystemExit` for which `_is_rate_limit_exit` is true: `failed`, and every later ticker is `not_attempted` ("vendor limit reached earlier in this run"). The limiter has already ended one call; more calls in the same minute only repeat it. No retry or wait: the owner re-runs.
- `SystemExit` for any other reason is re-raised (a genuine exit must stay honoured; same reasoning as `bulk_ingestion`).
- any other `Exception`: `failed`, `detail` is the exception class name only.
- beyond the first ticker, calls are spaced by `60 / DEFAULT_SYMBOLS_PER_MINUTE` seconds, the constant `bulk_ingestion` already uses, so a long holdings file does not hit the limiter it was written to survive.

`_is_rate_limit_exit` is imported from `bulk_ingestion` (a private name, used rather than copied so the two cannot drift; a test asserts the wrapper's decision equals the function's). A failed or skipped refresh does not stop the run: the holding is computed from stored prices and shown as "refresh failed; last bar <date>" (or "no stored prices") with a per-holding stale warning. Tests pass fake loaders; none reaches the vendor.

Staleness, per holding: its last bar is earlier than the newest last bar among all holdings, or more than 5 calendar days before the run date. There is no trading calendar in the repo (`macro.py` says so), so the 5 calendar days is a stated heuristic and a long public holiday can raise a false warning; the line says "calendar days". Provisional bar: a holding's bar is provisional when its last bar is today's date (ICT, UTC+7) and the time is before 15:15 ICT; the consequences are in D16. 15:15 is the time the review gave for end-of-day values (mid-session values read -9% against -24% final); VPB 2026-10-05 has two logged closes (22.90, 23.00) consistent with a pre-close run. Vietnam has no daylight saving, so a fixed UTC+7 offset is used and no tz database is needed.

### D5. Issued-brief log

`holdings_issued.jsonl` beside the holdings file (its name starts with `holdings`, so the `.gitignore` line covers it if it is ever copied into the repo). One JSON object per line, appended per holding per run, written with a single `os.write` on a descriptor opened `O_APPEND | O_CREAT | O_WRONLY`, mode 600, then `fsync`:

```
{"schema": 1, "issued_at": "<UTC ISO>", "ticker", "as_of": "<last bar date>", "close": <issued close>, "provisional": <bool>,
 "status": "<range status or no_prices|error>", "band_pct": <half-width or null>, "band_lo": <VND, thousands, or null>,
 "band_hi": ..., "calibrated": <bool|null>, "model_version": "<str|null>", "refreshed": <bool>,
 "levels": [{"comparator", "price", "entered", "text", "reached": <bool|null>, "distance_pct": <num|null>}]}
```

It does not record shares, cost or purchase date; they are not needed to compare ranges. It does record level prices and text (they are "levels as checked"), so it has the same permissions as the holdings file. The reader ignores unknown keys (N2a and N3 will add some) and skips a line that is not valid JSON or lacks a required key, with a count on stderr; it never raises into the brief.

**Last week's range.** The week just ended is the last 5 stored sessions: `dates[-5] .. dates[-1]`, and the range that covered it was issued on the bar 5 sessions before, `d0 = dates[-6]`. The lookup is an exact match on `as_of == d0` and takes the latest entry for that date (a same-day re-run after the final close supersedes a pre-close run). Outcomes, each with its own sentence:

| Log state | Sentence |
|---|---|
| no entry at all for the ticker | "first brief: no previous range" |
| entries exist, none with `as_of == d0` | "no range was issued for the week starting after <d0>; the latest one on file is for <date>" |
| entry with a null band | "last week's brief gave no range (<plain status wording>)" |
| entry with a band | "Last week's range was ±<b>% (<lo> to <hi>): the close was inside | outside it" |

Inside means `|ln(close[-1]/close[-6])| × 100 <= band_pct`, computed from **stored** closes at both ends, i.e. in adjusted return space (Rule 1: the measure the band is fitted to). A constant rescale of earlier closes cannot change a log return, so a dividend or share issue after the range was issued does not change the verdict (measured 2026-10-12: 6 ticker and date pairs reproduced to two decimals). The cost of this choice, measured on SAB ex 2026-07-28: the window containing the ex-date read -1.30% (inside) in adjusted terms while the board showed -7.65% (outside). N1 cannot see ex-dates, so it states the limit in one fixed sentence under the week line ("Compared on stored prices, which may be adjusted for dividends and share issues; this version does not say whether one fell in the week."). N2a adds the authoritative ex-date note and the week-1 recompute fallback; N1 never recomputes a past range.

*Alternative: no log, recompute last week's band from today's prices.* Rejected by the owner for N1: recompute is percent-only and, for the VND range, wrong after an ex-date (6.4% lower for SAB). It is in N2a, labelled "recomputed today ... not an issued range" and never written to this log.

### D6. Every non-ok status has plain wording; a holding never vanishes

`wording.status_lines(facts)` is total over the statuses and over the reason codes `assess_eligibility` can emit (`delisted`, `insufficient_history`, `stale`, `near_gap`, `hard_quality_flag`; an unknown code prints as "unrecognised reason `<code>`"). The holding block, the log entry and HOLDINGS LISTED exist for every holding whatever happens:

| Condition | Block shows |
|---|---|
| `ok` | band, VND range, the coverage sentence from `coverage_phrase` |
| `uncalibrated` | band and VND range; instead of the coverage sentence: "How often a range like this holds has not been measured for <TICKER>: it is outside the set the range was calibrated on." (Rule 4) |
| `ineligible` | "No range this week: <reason in plain words>." one clause per reason; close and position still shown from stored prices |
| `model_unavailable` | "No range this week: the volatility model file is missing or unusable." |
| `range_out_of_bounds` | "No range this week: recent prices look abnormal, so the range is withheld rather than shown." (no sigma figure) |
| `TickerNotLoaded` or no stored bars | "No stored prices for <TICKER>." plus the refresh outcome |
| any other exception while gathering | "This holding could not be computed (<exception class>); see the log." and the error is logged with `logging` |

A non-ok holding has no band, so it is left out of the upper-bound figure of HOLDINGS LISTED, and the sentence says how many were left out.

### D7. Band edges in VND, and units

Prices are shown as stored, thousand VND per share, with one fixed line "Prices are per share in thousand VND." Amounts on the shares are in millions of VND: `shares × price / 1000`. The range edges are `close × exp(∓band_pct/100)`, the exact image of the inside/outside test, so the printed edges and the verdict cannot disagree. The figure printed beside them, "±b%", is the band's own half-width as the product already shows it elsewhere; the edges differ from `close × (1 ∓ b/100)` by about `b²/200` points (0.04 at 2.7%) and an arithmetic check against the printed percent can differ in the second decimal. This is stated here and in the auditor re-read task, because the v5.3 examples were written with the simple form. The label is "Usual range (typical 5-session move)": the `volatility-range` spec names "typical 5-session move" as the label wherever the band is shown, and Appendix K calls it the usual range; both appear. `sigma_daily_pct` is never shown.

### D8. Levels (Rules 5 and 6)

A level is checked against the **last stored close** (the brief does not say Friday; the investor's own text may). `below`: reached iff `close < price`; `above`: reached iff `close > price` (strict; equal is not reached). Distance is `|close − price| / close × 100`, one decimal. The tool's words are exactly:

- reached: `<verbatim text> (you wrote this on <entered>): REACHED. The last close, <close>, is <below|above> it, by <d>%.`
- not reached: `<verbatim text> (you wrote this on <entered>): not reached; the level <price> is <d>% <below|above> the close.`

Under a heading line `YOUR LEVELS (you wrote these; the brief only checks them against the close)`, and the closing sentence "This brief does not place orders; what you do is your decision." The level price is printed in the tool's words so a mismatch between the investor's text and the structured fields is visible rather than silent. The text is printed after control characters are replaced and with no markdown escaping beyond that. No level, or no close: "none set" or "not checked: no stored close", still listing each text. The tool adds no word about direction, no instruction and no "approaching" wording; there is no threshold the tool picked (Rule 3).

### D9. Coverage sentence and disclaimer, derived and guarded

`coverage_sentence(range_coverage)` builds on `coverage_phrase`: for "about 2 in 3" it returns "About 2 weeks in 3 stay inside a range like this; about 1 in 3 is bigger, up or down."; for any other level it returns "<phrase> of weeks stay inside a range like this; the rest are bigger, up or down." with the phrase capitalised. It is never typed independently.

`BRIEF_DISCLAIMER` is a verbatim copy of the "Brief version" blockquote and contains the fixed words "About 2 weeks in 3". Three guards: (1) a test reads `docs/DISCLAIMER.md`, takes the blockquote under "## Brief version", normalises whitespace (the existing tests' rule: blockquote lines joined with one space) and requires equality; (2) a test loads the real `har_rv_model.json` through `load_model` and requires `coverage_phrase(model.range_coverage) == "about 2 in 3"` whenever the copy says "2 weeks in 3", so a retrain at another level fails the build; (3) at run time `disclaimer_for(range_coverage)` raises `DisclaimerCoverageMismatch` when the loaded model's coverage is not 0.68 and the run aborts before any vendor call, never printing a sentence that disagrees with the range. If the model cannot be loaded no range is shown; the disclaimer is still printed unchanged.

### D10. Output, and where the brief may be written

Default is stdout. `--out PATH` writes a file with mode 600 and refuses any path inside the repository's `reports/` directory (that folder is built for NotebookLM upload) and, for an unredacted brief, any path inside the repository at all. A redacted brief may go anywhere outside `reports/`. The brief is never written by default and never sent anywhere.

### D11. `--redact`: safe by construction, then tested

Two layers. **Construction:** `sections_market.py` receives only `MarketFacts` and never imports `Holding` or `Level`; `sections_holding.py` is not called in redacted mode, and `compose` substitutes fixed lines. A test scans `sections_market.py` for the names `shares`, `cost`, `purchase`, `Holding` and `Level` and fails on any. **Behaviour:** a leakage test builds hypothetical holdings with distinctive numbers, renders the redacted brief, and fails if the output contains any holdings field in any common format (thousands separators, with and without decimals, as millions), the gain or loss percent, any level price, text or entry date, any weight, the upper-bound figure, or any number token that is not in an allow-list built from the market facts and the fixed sentences. The allow-list is the point of the test: it fails on a *new* number nobody thought about. It also checks the specific inference route named in review: gain percent plus the close would reveal cost, and a level's distance plus the close would reveal the level, so neither appears.

Two section-level consequences: the per-ticker header has two forms (`--- SAB ---` from `sections_market`; with shares, cost and purchase date from `sections_holding`), and the range block's "On your <shares> shares: about ±<amount>M VND" sentence is a separate line from `sections_holding`, so the market range lines never need shares.

Kept (market data, derivable by anyone): tickers, close (with its "(provisional)" mark) and the provisional warning, last-bar dates, week move and its two closes, last week's issued range and verdict, the range in percent and VND per share, status wording, refresh and staleness notes, the re-adjusted-close note (without its levels sentence), the fixed sentences and the disclaimer. Dropped: the triggers line (its count is derived from the investor's levels), shares, `shares_as_of`, cost, purchase date, value, gain or loss in VND and percent, the amount on the shares, weights, the upper-bound figure, everything in YOUR LEVELS including the investor's text, and the as-entered note. The redacted copy says so in one fixed line under the title, and YOUR LEVELS becomes one fixed line ("not shown in the redacted copy"), printed whether or not levels exist, so the line itself reveals nothing. The issued log is not part of the output. Redaction limits what is *handed over*; once an agent reads a file its contents are in a model's context (Appendix L), which is why the three agents are pointed only at redacted briefs.

### D12. Guards over the brief's text and imports

- **Verb guard.** `test_brief_text_guard.py` renders the full and redacted brief across a matrix (every status in D6, a reached and a not-reached level, a failed refresh, first brief and not-first brief, one and several holdings, a provisional run, the triggers line at 0 and above 0), removes every investor-written string (level texts) from the output, and requires `\b(buy|sell|hold)\b` (case-insensitive) to match nowhere, and also scans the fixed-sentence constants in `wording.py`. The test's own level texts contain the three words so that the strip-first step is exercised: with the strip removed the test must fail (a mutation check inside the test). `TRANSACTION_VERBS` in `test_debate_export_api.py` is **not narrowed**: its only user is that test, which never sees the brief, and it is deleted with the debate export by C1 (`retire-debate-engine-and-verdict-ui`). The shaping session asked to "confirm when writing the proposal": confirmed by reading the test on 2026-10-12.
- **Import guard.** A subprocess (`python -I`, so a clean `sys.modules`) imports `app.services.brief.run` and the script module and fails if any of `anthropic`, `openai`, `google.generativeai`, `claude_agent_sdk`, `app.services.debate.llm_client`, `.engine`, `.runner`, `.synthesiser` or `.news` is loaded. `httpx` is allowed: `compute_range`'s eligibility chain reaches `news_feeds` (httpx and defusedxml only) and that is not a model client. A second, static check reads the package sources and fails on those names.
- **Holdings guards.** Tests that the default path is outside the repo, that a path inside it is refused, that mode 644, 640 and 604 are refused and 600 and 400 accepted, that no brief module references `sqlite3`/`get_connection` for holdings, that no route under `app.routes` mentions holdings or the brief, that `git check-ignore` ignores `holdings.toml` and `holdings_issued.jsonl` at the repo root and at `backend/`, and the new-files-not-ignored check from D2.
- **Isolation guard.** An autouse fixture in the brief tests points `app.db.connection.DB_PATH` at a temporary file and replaces `load_ticker` with a function that fails the test if called unexpectedly, so a forgotten injection cannot touch the real `app.db` or the vendor. Tests build temporary OHLCV databases the way `test_range_api.py` does.

### D13. Re-adjusted prices versus levels (best effort)

A refresh rewrites every fetched row, so after a dividend or share issue the stored history sits below what an earlier brief printed. The detector compares the close printed in the most recent earlier log entry for the ticker (`close` for date `as_of`) with the stored close for that same date now, if that date is in the stored window. If they differ by more than 0.005 (half the displayed price unit; a quantisation tolerance, not a move threshold) the brief prints: "NOTE: the close stored for <date> is now <x>; the brief issued then showed <y>. Stored prices may have been re-adjusted (for example after a dividend or share issue)." and, when the holding has levels and the copy is not redacted, "Levels you set looking at the earlier price may be on the old price basis." (a separate line produced by `sections_holding`, because the note itself is market data). Its limits are stated in the design and in one fixed clause in the note: it only sees an adjustment that has reached the stored prices, and the vendor's adjustment lag is not verified, so it cannot promise a level is safe when it is silent. It also fires for a provisional versus final close on the same date, which is the right warning. N2a adds the authoritative note from the feed's ex-date.

### D14. HOLDINGS LISTED

Shown only when the holdings file has two or more entries. Weight is each holding's value over the total value of holdings that have a close, to the whole percent. The upper-bound figure is `Σ weight × band_pct` over holdings that have a band, to one decimal. Wording (Appendix K's, with one clause added because 1 week in 3 is bigger than the range): "If every holding moved to the edge of its own range in the same direction, the listed holdings would move about <y>% (an upper bound for the usual ranges, not a forecast; larger moves are possible)." plus "<k> listed holdings have no range and are left out of this figure." when k > 0. Everything in this block is holdings-derived and is absent from the redacted copy.

### D16. The top of the brief: provisional warning, then a counts-only triggers line

*Owner decisions 4 and 5, 2026-10-12.* Simulated-investor reviews found all five simulated readers skimming past warnings. That is a **hypothesis, not evidence**: the readers are the same model family as the author playing caricatures, so the change adds the visibility and the 4-week real use is what can test it.

**Order of the first lines:** (1) the title line; (2) when any holding's bar is provisional, `PROVISIONAL_WARNING`: "WARNING: today's bar is provisional. The market may still be open, so the closes, ranges and week moves below can change after the close. Run this brief again after the close."; (3) the triggers line; (4) the refresh and last-bar line; (5) the units line; (6) the fixed header sentences. The run is never refused: a provisional run produces the brief, writes its log entries (marked `provisional: true`) and exits 0. In the position line the close reads `Close 42.90 (2026-10-09, provisional)`; the mark is market data and stays in the redacted copy, with the warning. A later same-day run after 15:15 supersedes it through the "latest entry for the date" rule (D5); if the provisional entry is the one used for the next brief's "last week's range", the week sentence appends "(that range was issued from a provisional bar)".

**Triggers line.** `Re-read triggers this run: <label>: <n>[; <label>: <n>].` It is assembled by `compose` from an ordered tuple of `TriggerCount(label, count)` values, so each later change adds its own count without rewriting the line. N1 supplies one: label "your levels reached", count = the number of the investor's levels, across all holdings, that were checked and reached. It is printed even at 0 ("Re-read triggers this run: your levels reached: 0."). It counts only items that the footer already names as re-read triggers; it contains no judgement ("needs attention", "important" and the like), no direction word and no instruction, and the number is a count, not a rank. If levels exist that could not be checked (no stored close) the line appends " (<m> levels could not be checked: no stored close)" so a 0 is not read as "nothing to check"; the facts are in YOUR LEVELS.

**Extension point for N3:** N3 adds its announcement count by appending one `TriggerCount` (for example "registered insider or major-shareholder trades") to the ordered tuple in `compose`; the line's format, position, zero rule and word guard are not edited. Announcement counts are market data, so N3 decides whether they appear in the redacted copy; the levels count is derived from the investor's levels and is **dropped from the redacted copy** (the whole line is absent there, and the redacted-copy notice already says levels are not included). If N3 wants an announcement-only line in the redacted copy it adds its own line.

**Guard.** A test requires the line to match `^Re-read triggers this run: [a-z' -]+: \d+( \(.*\))?(; [a-z' -]+: \d+)*\.$` and fails if it contains any of these **whole words**, matched case-insensitively with `\b(...)\b` and never as substrings: attention, important, urgent, alert, critical, should, must, review, action, act, risk, opportunity, recommend, consider. "Re-read", "exact" and "contact" pass; "act" and "Review" fail (a unit test of the guard itself covers both directions). It is also in the buy/sell/hold matrix (D12), with the provisional run added to the matrix.

### D15. Fixed text

All fixed sentences live in `wording.py` as module constants, so the guards in D12 can scan them: header "This brief does not update during the week. It does not predict direction."; the units line; the week-compare limit; the first-brief sentence; the footer "One of your levels appearing or being reached would make a re-read worthwhile. Re-run this brief to refresh." (no announcement wording until N3); the disclaimer; `PROVISIONAL_WARNING`; the triggers-line prefix "Re-read triggers this run:" and the label "your levels reached". The optional "biggest weekly fall or rise" line does not exist.

## Risks / Trade-offs

- **The band may be no better than a trailing standard deviation** (HAR out-of-time correlation 0.431 against 0.424 for `log(rv20)`) → the brief uses the existing, calibrated range because it exists, not because it is special; E1 tests it and kill criterion 2 in `proposal.md` stops the work if it fails.
- **Same-model blind spots**: every wording choice was read only by simulated readers → the 3-question real-people check is still open; the brief makes no claim beyond its inputs and N1 starts the 4-week clock that supplies real evidence.
- **Adjusted-space verdict can say "inside" for a week the broker shows as a big fall** (SAB ex 2026-07-28) → the limit is printed under the week line; N2a adds the ex-date note.
- **A holdings file with permissions the OS cannot express (drvfs)** is refused → the message says where to put it. A refusal is the safe failure.
- **Vendor analytics** (vnai posts tickers and a fingerprint, per the review's reading, untested) → the held set is visible to the vendor on every refresh; `--no-refresh` avoids a second call for the redacted copy. Not mitigated beyond that; stated in `proposal.md`.
- **Provisional close** when run before 15:15 UTC+7 → a header warning and the same-date supersede rule in D5; the 15:15 figure is the review's, not a verified exchange rule.
- **Level text and fields can disagree** → the tool prints the field price in its own words (D8); it does not parse free text.
- **Narrow ignore patterns miss a differently named holdings file** (for example `my-positions.txt` placed in the repo) → the loader refuses any holdings path inside the repository, so the ignore lines are a backstop for copies, not the control.
- **Readers skim past warnings** (simulated readers only; a hypothesis) → the provisional warning is the first line after the title and the close is marked in the position line; whether it helps is for the 4 weeks of real use.
- **Holdings typed into this session, an IDE or agent memory leave the machine whatever the code does** → proposal and tasks use hypothetical holdings only; the owner types the real file themselves.
- **Brief package mentions the feed** → would fail `test_company_feed_isolation.py`; a static test in the brief tests forbids the substring until N2a.

## Migration Plan

Additive. No schema change, no data migration. Rollback is deleting the new files and the one `.gitignore` line; nothing else reads them. The owner creates the real holdings file by hand (mode 600, directory 700) outside the repo; the log is created by the first run. The first real run is week 1 of the 4-week check.

Ordering: **N1 (this change) applies first.** N2a (`add-dividend-and-ex-date-lines`) and N3 (`add-announcement-tags-and-insider-sizing`) build on `compose`, the section modules, the log schema and the holdings fields; N2a also amends the company-feed spec and its isolation test to allow one adapter file in the brief package, and supplies the week-1 recompute fallback; N3 depends on N1 and N2a's count-changing-issue rule, not on N2b. E1 (`evaluate-band-against-trailing-stdev`) is independent of all of them. C1 and C2 wait for the 4-week check.

## Owner decisions 2026-10-12

Recorded as given; each closes the matching open question below.

1. **Personal-use premise confirmed.** The owner states that this project is used by the owner themself and is not commercial. It is the owner's statement, not verified by the tool. Rule 6 is kept as it is: no rule text is edited. If anyone else will use or receive the output, Rule 6 still requires restoring the old rule or obtaining sign-off first, and the vendor licence ("personal, research, non-commercial") and the company-feed log's "not to be shared" note stay as stated. This is a factual record, not legal advice.
2. **`.gitignore`**: `holdings*.toml`, `holdings*.jsonl`, `holdings*.json` instead of `holdings*` (D2); the check-ignore test over every new file stays.
3. **Accepted as written**: VND edges `close × exp(∓band/100)`; label "Usual range (typical 5-session move)"; the fixed line "Prices are per share in thousand VND."; `cost` required; `--no-refresh`; a redacted run still appends to the issued log; strict inequality for levels and "last close"; staleness of 5 calendar days; the provisional-bar warning before 15:15 ICT.
4. **Provisional run (D16)**: warning at the top, close marked "(provisional)", never refuse. Stated there as a hypothesis from simulated readers, not evidence.
5. **Triggers line (D16)**: counts only, no judgement words, present at 0, dropped from the redacted copy, extended by N3 through one `TriggerCount`.
6. **No domain-rule text is edited** by any of this.
7. **Triggers-line banned words**: the list in D16 plus "recommend" and "consider", matched as whole words, case-insensitively, never as substrings ("exact" and "contact" pass; "re-read" is allowed).
8. **Levels that could not be checked**: the triggers line appends their count with the reason, so a 0 is not read as "all checked".
9. **Upper-bound sentence** for several holdings keeps "for the usual ranges … larger moves are possible" as written in D14.
10. **Heading name**: `docs/DISCLAIMER.md`'s heading "## Brief version" is authoritative and the guard test reads it. The `domain-rules` spec calls the section "Brief disclaimer"; this change does not edit that spec, and its wording will be aligned by a separate small task (a spec wording fix outside this change).
11. **Provisional marking and provisional log entries** are accepted as written: provisional is per holding (last bar is today's date and the time is before 15:15 ICT); a provisional entry is logged with `provisional: true` and is superseded by a later post-close run (the later entry for a date wins); if only a provisional entry exists for a date, next week's comparison uses it and says so.

## Open Questions

None open. Every question raised in this design was answered by the owner on 2026-10-12 (see "Owner decisions 2026-10-12"). The one follow-up outside this change is the small spec-wording task in decision 10.

Not verified: the vendor's adjustment lag after an ex-date (the D13 detector depends on it); that stored closes are in thousand VND for every ticker (checked on SAB only); how vnai's analytics behaves on a held-ticker refresh; file-mode behaviour on non-Linux filesystems; that 15:15 ICT is after the final close on every session (from the review, not an exchange rule).

## Review fixes 2026-10-12

A Python review (one blocking finding) and a security review (two high, six medium) read the first implementation. The items below change behaviour; where they contradict the decisions D2, D4, D5, D10, D11, D12, D14 or D16 above, **this section wins**. The spec scenarios and `tasks.md` (section 12) were updated to match.

**Correctness**
- **Same-bar re-run (was a bug).** The week comparison, the first-brief decision and the re-adjusted-close detector read log entries for bars strictly before the last bar. The one exception is the detector, which also reads a *provisional* entry for the last bar itself, so a provisional close revised after the market closed still raises the note (D13). A provisional and a post-close entry for the same bar are kept side by side (the log key is ticker, bar and provisional flag); among entries for the week's base bar the one with a band is preferred, then the post-close one, then the later line. A re-run with no band never replaces an earlier entry that has one. Result: a run, a redacted `--no-refresh` re-run and a third run print the same past-facing sentences.
- **`shares_as_of`** defaults to `purchase_date` (D2 said so; the first implementation left it null). With neither date it stays null.
- **`MarketFacts`** carries defaulted `dates`, `opens`, `closes` and `model` so N2a can read them without new reads; opens come from a brief-local read-only query (`prices.py`, `open_readonly` on the path read at call time). The "no database import" test now allows exactly that one opener.
- **Smaller:** an `ineligible` result with no reason prints a generic clause; `TickerNotLoaded` after prices were read clears the prices (no Close line beside "No stored prices"); a model that fails to load is `model_unavailable`; the horizon constant is the model module's `HORIZON_SESSIONS` (Rule 1, one source); "today" for future-date checks is the Vietnam date; HOLDINGS LISTED leaves uncalibrated ranges out of the upper bound and says so (Rule 4) and guards a zero total value.

**Privacy and robustness (deviations from D2, D5, D10, D11)**
- **The log no longer stores levels** (price, text, reached, distance). Nothing read them. It keeps market figures, the bar date, the model version, the provisional flag and the ticker. This replaces D5's field list; old lines that still carry `levels` are read and the key ignored. The set of tickers in the log still shows what the investor holds, so the file keeps mode 600 and stays outside the repository. **Accepted residual disclosure:** ticker membership is visible in the redacted copy and in the log.
- **Log round trip:** the file is split on newline bytes (not `str.splitlines`, which also splits on U+2028, U+0085 and others), each line decodes on its own with replacement, an append starts a new line when the file does not end with one, and every string read back must match a strict pattern (ticker, ISO date, status, version) so an escape sequence cannot reach the brief.
- **Opening files:** the holdings file is opened once with `O_NOFOLLOW` (a symlink is resolved first and the resolved path is checked against the repository), checked with `fstat` on that descriptor (regular, owner, no group or world bit, at most 256 KiB) and read from it. The log is opened with `O_NOFOLLOW`, checked as a regular file owned by the user and set to mode 600. A directory that group or others can **write** is refused; one that others can read is still a warning, as is a git working tree above the file. The log path is derived from the resolved holdings path and is refused if it falls inside the repository.
- **Holdings file limits:** unknown fields are refused (a typo such as `share_count` would otherwise drop a value silently); at most 200 holdings, 50 levels each, `shares` at most 10^12; level text may not contain control, format, surrogate, private-use, unassigned, line- or paragraph-separator characters; nesting and encoding errors become a plain `HoldingsError`.
- **Print before append (changes D3 step 8):** the log is appended only after the brief has actually been written to stdout (a flushed write through an `emit` hook) or to `--out`. A closed pipe, Ctrl-C or a failed write leaves no entry and exits 1 (130 for Ctrl-C).
- **`--out` (changes D10):** refused anywhere inside the repository, redacted or not, and when it is (or is linked to) the holdings file or the log; written with `O_NOFOLLOW` and a loop until every byte is written. When stdout is a regular file that others can read, or one inside the repository, a warning goes to stderr (unredacted runs only).
- **Vendor text:** the refresh and fact gathering run with stdout redirected to stderr, so library notices never enter the brief.
- **Redaction (changes D11):** the redacted copy omits every sentence derived from the log: first brief, last week's range and verdict, "no range was issued", "last week's brief gave no range", the comparison limit sentence. They show how long a ticker has been in the investor's briefs. The week's move (stored prices) stays, and so does the re-adjusted-close note, which the original redaction list keeps; it too is derived from a log entry, so it discloses that an earlier brief existed for that date. That residual is accepted for now and recorded here for the owner. The structural test now globs every `sections_market*.py` module and checks each function reads only `MarketFacts` fields.

**Guards and extension points (changes D12, D15, D16)**
- **Runtime scan:** `build_brief` ends with one pass over every line the tool wrote (the investor's level texts removed): NFKC normalisation, format characters stripped, then buy, sell, hold, confidence and market sentiment; the triggers line also gets the judgement list. A failure stops the run with the line number only and nothing is shown or logged. `build_brief` also calls `disclaimer_for` on every coverage found in the facts (including the model), so any caller with a model at another coverage fails closed.
- **Triggers:** labels are lowercase letters, spaces and hyphens; counts are non-negative integers; notes come from a fixed list of patterns that a later change extends. The judgement list gains stem forms (risks, risky, recommended, recommendation, considered). Counters live in `TRIGGER_COUNTERS` in `compose.py`; N3 appends one there and edits neither `build_brief` nor `run.py`.
- **Fixed sentences:** `fixed_sentences()` returns every UPPER_CASE string constant in `wording.py` plus sentences registered by later modules, so a new constant is scanned without editing a list.
- **Sections:** the blank line between a ticker's sections no longer depends on a section's index; a section marked `joins_next` sits directly above the next. One failing holding prints "could not build this holding: <ErrorClass>" and the others (and the log) are unaffected. `LogRead.previous_issued_at(ticker, before)` is available for N3.
- **Deferred to the owner:** the way the investor's own level text is quoted in the brief (spec-mandated verbatim); the brief-auditor agent's tool list.
