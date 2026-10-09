## Context

The band is `range_k × √5 × sigma_daily_pct(t)`: a HAR-RV forecast of daily volatility, scaled by one global multiplier fitted so that the band holds the realised 5-session move `|ln(close[t+5]/close[t])|` about 68% of the time (`volatility-range` spec, Rule 1). Recorded figures, in the archived `calibrate-volatility-range` design and the describe-not-vote note (`docs/DISCUSSION_describe_not_vote_redesign.md`, "Second opinion"), are: pooled out-of-time coverage 0.676; flat across the ticker's own sigma quintiles (about 0.66 to 0.70); by test year 0.614 to 0.741 over seven walk-forward folds; date-clustered coverage sd about 0.24 across dates. **None of these was re-run when this change was written.** They are motivation, never a result. The by-year swing is market-wide by nature, so the open question is whether a market-level regime variable explains it, which would make it describable, or whether it is year-specific.

Facts checked in the repo on 2026-10-09 (read-only):

- `ohlcv` holds 599 tickers, 2016-01-07 to 2026-10-08, 2,685 distinct dates. No `VNINDEX` rows. The modelling universe is 208 tickers. Sessions per year are about 250; tickers with data per year rise from 80 (2016) to over 500 (2018 on).
- `backend/scripts/evaluate_vol_range.py` and `train_har_rv.py` already hold what this study needs: `build_window_frame` (windows with `r5`), `load_frame`, `split_fold`, `fit_fold`, `_month_block_interval` (a calendar-month block bootstrap, 1,000 resamples, seed 0), and `open_readonly`. `backend/scripts/evaluate_fibonacci_levels.py` fixes `SPLIT_DATE = "2023-01-01"` for an early/late split, which this study reuses.
- The Macro agent's vendor path is `_get_vnindex_closes` in `backend/app/services/debate/macro.py`: it reads `ohlcv` for "VNINDEX" (none stored), then calls `_market_closes(Market().index("VNINDEX"))`, which requests a hard-wired `MARKET_LOOKBACK_DAYS = 90` and `_get_vnindex_closes` keeps the last `n` (27, `VNINDEX_CLOSES`) closes. It does not pass `count`. P1 (`retire-debate-round-two-and-model-prose`) edits this file.
- The vnstock skill records a community-tier cap of 8 years of daily OHLCV, measured back from the call's `end`, observed on equities in 2026-07, silently truncating, and says `count` must be passed explicitly for a wide range. It was not observed on an index. The stored stock history is not bound by an 8-year wall either (172 of 599 tickers have rows before 2018-09, the oldest 2016-01-07), so how the vendor limits depth is not fully understood here. **The index's history depth is unverified**; measuring it is the first task.

## Goals / Non-Goals

**Goals:**

- Answer one question with a pre-stated kill criterion: does the band's out-of-time coverage differ by market regime (VN-Index volatility percentile at t) by at least 5 points between the calmest and most volatile third, in both an early and a late half, with a month-clustered interval that excludes zero and a gap that is not just the by-year variation?
- Make the answer re-runnable and read-only, in the repo's study-script pattern.
- Say plainly how few independent market episodes the data holds, and let that, not hope, set what the script can conclude.

**Non-Goals:**

- Any product, API or UI change; a regime badge, Rail chip or headline part (P7); the by-year coverage disclosure (Rule 4 sign-off, P3); the event study S2; fundamentals; a persisted index table; edits to `macro.py`, `requirements.txt`, `conftest.py` or any existing spec.
- Refitting or recalibrating the band by regime. The study measures the band as it is.
- A stock-derived market proxy (circular, decision 7).

## Decisions

### 1. A new script and a new capability, not an edit to `evaluate_vol_range.py` or `volatility-range`

`evaluate_vol_range.py` has its own spec requirement in `volatility-range` and answers a different question (in-sample and time-split coverage by year and sigma quintile). A separate script and capability keep that requirement stable and keep this change out of the specs P1 edits. This follows `cross-sectional-momentum-evaluation` (own capability, kill criterion before running, a plain verdict whatever the result, no served surface changes).

Alternative rejected: add a regime section to `evaluate_vol_range.py`. It would modify a shipped script and a spec requirement for a study that may be killed.

### 2. Regime: trailing 252-session percentile of the index's 20-session volatility, in thirds (new; no domain rule)

