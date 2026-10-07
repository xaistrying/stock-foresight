## Context

`multi-agent-debate-analyst` and `debate-data-quality-refinements` (both archived 2026-10-05) shipped the debate; commit e77986e (stance parsing, Round 2 failure) is the baseline. The 2026-10-06 post-pivot review (`docs/DISCUSSION_post_pivot_review.md`) found the debate has no data or degraded-agent guards. Its figures are the reviewers' own measurements and **have not been reproduced by us**; below they are marked "measured in the 2026-10-06 review". Figures marked "drafting probe" were read by the author of this change from `backend/data/app.db` opened `mode=ro` on 2026-10-06; they are not yet preserved as a script (task 1.1 does that).

Current behaviour, re-verified against the tree after e77986e:

- `api/debate.py:56-83` checks only `features_computed` (503) and row existence (404), then runs the engine and exports.
- `engine.py:137-154` `_safe_run`: a Round 1 exception becomes a neutral placeholder; a Round 2 exception returns the Round 1 position plus a note. Both count as normal votes. `DebateResult` (`engine.py:50-60`) has no degraded field.
- `engine.py:156-163` `_get_as_of`: reads `tech._as_of`, which `technical.py:140` sets only on full completion; otherwise `date.today()`. The `no feature data` and `no indicators` early returns (`technical.py:112-127`) skip it. The report filename and title use `as_of` (`export.py:67`).
- `news.py:126-140`: an LLM failure returns a neutral position (no exception), so `_safe_run` never sees it; `news.py:131-133` forces neutral when the stance line is unrecognised. News stance exists only through the LLM.
- `macro.py:301-310` (signal 2) takes the ticker's last 20 stored closes and the live VN-Index's last 20 by position. `VNINDEX` is not in `ohlcv` (drafting probe: 0 rows), so it is always the live frame, which `_market_closes` (`macro.py:79-87`) reduces to closes with `reset_index(drop=True)`, discarding dates. A macro run with no counted signal returns `neutral` (`macro.py:339-344`).
- `synthesiser.py:30-54` maps three stances; two neutral plus one directional is `OBSERVE` (`:49-51`). The `debate-engine` spec scenario "Agents split with no majority direction" says `SPLIT` for that case, and so does the archived design (Decision 2). The `debate-synthesiser` spec says `OBSERVE`.
- The stored `features.near_gap` flag (`feature_engineering.py:196-227`, `GAP_THRESHOLD_DAYS = 5` at `:170`) is what `/prediction` and `/insight` refuse on.

Evidence for the thresholds (drafting probe unless stated):

- Staleness (review): `last_loaded_at` is 2026-09-07 for 596 of 599 tickers, 10-05 for 2, 10-06 for 1. Probe: 21 market sessions exist after 2026-09-07; 3 tickers have a row within 2 sessions of the newest.
- The data-derived session calendar is clean: no weekend rows, and no date before 2026-09-07 with fewer than 300 tickers. Since 2025-06 there are 15 weekday non-sessions (1–2 Sep 2025, 1–2 Jan 2026, 16–20 Feb 2026 (Tet), 27 Apr, 30 Apr, 1 May, 31 Aug–2 Sep 2026).
- **The stored `near_gap` flag cannot be reused as a guard.** `GAP_THRESHOLD_DAYS = 5` calendar days is not holiday-aware: the 6-day National Day gap (2026-08-28 to 2026-09-03) is a "gap". Row D is flagged when a gap lies 26 to 77 rows before it, so every ticker that includes that gap flips to `near_gap = 1` 26 sessions after 2026-09-03, i.e. from 2026-10-09 (SAB, VIB and VPB, the three refreshed tickers, are 21 to 23 sessions past it today), for 52 sessions. The same pattern is visible in history: ACB's rows 26 to 77 sessions after the Tet reopening on 2026-02-23 are `near_gap = 1`, 25 and 78 are not. Used as a guard it would refuse almost every refreshed ticker from 9 October until about late December, and again after Tet.
- Ignoring age, with the definitions in this change, 313 of 599 loaded tickers pass (all listed). Reasons among the rest (a ticker can have several): delisted 194, near_gap 200, indicators_missing 88, hard_quality_flag 67, insufficient_history 9. The review's "49 tickers with a hard flag within 120 days" is a different window and reference date; ours counts a flag within each ticker's own last 78 sessions.