At each session `t`, `sigma_idx(t)` is the standard deviation of the index's last 20 daily log returns (the same estimator as the HAR feature `rv20`). The regime percentile is the share of the last 252 `sigma_idx` values, `t` included, at or below `sigma_idx(t)`; at most 1/3 is calm, above 2/3 is volatile. Only closes up to `t` are used.

Why this form:

- **Relative, trailing**: a percentile is relative by construction, in the spirit of Rule 3 (nothing is a fixed move size), and a trailing window is what a live page could compute, so a later headline part (P7) could show the same quantity. 252 sessions is about one year and matches the roughly 250 forecast values the live range service can hold (`HISTORY_ROWS = 311` closes in `volatility.py`).
- **It keeps regime from being a relabelled year.** A trailing one-year percentile puts about a third of the sessions of almost every year into each third, so the regime contrast is largely within years. An absolute level, or an expanding percentile, would put whole years in the volatile third and make "regime" and "year" the same variable. The expanding percentile is reported as a sensitivity result for exactly that comparison and does not enter the outcome.
- Cost: the first regime date is the 271st index session (20 returns, then 252 values), about 13 months after the series starts.

Dates with too little history (the first 271 index sessions, and any stock date with no index close) are excluded from every regime figure, counted, and never given a third or imputed.