## Goals / Non-Goals

**Goals:**
- No debate verdict from stale, partial or degraded inputs: eligibility before any LLM call; degraded agents excluded from the vote and listed; abstention when fewer than two agents are live.
- `as_of` is always the date of the data used; data age is visible in sessions.
- One eligibility service the range endpoint and the debate log share.
- Macro signal 2 compares like with like.
- Remove the `SPLIT` / `OBSERVE` spec conflict.

**Non-Goals:**
- Range math, `range_hit_rate` (`calibrate-volatility-range`); outcome logging (`debate-outcome-log`); LLM timeouts, retries, concurrency, prompt fencing (`harden-debate-runtime`); display labels, "Agreement" wording, `DISCLAIMER.md`, Rule rulings (`align-rules-and-disclaimer`).
- Refreshing stale tickers automatically (the app has no scheduler); the panel points the user at Refresh.
- Fixing canned fallback prose for the Synthesiser (`"Unable to generate key tension analysis."`, `synthesiser.py:147`) or the always-printed "Report saved to" note (`DebatePanel.jsx:123`). They are flagged, not fixed: they never alter the verdict, and only the second becomes wrong in a new way (abstentions are not exported); the insufficient-data view has no Level 3, so it never shows the note.
- A market calendar dependency.

## Decisions

### Decision 1: data age is counted in sessions, with a wall-clock tail and a stored-session body