Alternatives rejected: fixed volatility cut-offs (a fixed number, against Rule 3's spirit and not comparable across eras); index drawdown or trend (a direction variable; the question is about volatility regime); the HAR model applied to the index (fitted on stocks, so out of distribution); a market proxy from the 208 stocks (decided circular).

### 3. Index history: the vendor's index call, reimplemented in the script, not imported from `macro.py` (decision 7)

Decision 7 says to reuse the vendor index path in `macro.py`. This design reuses the call (`Market().index("VNINDEX").ohlcv` through the Unified UI, as the vnstock skill directs) and the date-dedupe rule (the later row of a date wins, because the live frame can repeat the latest session), not the function. The helper cannot fetch years (it requests 90 days and `_get_vnindex_closes` keeps 27 closes) and generalising it would put this study's change into a product file that P1 is editing. The script's fetch helper passes an explicit `count` (never omitted) and imports `vnstock` lazily inside the fetch function, after `app.vnstock_guard.install()` has run at the top of the module. That keeps the module import-safe for tests and satisfies `test_every_vnstock_importer_installs_the_guard_first`, which scans every `.py` under `backend/` for a vnstock import preceded by the guard import.

Rate limits: vnai ends a rate-limited process with a `SystemExit`, so the helper catches it with `_is_rate_limit_exit` from `app.services.bulk_ingestion` (the repo's single definition, imported lazily because importing that module imports `vnstock`) and the rate-limit exception the repo already catches (`ticker_ingestion.py` imports `RateLimitError` from `vnstock.core.exceptions`; the vnstock skill names `RateLimitExceeded` in `vnstock.core.quota`; task 1 checks which exists in the installed 4.0.5). A rate limit writes no partial series and exits non-zero. Calls are few (one, or a handful when walking back) and paced.

No API key is used (decision 3: the key path is untested against the guard). Vendor terms: `vnstock` 4.0.5 is licensed for personal, research and non-commercial use; this study fits that, per decision 3. Work, paid or shared use is outside it and is not legal advice. The call sends a symbol and a date range and nothing else.

### 4. History depth is measured first; the floor is about seven years, not six

The describe-not-vote note says to revisit if the vendor's history is under about six years. This design's own arithmetic is stricter. With a 271-session warm-up, an index series that starts at date `d0` yields regime dates from about `d0` plus 13 months. The walk-forward test years begin about 2020 and the early half runs to 2022-12-31, so the early half has 24 or more months of regime dates (`MIN_MONTHS_PER_HALF`) only if `d0` is about 2019-12 or earlier, that is about seven years before the 2026-10 end date. At six years the early half would have about 14 months and the study could not reach a verdict. If the series starts after about 2019-02, the first regime date falls after March 2020, which would leave the early half without its most obvious volatile stretch: in the stored data the modelling universe's mean absolute daily return is 2.9% in March 2020 against 1.2% to 1.4% in the last quarter of 2019 (a read-only query on 2026-10-09, not a study result).

Fallback ladder, in order, each step only if the previous leaves the first date later than about 2019-12:

1. Walk `end` backwards: repeat the call with `end` set to the earliest date returned, until the earliest date stops moving (the vnstock skill describes this for equities; not tested on the index).
2. Try the other source behind the Unified UI (`source=` as `ticker_ingestion.py` passes it for equities), then, for depth only, the Legacy `Quote(source=..., symbol="VNINDEX")` with the source pinned, which the skill allows when a single source must be pinned.
3. Stop. Do not build a stock-based proxy. Record the depth reached, and let the pre-stated rule produce `INCONCLUSIVE` (the early half is not evaluable). The owner may then revise `MIN_MONTHS_PER_HALF` once, before the first coverage run, with the reason recorded here, or accept the inconclusive outcome (decision 7: "revisit").

The measurement is a small `--depth-only` mode that fetches, prints the first and last date, session count, calendar gaps over 10 days and any vendor warning, and exits. It reads no database and writes no file.

### 5. The index series is cached as a CSV outside `app.db`

`--index-csv PATH` reads a cached `date,close` file and makes no network call. `--fetch-index PATH` fetches and writes that file; with neither flag the series is fetched and held in memory. The report prints the series' fetch date, source and SHA-256 when a CSV is used, so a re-run on the same CSV and database reproduces every figure (the momentum spec's "re-runnable" requirement), and a vendor revision of history shows up as a changed hash. Default location: `backend/data/study_cache/vnindex_closes.csv`, with `data/study_cache/*` added to `backend/.gitignore` (the existing rules cover only `data/*.db*` and `data/models/*`; vendor data should not be committable).

Alternatives rejected: a table in `app.db` (the study is read-only; a persisted index table is out of scope and `app.db` is disposable); a table in a new SQLite file (more machinery than 2,000 rows need, and it would resemble P2a's snapshot log); always refetching (not reproducible; invites a different vendor answer each run).

### 6. The band is measured out of time with the training script's own folds, reused by import

The by-year figures this study must be compared with are out-of-time walk-forward figures. Using the shipped coefficients on all dates (as `evaluate_vol_range.py` does for its headline rows) would fit `range_k` on the windows being scored. So the study imports `load_frame`, `split_fold`, `fit_fold` and the constants `RANGE_COVERAGE` and `MIN_TRAIN_ROWS` from the sibling `train_har_rv.py` (the script directory is put on `sys.path`, as the existing script tests do) and keeps each test window's hit. The by-year coverage it prints is recomputed from these folds, next to the reviewer-reported range, labelled as such.

A test asserts that on a synthetic frame the study's per-fold test year, window count and coverage equal `train_har_rv.run_validation`'s, which guards against drift if the training script is ever refactored. Alternatives rejected: re-implementing the fold loop (drift risk); moving the helpers into `app/ml/volatility.py` (a product-code change this study must not make).

### 7. Statistic, clustering and effective sample

For each half and third: window-weighted coverage (the convention of the artifact's pooled figure), the number of windows, distinct dates, distinct calendar months and regime episodes (maximal runs of consecutive index sessions in one third), and the mean and sd across dates of per-date coverage (the `date_clustered` view of `evaluate_vol_range.py`). The gap is calm minus volatile coverage in points.

Intervals: a 95% percentile interval from a calendar-month block bootstrap (`date[:7]` blocks, as `_month_block_interval` does; 2,000 resamples, seed 0), resampling months within the half so all windows of a date move together. Draws with an empty cell are dropped and their share printed. A quarter-block interval is printed beside it; if they disagree about whether zero is excluded the report flags it, but the outcome uses months. Months are not independent either (a volatile regime lasts months), so the number of months and of episodes is printed as the effective sample, and the interval half-width is printed so a wide interval is distinguishable from a small gap.

Why not dates as clusters: windows on one date move together (recorded per-date coverage sd about 0.24) and consecutive dates share four of five return days, so a date-level interval would be far too narrow. Why not non-overlapping windows as the sole control: the month block handles the dependence and keeps every window.

### 8. The pass level, the extra conditions, and the three outcomes

Decision 8 fixes at least a 5-point gap between the calmest and most volatile third, in both halves, with a date-clustered interval that excludes zero, and allows this design to revise the level after considering how few independent market episodes there are. **The level stays at 5 points.** Reason: the number of independent episodes is small (an expectation of single digits to low teens per half, an assumption that the script's episode count replaces), so the interval, not the 5-point floor, is expected to bind. Illustration, with an assumed value and no measurement behind it: if the month-to-month sd of a third's coverage were 0.10 and each cell had 12 months, the standard error of a gap would be about 0.10 × √(2/12) ≈ 4 points and the 95% half-width about 8. A lower floor would not make a gap detectable, and a higher one would make a `PASS` nearly impossible, so the floor is left where the owner set it and the report prints each half-width.

Three things are added so that the question actually asked ("beyond the by-year variation") has an answer, and that an unlucky sample cannot pass by accident:

- **Sign agreement**: both halves must show the gap in the same direction; opposite signs are a `KILL`.
- **Year-adjusted gap**: the equal-weighted mean of each calendar year's own calm-minus-volatile gap (years with windows on at least 20 dates in both cells), with a year-stratified month-block interval. A `PASS` needs its sign to match and its interval to exclude zero. If the regime thirds were just years, there would be few qualifying years and this check would fail, which is the point.
- **Evaluability**: a half needs 24 months, each third 8 months in it, and 99% of test dates must have an index close. Otherwise the outcome is `INCONCLUSIVE`, never `PASS` or `KILL`.

Outcomes: `PASS`; `KILL` (a half under 5 points, or opposite signs); `INCONCLUSIVE` with the failing conditions printed (not evaluable, an interval that includes zero, a year-adjusted gap not separable from zero). A `KILL` whose interval for the gap reaches 5 points is printed with a note that the level is not met and that this is not evidence of no effect. `PASS` means a later change may design something; it does not mean anything is shown or served.

All of these constants (252, 20, thirds, 2023-01-01, 5 points, 95%, 2,000 resamples, 24/8/20 months and dates, 0.99) are new thresholds and covered by no domain rule. They are not thresholds on the size of a price move, so Rule 3 is not engaged, and they are fixed in the spec and in the script before any real run.

### 9. Reporting and rules

Stdout: a header line (study output, not shown to any user (Rule 4), a technical observation and not investment advice (Rule 6)); the index series' provenance and depth; counts and exclusions; the recomputed by-year coverage beside the labelled reviewer-reported range; the cell table; the gaps, intervals and half-widths; the sensitivity result; the outcome with reasons. `--json PATH` writes the same figures. Nothing reaches an API, the UI or an export, so Rule 4 is honoured by construction (no reliability figure is shown to anyone), Rules 5 and 6 are not triggered by a developer printout (the header carries the two labels at near-zero cost), and the debate-synthesiser label table is not involved (the study's `PASS`, `KILL` and `INCONCLUSIVE` are study outcomes, not debate verdicts). Rules 1 and 2 are honoured unchanged: the outcome is the existing 5-session `r5` and every printed rate is a percentage.

### 10. Tests

`backend/tests/test_evaluate_band_coverage_by_regime.py`, in the style of `test_evaluate_fibonacci_levels.py`: the script is loaded by path, tests are small pure-function tests on synthetic series, no network and no real database. They cover the regime (no look-ahead, warm-up, thirds), the verdict table (every scenario in the spec), the interval on constructed effects, fold equality with `train_har_rv.run_validation`, read-only behaviour on a temporary database, the CSV cache and duplicate-date handling with a stubbed vendor handle, and that the constants equal the spec's values. Only this file and the guard test are run; the full suite is not run for this change because it touches the real database.

### 11. Overlap with the other two open changes

- P1 (`retire-debate-round-two-and-model-prose`) edits `macro.py`, `technical-agent`, `macro-agent` and one `volatility-range` scenario. This change imports nothing from `macro.py` and modifies no spec, so there is no file or spec overlap; it cites `macro.py` helpers by name because their line numbers will move.
- P2a (`add-company-feed-news-and-events`) adds a second `vnstock` importer, edits `requirements.txt` (pins) and `conftest.py`, and writes `backend/data/company_feed_log.db`. This change edits none of those; it adds one `.gitignore` line, which P2a does not need (its file matches `data/*.db*`). The two share only the vendor's rate limit (about 20 requests a minute without a key, unverified), so the depth probe and a P2a fetch should not run in the same minute.

## Risks / Trade-offs

- **The vendor's index history is under about seven years** → the ladder in Decision 4, then `INCONCLUSIVE` by rule, with the owner able to revise the month floor once before any coverage run. No proxy is built.
- **Few independent market episodes, so the interval is wide** → `INCONCLUSIVE` is the likely outcome if the true gap is about the size of the by-year gaps. The report prints half-widths and episode counts so that is visible, and the level is not lowered to avoid it.
- **Regime and year are partly collinear anyway** → the trailing percentile mitigates it and the year-adjusted gap tests it; if too few years qualify, the outcome is `INCONCLUSIVE`, not `PASS`.
- **Month blocks understate dependence** (a volatile regime spans months) → the quarter-block interval is printed and disagreement is flagged; the episode count is the more honest effective sample.
- **Overlapping 5-session windows and pooled tickers** → the month-block bootstrap resamples whole months; the point estimate keeps every window, as the artifact's pooled figure does.
- **Selection by the universe filters** (liquidity and history filters use full history, a caveat the Fibonacci study also carries) → shared with the artifact's own coverage figure; not corrected here.
- **Vendor data can be revised or truncated silently** → the CSV hash is printed; the depth probe reports the vendor's history-limit warning.
- **A partial intraday close on the latest index row** → windows need `t+5` stock data, so the last few index dates never form a window; the dedupe rule keeps one close per date.
- **Importing a sibling script** (`train_har_rv`) couples two scripts → the fold-equality test fails if they drift.
- **The study could be read as endorsing a regime-conditional claim** → the outcome text names what a `PASS` would still need, and nothing is added to `MODEL_CARD.md`, because a by-regime coverage figure is a second reliability figure (Rule 4 sign-off).

## Migration Plan

No deployment and no data migration. New files only, plus one `.gitignore` line; the cache CSV is disposable and gitignored. Roll back by deleting the script, its test, the cache directory and the `.gitignore` line. On archive, the delta spec becomes `openspec/specs/band-coverage-regime-evaluation/spec.md`; run `openspec validate` before archiving (the describe-not-vote note records that two active changes editing one requirement is untested, which does not arise here because this change adds a capability only).

The recorded result goes into this file under a "Result" heading when the single run is done, with the verbatim outcome line and the index CSV's SHA-256, and one pointer line is added to the describe-not-vote note's "Not verified" list.

## Open Questions

1. **Vendor index depth (unverified).** Resolved by task 1. If the ladder cannot reach about 2019-12, recommendation: accept `INCONCLUSIVE` or let the owner lower `MIN_MONTHS_PER_HALF` once, before the first coverage run, and never fall back to a stock-derived proxy.
2. **Is `source=` accepted by `Market().index(...).ohlcv`, and does depth differ between VCI and KBS for the index?** Unknown; task 1 checks. Recommendation: pin nothing unless the default source is shallower than another.
3. **Which rate-limit exception exists in the installed vnstock 4.0.5**, `vnstock.core.exceptions.RateLimitError` (used by `ticker_ingestion.py`) or `vnstock.core.quota.RateLimitExceeded` (named in the skill)? Task 1 checks and the helper catches what exists, plus the `SystemExit` path.
4. **Added conditions versus decision 8's literal text.** Sign agreement, the year-adjusted gap and the `INCONCLUSIVE` outcome operationalise "beyond the by-year variation" and "date-clustered interval", but they make `PASS` harder than the literal text. Recommendation: keep them; the owner may drop the year-adjusted condition before the first run, in which case the question is no longer "beyond the by-year variation".
5. **Split date.** A fixed 2023-01-01 (the Fibonacci study's) against the midpoint of the evaluated range. Recommendation: the fixed date, because it is stated before any data is seen and repeats an existing split.
6. **Rule 6 and the printout.** The script prints a header with the two labels and no disclaimer, on the reading that a developer printout is not "displayed or exported" to a user. If the owner reads `--json` as an export, the one-line fix is to add the disclaimer text from `docs/DISCLAIMER.md` to the header; recommendation: not needed.
7. **After a result.** `PASS` leads to a design question for P7 and a Rule 4 sign-off question for P3 (where a by-year or by-regime coverage statement goes); `KILL` closes the regime idea for the headline parts; `INCONCLUSIVE` may be re-run as months accrue or history is extended. None is decided here.