`age_sessions` = (distinct session dates stored for any ticker after the ticker's `as_of`) + (weekdays after the newest stored session date, up to and including the previous weekday in Vietnam time (UTC+7); zero if none). Today's session is never expected: the app has no scheduler and the board settles after the close, so the check is "up to yesterday". A ticker is `stale` when `age_sessions > MAX_AGE_SESSIONS = 3`. Rule 1's unit is trading sessions, so age is in sessions, not calendar days. The 3 is new and provisional (not covered by Rules 1–6): it absorbs a weekend plus one slack session, and a 3-weekday holiday in the unrefreshed tail (31 Aug–2 Sep 2026).

**Alternatives considered**
- *Wall-clock weekdays only.* Cannot be fooled by a stale database, but counts every holiday weekday as a missing session, permanently for any ticker whose `as_of` precedes it (15 weekday holidays since 2025-06). With a tolerance of 3 only Tet-sized closures (5 weekdays) would false-positive, but the stored-session body removes the error up to the newest stored date for free.
- *Newest session across the database as the reference* (the `DISCUSSION_calendar_staleness.md` proposal, written for the Fresh/Stale dot). No threshold, no holiday error, but it degrades to "everything is fresh" when nothing has been refreshed: until 2026-10-05 the newest stored session was 2026-09-07 (596 tickers were loaded that day), so all 599 tickers would have read age 0 for a month. A debate guard must not have that failure mode. Chosen: use it only for the part of the count it is exact for (sessions the app has actually stored), and wall-clock only beyond it.
- *Hand-maintained holiday list or a market-calendar package.* A new dependency or a table to maintain for a count whose tolerance already absorbs most error.

**Known Limitation (owner-accepted, no special exemption):** the hybrid rule removes the holiday error only for closures that stored sessions already cover (a holiday followed by any ticker's later session). It does not remove it during a closure itself, because nothing stored lies beyond it. During a long closure such as Tet (5 weekdays), the wall-clock weekday part makes every ticker read stale from the 5th weekday of the closure (age 4; the 4th weekday reads 3 and is still accepted), so the debate refuses until the market reopens and a refresh stores the first new session; Refresh during the closure cannot clear it. This is about 2 weekdays a year for Tet and nothing for closures of 3 weekdays or fewer (31 Aug–2 Sep 2026 reads age 3, not stale). **Follow-up (not built):** an optional extra-closures list consulted by the wall-clock part.

Cost: one scan of `ohlcv` by date (about 0.07–0.09 s on 1.04M rows in the drafting probe; no index on `date`). `# ponytail: full scan per call; add an ohlcv(date) index or a short-lived cache if /range or the log call it in bulk.`

### Decision 2: eligibility reasons and their definitions

All reasons that apply are returned, in fixed order `delisted, insufficient_history, stale, near_gap, hard_quality_flag, indicators_missing`; `eligible` is `reasons == []`. `as_of` is the date of the latest `features` row (`null` when there is none, which also gives `insufficient_history`). The service reads the database itself and must not import `app.api.predictions`.

| Reason | Definition | Constants |
| --- | --- | --- |
| `delisted` | `ticker_universe.listing_status = 'delisted'`. No universe row: not flagged. | |
| `insufficient_history` | fewer than `MIN_SESSIONS` priced (`close > 0`) `ohlcv` rows | `MIN_SESSIONS = 65`, imported from `ml/volatility.py:31` |
| `stale` | `age_sessions > 3` (Decision 1) | `MAX_AGE_SESSIONS = 3` |
| `near_gap` | more than `MAX_MISSING_SESSIONS` market sessions are absent from the ticker's own series within the span of its last 65 priced sessions; a market session is a date on which any stored ticker has a row | `MAX_MISSING_SESSIONS = 2`, window 65 |
| `hard_quality_flag` | an `ohlcv_quality_flags` row with `flag_tier = 'hard'` dated within the ticker's last 78 priced sessions | imported `HARD_FLAG_BLACKOUT_SESSIONS = 78` (`feature_engineering.py:440`) |
| `indicators_missing` | any of `rsi`, `macd_histogram`, `tenkan_sen`, `kijun_sen` is null on the `as_of` row | |

- *History.* `predict_volatility_range` needs 61 closes (`rv60`; its own guard is `len(df) < 60`, `volatility.py:142`) and the first non-null MACD histogram is the 34th row (`feature_engineering.py:310-311`). 65 is the serving constant `MIN_SESSIONS` (training needs it for the forward target). Using it costs tickers with 61–64 sessions (none in the drafting probe beyond the 9 below 65) and keeps one definition. The range endpoint's `range_hit_rate` needs far more history (about 126 closes); that stays `calibrate-volatility-range`'s status field, not an eligibility reason.
- *Hard flag window.* The HAR model reads 61 closes, the Technical agent's indicators are nulled for 78 sessions from a level-shift flag (`HARD_FLAG_BLACKOUT_SESSIONS`), and an `invalid_close` flag marks a zero close that the HAR loader does not filter, which makes `rv` windows NaN. Measured read-only on a synthetic 130-session series with the real `har_rv_model.pkl` (task 1.3): a zero close in the last 4 rows makes `predict_volatility_range` silently read an older row (1 to 4 sessions back); a zero 5 to 64 rows from the end makes it return `None`; only a zero at the very start of the 65-row window is harmless. Either way the range is wrong or missing, so the hard-flag reason holds, but "falls back to an older row" is true only for the last 4 rows. 78 covers both readers and makes the reason name the cause (otherwise the same ticker would only say `indicators_missing`). Alternatives: 65 (HAR span only; leaves the indicator blackout reported under a vaguer reason), 120 calendar days (the review's figure; not tied to what is read).
- *`near_gap` is deliberately not the stored flag.* See Context: it is holiday-blind and flips for every ticker for 52 sessions after each holiday of more than 5 calendar days. The new definition counts only sessions the market had and the ticker lacks, using the data-derived calendar from Decision 1 (holiday weekdays have no row for any ticker, so they cost nothing). Thin-trading tickers with omitted sessions are caught: of 405 listed tickers, 75 miss six or more sessions in their last 65 and 112 miss at least one (37 miss between one and five; reproduced by `verify_data_eligibility.py`, task 1.2; an earlier draft said "37 miss at least one"). `MAX_MISSING_SESSIONS = 2` is new and provisional (about 3% of the window; a single omitted day should not exclude a ticker for three months). With a single loaded ticker the calendar is its own dates and the count is zero by construction (documented ceiling).
- *Indicators.* Partial availability does not pass: the Technical agent would vote on one or two of three signals. The four columns are exactly the ones `technical.py:43-70` reads.
- All thresholds are new; none implements Rules 1–6. The owner accepted the four values (stale after 3 sessions, more than 2 missing sessions in the last 65, history 65, hard-flag window 78) as provisional; they are module constants, revisited after outcome data.

### Decision 3: ineligible ticker is HTTP 200 `INSUFFICIENT_DATA`, not a 4xx

The endpoint calls `assess_eligibility` after the existing 404/503 checks and before the engine. When `eligible` is false it returns 200 with `verdict = INSUFFICIENT_DATA`, `agreement_level = none`, `eligibility`, `data_as_of`, `data_age_sessions`, empty `round1`/`round2`, empty `agents_degraded`, null range fields, no LLM call, no report file.

| | 200 + `INSUFFICIENT_DATA` (chosen) | 409/422 with a detail body |
| --- | --- | --- |
| LLM cost | none | none |
| Frontend | one success path; `mutation.isSuccess` renders the state. The client treats non-2xx as `ApiError` and shows "Analysis failed — please try again" with a Retry button, wrong for a deterministic refusal | needs an error-body parser and a second state |
| Consumers (log, scripts) | one shape for abstentions, whether from eligibility or from degraded agents | a second shape |
| Semantics | the question was answered: "not enough data" | request treated as an error |

404 (not loaded) and 503 (feature computation failed) stay: those are not data-quality judgements. Agents that never ran are not "degraded": `agents_degraded` is `[]` on this path.

No export for abstentions: the report filename is `{as_of}_{TICKER}.md` and re-runs overwrite, so a Thursday refusal on the same `as_of` would destroy Monday's real report.

### Decision 4: a degraded agent does not vote; the verdict rule for 3, 2 and fewer live agents

`AgentPosition` gains `degraded_reason` (null = live). Codes: `agent_error` (the agent raised in Round 1), `no_input` (nothing to form a stance from), `llm_failed` (a stance that only the LLM can supply failed or was unrecognised in Round 1), `round2_failed` (the Round 2 call raised, was blank, or had no recognisable stance line). Round 2 runs only for agents live after Round 1. An agent degraded in either round has no vote; its Round 1 position (if any) stays visible.

Per agent, "degraded" means the stance, not the prose, cannot be trusted:

- Technical: none of RSI, MACD histogram, Ichimoku available → `no_input`; exception → `agent_error`. An LLM prose failure is not degradation (the stance is deterministic) but its fallback bullets must state the computed values instead of the current "Indicator data unavailable" (`technical.py:101,208`), which contradicts reality.
- News: all feeds failed, or zero headlines → `no_input` (a nothing-to-read agent is not a neutral opinion; real zero-headline runs are rare because `[market]` headlines nearly always exist, so this is close to an outage flag); LLM raised or reply without a recognisable stance → `llm_failed`. Today these return neutral without raising, which is why `_safe_run` never saw them.
- Macro: no counted signal → `no_input` (today: default neutral, `macro.py:339-344`); LLM prose failure is not degradation (the fallback bullets are the numbers).

Verdict with live stances `L` (Round 2 stances of live agents):

| Live agents | Rule |
| --- | --- |
| 3 | existing mapping, unchanged (including 2 neutral + 1 directional → `OBSERVE` / `majority`) |
| 2, agree | `BUY_SIGNAL` / `CAUTION_SIGNAL` / `OBSERVE` by the shared stance; `agreement_level = majority`, never `unanimous` and never a "strong" verdict (those need three agreeing agents) |
| 2, disagree | `SPLIT` / `split` |
| 0 or 1 | `INSUFFICIENT_DATA` / `none`; Round 2 (if not yet run) and both synthesis LLM calls are skipped |

**Alternatives considered**
- *Forced downgrade* (keep a neutral placeholder vote, cap strength). Bull, bull, placeholder gives the same `BUY_SIGNAL`, but bull plus neutral plus placeholder gives `OBSERVE` (two neutrals) where two live agents that disagree are a `SPLIT`. A placeholder is not evidence and must not decide an outcome.
- *Keep the Round 1 stance when Round 2 fails* (e77986e). Avoids discarding a deterministic stance on a transient failure. Rejected for the vote: it is the "silent confirmation" the review flagged and, with the LLM down, lets Technical and Macro produce a verdict with no debate at all. An LLM outage now yields News `llm_failed` plus Technical and Macro `round2_failed`, so three degraded and `INSUFFICIENT_DATA`. The retained Round 1 position is still shown. **Owner-approved: this reverses part of commit e77986e** (which kept the Round 1 stance on a Round 2 failure).
- *Abstain at one degraded agent.* Too aggressive: News is the agent most likely to degrade and the other two are deterministic.

The synthesiser's tension and summary prose failing is not a vote degradation; the verdict is unchanged.

When Round 2 is skipped (fewer than two live agents after Round 1) `round2` repeats the Round 1 position objects, so a lone live agent appears there with its Round 1 stance and `degraded_reason: null` although no Round 2 ran for it. An `INSUFFICIENT_DATA` result therefore has no meaningful Round 2 stance: consumers (notably `debate-outcome-log`, which reads `r2_*` columns) must not record round2 stances from an abstention. Found in the post-implementation review; left as is because the panel and export never show round2 for an abstention.

The agreement count is "N of M live agents" with "(K unavailable)" when `K > 0`; the panel and export compute it from Round 2 stances of live agents (the current code counts all `round2` entries, `DebatePanel.jsx:45-53`, `export.py:75-79`).

### Decision 5: `as_of` is the features row date; the Technical agent reads that row

The engine takes `as_of` and `age_sessions` from `assess_eligibility` before Round 1, removes `_get_as_of` and the `tech._as_of` attribute, and passes `as_of` to the Technical agent so it reads the features row of that date. A refresh landing during the 40–65 s debate (the panel's Refresh is independent) would otherwise make the label and the data disagree. `data_as_of` equals `as_of`; both are kept (shared contract names `data_as_of`; `as_of` stays for the report filename and existing clients).

**Alternatives:** keep the attribute hack and fix only the fallback (leaves the three early returns uncovered); stamp `as_of` after Round 1 from whichever row Technical read (the label could still be wrong if Technical failed).

### Decision 6: Macro signal 2 compares the same dates; mismatches are unavailable

The ticker's window is its last 20 stored closes (the current convention: first to last close, `iloc[-20]` to `iloc[-1]`, 19 intervals; not changed here); its dates are `d_first` and `d_last`. The VN-Index return is taken between the closes dated exactly `d_first` and `d_last`. If either date is absent from the live VN-Index frame (a holiday mismatch, or a ticker whose window reaches back beyond the 90-calendar-day fetch, `MARKET_LOOKBACK_DAYS`), the window is mismatched: signal 2 casts no vote and the reasoning says `ticker window <d_first>..<d_last> not covered by the VN-Index data`. The signal text carries the dates. `_load_ohlcv_closes` and `_market_closes` must keep dates. Task 5.1 confirmed with one live `Market().index("VNINDEX").ohlcv()` call (2026-10-07): the date column is `time` (datetime64, stamped 07:00), as the test double has it, and the frame can repeat the latest session (2026-10-06 appeared twice, same close, different volume), so `_market_closes` keeps one row per date, the later one, or `series[date]` would not be a scalar. The index fetch widens from 22 to 27 closes (d_last up to 5 closes from the end including today's bar, d_first up to 26 with 2 tolerated missing sessions, +1 slack) so a ticker at the age and gap limits still has its first date covered.

Signals 1, 3 and 4 are live market state and stay unaligned; eligibility bounds the ticker's age at 3 sessions, so the mismatch with the stored indicators is at most that, and it is visible via `data_age_sessions`.

**Alternatives:** interpolate or forward-fill the index (invents closes); refuse the whole Macro agent on mismatch (loses three valid signals); align by trimming to the shorter window (still compares different spans).

### Decision 7: resolve 2 neutral + 1 directional as `OBSERVE` / `majority`

The code, the `debate-synthesiser` spec and its tests (`test_map_verdict_two_neutral_one_bull`) say `OBSERVE`; the `debate-engine` spec scenario and archived design Decision 2 say `SPLIT`. Recommended: align the engine spec to the code. Reason: two agents agree there is no actionable lean, so a directional verdict is not warranted, and `SPLIT` ("no consensus") would overstate disagreement. The alternative is a code change plus new synthesiser tests. Not a domain rule. Owner-approved: align the `debate-engine` spec to the code; no code change. The `debate-engine` delta rewrites the scenario. The `debate-synthesiser` mapping requirement is MODIFIED only to drop the superseded sentence that bans "BUY"/"SELL" "as standalone instructions" (display wording is `align-rules-and-disclaimer`'s, whose ADDED requirement says it supersedes that sentence; it ADDs rather than MODIFIES, so there is no header collision and its "supersedes" wording becomes redundant after both archive); the mapping table itself is unchanged and gains a scenario for two neutral plus one directional.

### Decision 8: UI and export are additive

New `debate-panel-ui` and `debate-report-export` requirements have distinct names; no existing requirement there is modified by this change, so `align-rules-and-disclaimer` can modify labels without a header collision. The data-date line and degraded markers use text and an icon, never colour alone. The insufficient-data view has no Level 2/3, shows the disclaimer (Rule 6, existing requirement covers all states), and does not render Advice, Confidence or Sentiment. Reason text lives in the frontend (a mapping from code to sentence); the stale sentence points at the ticker panel's Refresh. The "Insufficient data" display label and the word "Agreement" belong to `align-rules-and-disclaimer`.

## Risks / Trade-offs

- **[Most tickers will be refused until refreshed]** (3 of 599 had a row within 3 sessions in the drafting probe; 313 would pass after a refresh) → the state says why and what to do; this is the intended behaviour, and the scale is the review's finding, not a side effect.
- **[Long closures (Tet) read stale]** → owner-accepted Known Limitation (Decision 1); follow-up extra-closures list.
- **[`near_gap` redefinition diverges from the stored flag]** → `/prediction` and `/insight` still use the flag until `retire-direction-model` removes them; the stored column is unchanged and documented as legacy.
- **[Excluding thin-trading names]** (75 of 405 listed tickers miss six or more sessions) → consistent with the HAR forecast being unreliable there; `MAX_MISSING_SESSIONS` is the knob.
- **[Round 2 exclusion changes e77986e behaviour]** → owner-approved; recorded with the alternative; retries in `harden-debate-runtime` shrink the exposure.
- **[Same-requirement edits across siblings]** `DebateResult` shape: this change and `calibrate-volatility-range` both modify "Debate engine produces a structured `DebateResult` object" (the rename to `range_5s_pct` / `sigma_daily_pct`). The delta here already uses the contract names (`range_5s_pct`, `sigma_daily_pct`, `range_coverage`; `calibrate-volatility-range` does not modify the `debate-engine` requirements itself, so this delta carries the shape). If calibrate archives after this change, its text replaces ours and drops our fields: archive order or a manual merge is needed. The Round 1 requirement also named `volatility_range_pct`; the delta here removes that field name from it (the range fields belong to `volatility-range`).
- **[`ohlcv` full scans]** → see Decision 1 ponytail note.
- **[A degraded News agent on thin headline days is rare but possible]** → shown as unavailable, not as neutral.

## Migration Plan

1. Land `data_eligibility.py` and its tests (no behaviour change).
2. Engine, synthesiser, agents, endpoint; update the tests that encode the old behaviour (`test_engine_one_agent_fails_debate_proceeds`, `test_engine_round2_failure_keeps_round1_stance`, `test_parse_stance_unrecognised_keeps_round1_stance_not_neutral`, the News "graceful" tests, Macro tests that patch `_load_ohlcv_closes`).
3. Frontend and export.
4. Rollback: `VITE_DEBATE_PANEL_ENABLED=false` hides the panel; the API additions are backward compatible (new fields, one new verdict value that clients not updated would render as the raw string).

## Resolved by the owner

1. Two neutral plus one directional is `OBSERVE` / `majority`; the `debate-engine` spec follows the code (Decision 7).
2. A failed Round 2 excludes the agent from the vote (Decision 4; reverses part of e77986e).
3. Thresholds accepted as provisional (Decision 2).
4. No special exemption for Tet or other long closures; documented as a Known Limitation (Decision 1) with a follow-up.
5. News with zero headlines is degraded (`no_input`).
6. Macro with one counted signal stays live.
7. Taken over from other drafts: drop the superseded BUY/SELL sentence from the synthesiser mapping requirement (done as a MODIFIED requirement, Decision 7); fix the stale `macro.py` comment "Provisional, like Rule 3's 0.5" (`macro.py:180-182`; Rule 3 is not what that threshold implements) as task 5.4.
8. `assess_eligibility` lives in `app/services/data_eligibility.py`; `debate-outcome-log` and `harden-debate-runtime` apply after this change.

## Open Questions

1. `data_as_of` duplicates `as_of`; drop one once the log and frontend are migrated (shared contract fixes the name).
2. Optional follow-up: an extra-closures list for the wall-clock part of `age_sessions` (Known Limitation, Decision 1).
3. Synthesiser prose failure and the always-printed "Report saved to" note are unfixed (Non-Goals); who owns them?
4. Deviation from the shared contract: new `degraded_reason` per position, `agreement_level = none`, and `assess_eligibility(ticker, now=None)` takes an optional clock for tests. The contract's signature and return keys are unchanged.
