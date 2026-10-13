# Discussion: what the project is for, and a weekly check-in brief for holdings (2026-10-11)

Raised on 2026-10-11 while the owner compared `reports/2026-10-09_SAB.md` with the 2026-10-08
report and asked whether the verdict label can be made sensible and somewhat trustworthy. The
session widened into "what is this project for?", settled a purpose with the owner, and
prototyped a weekly brief on paper, with simulated investors reading it.

**Status (updated 2026-10-12)**: open, partly implemented. The rules part is done: Rules 4, 5 and 6 were
rewritten and the brief disclaimer added by `align-rules-with-weekly-brief` (archived 2026-10-12). No brief
code exists yet. The **current plan and the list of what is left are in "Status record (2026-10-12)" at the
end of this file**; where an earlier section disagrees with it, the status record and the notes marked
"Update" win. This file records what was found, what the owner chose, what is only proposed, and what is
unverified, so a later session can continue without redoing it. Anything that changes a domain rule or the
product shape is `/opsx:propose` territory (`CLAUDE.md`: ask before changing a rule).

**How to read the evidence.** Three kinds of statement appear, and they are not equally strong:

- **Measured**: a read-only query on 2026-10-11 against `backend/data/app.db`,
  `debate_log.db` or `company_feed_log.db` (opened `-readonly`).
- **Persona-run**: a number produced by a role-played agent's own small check, usually on a proxy
  (not the production band or agent code). Unreplicated.
- **Simulated**: a role-played investor reading a brief. The same model wrote the brief and played the
  reader, so this finds reading errors and plausible reasoning, not real behaviour. n = 1 per cell.
  Scenario inputs marked *hypothetical* were invented.

## Decided by the owner in this session

1. **Purpose (primary)**: a **risk and awareness monitor** for stocks the owner holds: how big a
   normal week is, what is scheduled, what changed, scored over time. No buy/hold/sell verdict.
2. **Usage**: a few holdings, checked about **once a week**.
3. **Retire Agreement and the vote** (Rules 4 and 5), with a fixed sentence saying the brief does not
   predict direction (candidate wording: "This brief does not predict direction"). Approved
   2026-10-11 as the assistant recommended. *Update 2026-10-12: the rule text in `CLAUDE.md` and
   `openspec/config.yaml` was edited in lockstep by `align-rules-with-weekly-brief` (archived). The Agreement
   clause stays in Rule 4 only while the debate verdict is displayed; it is deleted by the change that
   removes the debate surface (C1).*
4. **Fibonacci stays out of the headline.** Approved 2026-10-11 as recommended; it may return later as
   an optional chart layer with its measured excess shown beside it.
5. **Rule 6 (not investment advice) is relaxed for this tool.** Stated by the owner 2026-10-11: the tool
   is for internal use by the investor, not commercial. The rule text, the disclaimer and the tests
   that guard them are not edited; that goes through `/opsx:propose` with the Rule 4 and 5 changes.
   What it does and does not unlock is under "Rules impact". The assistant's flag: if anyone besides the
   owner will use or receive the output, confirm the advice-framing question with the appropriate
   internal team (legal or compliance); this is not legal advice. *Update 2026-10-12: the Rule 6 text and
   the disclaimer were changed by `align-rules-with-weekly-brief` (archived), with the owner's tightening
   (decision 6 below). The guard test for the brief disclaimer copy is written by the change that creates the
   copy (N1). The personal-use premise is still unconfirmed.*
6. **Scope of the Rule 6 relaxation** (decided 2026-10-11, as the assistant suggested): yes to
   (a) plainer wording for the re-read prompt, (b) levels the investor sets as their own stop or
   target, with the tool reporting whether each was reached in band units, and (c) a shorter
   disclaimer. **No** tool-originated buy/hold/sell label, except the tool applying the investor's own
   written rule ("your rule: trim 30% if ... was reached"), never the tool's own opinion. *Revised by the
   independent review (below) and as finally written into Rule 6: no "plain decision-support wording"; the
   investor's own rule text is shown verbatim and labelled as theirs, and the tool's own words are limited to
   reached or not reached and the distance.*
7. **Adjusted levels** (decided 2026-10-11, as suggested): drop the 52-week high and the "one month
   ago" lines. Show the year low only when the price is within a volatility-relative distance of it
   (Rule 3). Any level from before the latest ex-date that is shown is labelled "adjusted". *Superseded by
   the review: the brief shows no pre-ex-date level at all, and v5 to v5.3 show no year low either.*
8. **Foreign-flow snapshots** (decided 2026-10-11, as suggested): yes, store a daily per-stock foreign
   buy/sell snapshot from now on, starting with held tickers plus the existing 30-stock sample, so a
   ticker-specific weekly figure exists later. It cannot be backfilled on the free tier, so starting
   early is the point. It is a small daily job and belongs in the proposal; the weekly brief does not
   depend on it. *Revised by the review to "defer" (cost, no scheduler, vendor analytics, must not use
   `company_feed_log.db`), and every brief draft from v5 on lists foreign flow as deferred. The owner's
   confirmation of the deferral is not recorded in this file, and no proposal below includes the job. Open: as
   the data cannot be backfilled, each week without the snapshot is lost for good, so confirm "defer" or
   scope a small proposal.*
9. Everything below the line "Proposed" is the assistant's suggestion and not yet confirmed, except
   where a later line says it was checked or decided.

## Trigger: the 2026-10-09 SAB report versus 2026-10-08 (measured)

| | 10-07 | 10-08 | 10-09 |
|---|---|---|---|
| Verdict | Bearish lean | Observe | Bearish lean |
| SAB close | 42.85 | 43.00 | 42.90 |
| Technical | RSI 39.6, MACD hist -0.1092 | 41.4, -0.0652 | 40.5, -0.0358 |
| Macro | Bear | Neutral | Bear |
| Band | ±3.0% | ±2.9% | ±2.7% |

- The three closes span 0.35%; the verdict flipped twice. The flip came from the Macro agent's
  relative-performance signal moving from +1.19% to -1.16%. SAB closed 43.85 on 2026-09-11 and
  44.75 on 2026-09-14 (+2.1%); the window start rolled across that jump. If relative performance is
  SAB's return minus the index's, the implied VN-Index window return barely moved (about -3.1% to
  -3.0%). The index series is not in `ohlcv`, so this is an inference.
- Technical stayed "Bear" while its MACD histogram faded toward zero and RSI rose from 39.6; the new
  report shows only "RSI: 40.5".
- Foreign flow is shown at different scales in one report (Macro: -50B of 5,742B gross; News: about
  13,500B for the week and a 9,000B block sale), with the earlier "30 large caps" scope label gone.
- `debate_log.db`: 7 SAB rows (ids 4 to 10); ids 4 to 8 are five re-runs of 2026-10-07; none scored
  (`outcome_status` NULL); the 10-09 row was run 2026-10-10 22:04 UTC. The first scoring is due about
  2026-10-14. A price-only check on the earlier "Caution Signal" of 2026-10-02: close 42.45 to 42.90
  five sessions later (+1.1%), the opposite of the lean, inside the band. One sample.
- Verdict labels are named in the display table `VERDICT_CONFIG` (`frontend/src/lib/debateText.js`);
  the 10-07 log rows store `CAUTION_SIGNAL` while the 10-07 file shows "Bearish lean".

## Why the project feels purposeless

- Three identities in sequence: a direction predictor (XGBoost, retired; correlation 0.0095), an
  LLM debate verdict (being dismantled), and "describe, not vote"
  (`DISCUSSION_describe_not_vote_redesign.md`).
- Footprint versus use (measured 2026-10-11): 24 specs under `openspec/specs/`, 20 archived changes
  plus 3 active, about two dozen scripts under `backend/scripts/`, 599 tickers ingested (208
  modelled). Reports exist only for SAB, VPB and VIB (10 files, 2026-10-02 to 10-09).
- The only validated output is the volatility band (corr about 0.45;
  `DISCUSSION_model_direction.md`). The vote, Fibonacci levels and cross-sectional momentum are
  killed or unproven.

## Role candidates considered

| Role | Question it answers | Evidence |
|---|---|---|
| A. Position risk monitor | How big is a normal week for what I hold, in VND on my size? | Strong (the band) |
| B. Watchlist awareness | What is scheduled, what changed? | Facts only |
| C. "What is unusual today" triage | Where should I look? | Needs new, unproven signals |
| D. Decision journal | Were my rules and the band right over time? | Outcome log exists |
| E. Buy/hold/sell verdict | What should I do? | Contradicted by the repo's own data; barred by Rule 6 |

Chosen: **A + B, with D as the trust mechanism**. C parked. E cut.

## Debate of ideas: four investor personas, two rounds (persona-run)

Personas: long-term holder, swing trader, skeptical quant, novice retail. Each proposed ideas for a
trustworthy headline, then ranked and attacked the pooled list.

**Unanimous**: drop "Bearish lean", "Observe" and "Majority (2 of 3)"; lead with close, band in VND
and the measured band hit-rate; keep Fibonacci out of the headline; stop labels flipping on noise.

**Persona-run figures** (proxies, not production code; unreplicated):
- Quant, sign-count Technical rule approximated from `features`, 541 tickers, 2023 to 2026, 392k
  ticker-days: flips on 14.6% of days, median run 3 sessions, 45% of runs 2 sessions or fewer,
  A-B-A reversals on 2.7% of days.
- Quant, range terciles (20-session sigma over own trailing 252-day median; band = sigma x sqrt 5),
  180 tickers, 131k windows: median |5-session move| 1.70% / 2.17% / 2.56%; top-to-bottom ratio 1.51
  (block-bootstrap 95% 1.42 to 1.61). Proxy band coverage 63.5% / 73.2% / 79.6% across the terciles,
  which may be a trailing-sigma artifact; to be rerun on the production band.
- Trader, proxy band: SAB 2020 windows ended inside 68% and touched the lower edge in 32%; a
  40-ticker pool 72% and 37%.

**Disagreements and the assistant's calls (proposed)**:
- Directional tag: holder no; quant default "no clear directional tilt measured"; trader a stable,
  gated tag. Call: **none in v1**; reopen only after 200+ scored reports with a pre-registered test
  that (hit rate minus base rate) has a confidence interval above zero.
- Range-regime label ("wider / typical / narrower"): holder and trader call it S1 re-opened
  (S1 was KILLED, `DISCUSSION_describe_not_vote_redesign.md`); quant calls it a dispersion claim.
  Call: show a raw band with context, not a three-way label, until rerun on the production band.
- Evidence count ("1 of 3 sources"): novice objected it reads as a score. Call: a plain sentence.
- Fibonacci: all would keep it out of the headline; this sits against the owner's earlier decision to
  apply it. Owner's call.

## Proposed: the weekly check-in brief

Weekly cadence matches the 5-session horizon and removes the daily-flip problem. "Changed since last
report" becomes "since last week"; scoring uses non-overlapping weeks. The unit is the holdings, not
the ticker.

**What to capture for a weekly decision**
- Core: your exposure (shares, cost, P/L, share of portfolio); the band in VND and as % of the
  portfolio; scheduled events in the window (ex-dividend date, AGM, share issues, director deals);
  new company announcements; execution (volume against your size, daily price limit, settlement).
- Slower context: valuation and fundamentals trend; where price sits in its range; market backdrop as
  context, not a vote.
- Recorded by the investor: a one-line thesis, what would change their mind, rules set before the
  week, and last week's outcome. These make the scoring (role D) possible.
- Cadence weakness: a Friday brief is stale by Wednesday. Mitigation is **triggers, not predictions**
  ("re-read before trading if ..."). Manual refresh already exists; alerts are later.

**Boundary**: facts and conditions only. No target, no "buy more", no direction.

**Privacy**: holdings are personal financial data. Keep them local and out of every language-model
prompt. The News agent calls a model, so that boundary needs its own test.

## Simulation: do investors read the brief the way we intend? (simulated)

Method: a fresh agent with no tools and no project knowledge plays an investor holding 1,000 SAB,
reads one brief, and must choose buy more / hold / sell part / sell all. SAB numbers in the briefs
are measured (close 42.90, band ±2.7% = 41.74 to 44.06, 20-session average volume 425,500, 52-week
range 39.34 to 53.42, last ex-dividends 2,000 VND on 2026-01-12 and 3,000 VND on 2026-07-28, no
company item since 2026-08-28). The market lines come from the 10-09 report. The control is the
current report format with the same position and the 42.90 close.

**Round 1 (cost 41.80)**: new brief v1 and current report both hold. Old-format reader: anchored on
cost; ignored all indicators; "[ticker]" and "[sector]" read as a template bug; "Majority" read as
expert agreement; the "-50B vs 13,500B" foreign flow read as contradictory. New-brief reader: drove on
"no company news / no event / no measured ability to call direction" and the volume line; liked the
"re-check before trading" line best. Both set their exit at about 41.7, which is the band's lower
edge and also their cost (a coincidence in this scenario that anchors on breakeven).

**Round 2 (v2 brief, four scenarios, new format versus control)**

| Scenario | Current report | New brief v2 |
|---|---|---|
| S1 cost 46.00 (-6.7%) | Hold; anchored on "get back to 46" | Hold; same anchor |
| S2 cost 38.00 (+12.9%) | Hold; itch to sell 300 | Hold; itch quieted |
| S3 ex-dividend Wed 10-14, 2,000 VND (hypothetical) | **Sell 300**, unaware of the dividend; drivers: "Bearish lean", "2 of 3", 13,500B foreign selling, the unattributed 9,000B block sale | **Hold**; the ex-date line reframed the week |
| S4 close 40.90, outside last week's range (hypothetical) | Hold, "more nervous" | Hold; "last week's range did not contain this move" stung |

Findings: the verdict caused worry and was never a decision driver in the new-format runs; the
calendar fact changed the decision only where there was a fact (S3); the other cells mostly reinforced
holding. Readers wrote their own stop-like levels from the band edge or the 52-week low even though
the wording said "a prompt to re-read". The v2 brief's defects: the band excludes the ex-dividend
price drop, so the re-read prompt would fire on Wednesday from the dividend alone and P/L would show a
loss despite cash received; "typical range" read as a safe zone; the market paragraph still scared;
fees and tax, Q3 timing and "why did it fall" were asked for repeatedly; jargon.

**Round 3 (v3 brief, same four scenarios, new format only; template in the appendix)**: all four
hold. What v3 fixed:
- The dividend-aware lines worked: in S3 the reader did not sell before the ex-date and wrote the rule
  "I won't sell on Monday just because ex-dividend day dropped the price".
- Showing dividends received turned "I'm losing" into "slightly ahead" (S1, S4).
- The market line was no longer scary; two readers deleted it as unactionable.
- Three of four self-written rules were "re-read at the weekend", not "sell"; one (S4) was
  "re-read and sell 500 if close below 39.34".
What v3 broke or left open (4 of 4 readers flagged the first):
- **Three frequencies that do not reconcile**: "about 1 week in 3 goes beyond" (nominal), "23 of 104
  weeks" (about 1 in 4.5, measured, but against today's ±2.7% rather than the band set each week), and
  "70 to 74% inside". Use one frequency per concept.
- Two ranges (usual swing 2.7% versus ±2.9% next week; shifted range after the ex-date) and "0.4 times
  the usual swing" as jargon.
- "Before tax", "not set" and "list may be incomplete" left readers unsure what they actually hold;
  one said they "mentally rounded it up", so the dividend total can bias optimistic if the feed is
  incomplete.
- The 52-week high (53.42) and "one month ago" generated regret ("I missed selling at 53").
- The band's upper edge was read as a target (S2) and "closes outside the range" was ambiguous (any
  day or Friday?).
- Still wanted: why the price fell from 53 to 43 or "2.5 times the market"; valuation or dividend
  yield; Q3 expectation; payment date; a note that price-only P/L will show a loss after the
  ex-date while the total does not.
- Price levels "look odd" (39.34, 53.42 are not board-style quotes): consistent with the series being
  dividend-adjusted (confirmed later; see "Checks run 2026-10-11").

**Round 4 (v4 brief, same four scenarios, new format only, with a 5-question comprehension quiz;
template in Appendix B)**: all four hold again (so v2, v3 and v4 gave 12 holds out of 12 in the new
format; this is not a discriminating test of the action). v4 changes: one frequency ("2 weeks in 3"),
one range with a dated shift for the dividend, the total shown as conditional ("if that list is
complete"), "small week / large week" wording, and the 52-week range, volume and by-period hit-rate
moved to a Details line.
- **Quiz: 20 of 20 answers correct** (about 3 weeks in 10 go beyond the range; no direction claim; the
  range ends are not targets; the total and what it depends on; a small week / the ex-dividend drop
  is normal / a missed range is not a malfunction). The v3 frequency conflict is gone. The quiz is
  open-book and the reader is the same model that wrote the brief, so this overstates real
  comprehension; a human check is still needed (3-question protocol: "up or down this week?",
  "where could the price be in a week?", "do you need to do anything today?").
- **S3 worked**: the reader derived "42.90 minus 2.00 = 40.90, inside the shifted range 39.74 to
  42.06", and dropped an itch to "buy before Wednesday to catch the dividend" because the price falls
  by the dividend.
- **S4 worked in part**: "a miss is expected sometimes" removed the "tool is broken" reading, but "only
  7 of 104 weeks moved this much" spiked stress for a minute (it had read as calming in v3).
What is still wrong or new (counts are of four readers):
- **By-period hit-rate line (61 to 62% versus 70 to 74%) is ignored or confusing (4 of 4)**, even
  though the headline frequency was understood. Candidate: remove it from the brief and keep it in
  the report details or `MODEL_CARD.md`. The by-year disclosure's placement needs Rule 4 sign-off
  (already an open item in `DISCUSSION_describe_not_vote_redesign.md`).
- **Dividend data looks suspicious (2 of 4)**: "since purchase" (bought about 16 months ago) equals
  the "last 12 months" figure exactly, so an earlier dividend looks missing. Show the period the source
  covers ("complete from <date>") instead of a bare "may be incomplete".
- **Dividend yield line nudges buying (1 of 4; "12% sounds too good to trust", another "tempted to buy
  more because it is near the year low and dividends are 12.2% of price")**. Candidate: show amounts,
  not a trailing yield percentage.
- **After-tax net is still the most-wanted missing fact (4 of 4)**; "rates not set" gives nothing to
  act on. Needs a one-time settings step with rates the owner has verified, not assumed (readers'
  guesses of 5% dividend tax and so on are unverified).
- **Totals as % of cost** (2 of 4 computed it themselves) and **a likelier Q3 date** (3 of 4).
- **Year low and high**: 52-week high and "one month ago" still produced regret ("feel 20% down",
  "wince that I didn't sell then", 2 of 4). The year low mattered to the reader near it (S4) but sat in
  Details. Candidates: drop the high and the month-ago line; surface the low only when the price is
  within a volatility-relative distance of it (Rule 3).
- **Range meaning versus trigger (1 of 4)**: the range describes where the price could be at the end of
  the week, but the re-read prompt fires on "any day's close outside". The path touches a band edge
  more often than the end point does (trader persona's proxy: lower edge touched in about 32 to 37% of
  windows), so this prompt may fire often. Measure its trigger rate before shipping it; if it fires in
  many weeks it is noise.
- **"These readings have not shown a measured ability to tell" (1 of 4)** reads as the tool admitting it
  is useless. Candidate wording: "This brief does not predict direction"; the Rule 4 sign-off covers it.
- Two headline numbers pointing in opposite directions (-6.7% price, +1.90M total) were resolved by
  trusting the green one in all four readers. The dividend-inclusive total changes how the reader feels
  (every reader said so), so lead with it only when the dividend history is verified complete.

## Proposed changes, in order

**Superseded (2026-10-12).** This is the first-pass plan, written before the review and the v5 to v5.3 drafts.
The current plan is the table in "Status record (2026-10-12)" at the end of this file; what became of each item
here is recorded there under "Items from this early plan".

1. **Headline block**: close, band in VND, measured band hit-rate (by-year detail below the fold), the
   fixed sentence "these readings have not shown a measured ability to call direction", news and
   calendar as plain sentences; drop Agreement, "Observe" and "lean". This is the "describe, not vote"
   design the owner already chose, with specifics.
2. **Stability**: make Macro thresholds volatility-relative (also closes a Rule 3 gap) and fix the
   window-start sensitivity of the relative-performance signal; add "changed since last week".
   Candidate acceptance tests (from the quant persona, to be fixed in a design before any run): flip
   rate below 3% per day, median run at least 10 sessions, A-B-A under 0.5%, unchanged label on 95% of
   replayed days under a 0.35% price perturbation.
3. **Company calendar line** with "feed returned nothing" worded differently from "nothing found";
   Q3 timing from last year's filing date (feed: Q3 2025 explanation filed 2025-10-28).
4. **Holdings input** (ticker, shares, cost, purchase date; local only), dividend-aware P/L, price-only
   first and the total labelled "if the dividend list is complete"; user-entered selling-cost rates.
5. **Scoreboard** hidden until 30+ scored reports; dedupe re-runs first (5 duplicate rows for
   2026-10-07).
6. **Defer**: band touch-rate, Fibonacci, regime label.

## Rules impact

| Rule | Effect |
|---|---|
| 1 horizon | Unchanged; weekly cadence fits |
| 2 no raw log return | Unchanged; show simple % |
| 3 volatility-relative thresholds | Macro's fixed thresholds (1 point, 0.5%) are in tension; the "unusually large move" prompt and any trigger must be volatility-relative |
| 4 reliability measured | Agreement retired needs sign-off; the "no measured ability to call direction" sentence is worded without a number because only the range hit-rate is an allowed reliability figure; one frequency per concept |
| 5 provenance labels | Names change if Technical stops voting and Macro becomes context; model-written text stays marked |
| 6 not advice | **Relaxed by the owner for internal use (decision 5).** Unlocks: plain decision-support wording, a shorter disclaimer, and levels the investor sets as their own stops and targets. Does not change: there is still no measured directional edge, so any tool-originated buy/hold/sell label would be an unscored claim (Rule 4's "measured, never asserted" stands on evidence, not on legality). The upper band edge was read as a target (S2), a usability problem that survives. Tests that guard the old wording (`TRANSACTION_VERBS` in `backend/tests/test_debate_export_api.py`, the verbatim disclaimer copies) and the specs would need editing |

`CLAUDE.md` and `openspec/config.yaml` carry the rules word for word; change both together.

*Update 2026-10-12: rows 4 to 6 were applied by `align-rules-with-weekly-brief` (archived). Still to do from
this table: narrow the `TRANSACTION_VERBS` guard and add the brief-disclaimer guard (N1); the Macro threshold
gap in row 3 matters only while the debate verdict is displayed (C1).*

## Checks run 2026-10-11 (decisions 4 and 7; measured, read-only)

**Stored prices are dividend-adjusted.** Method: for each SAB cash-dividend ex-date in the company feed
that falls on a stored trading day (17 of 18), compare that day's open with the previous close, against
the drop expected if prices were raw (dividend over previous close). Result: the average gap is +0.2%
against an expected -3.5%. The gap is near zero on every date, for example 2026-07-28 (-1.4% against
-6.9% expected), 2025-06-30 (0.0% against -7.0%) and 2026-01-12 (+0.6% against -4.6%). Only 2023-03-02
(-1.5% against -1.4%) looks like a raw drop, and it is the smallest dividend that matches. So the
stored history is back-adjusted.
- Returns, the band and the outcome scoring therefore run on dividend-adjusted prices. The band
  excludes the ex-dividend price drop, so a window that contains an ex-date needs the shift note drafted
  in the v4 template.
- Consequence (not measured): levels from before the latest ex-date, such as the 52-week high (53.42) and
  any comparison with a purchase-date price, are adjusted figures that sit below what the board showed
  then. Bars after the latest ex-date (here after 2026-07-28), including the 42.90 close, are board
  prices.
- `load_ticker` (`backend/app/services/ticker_ingestion.py`) fetches history from 2000-01-01 on every
  load. **Corrected by the independent review below**: `UPSERT_OHLCV` is `ON CONFLICT DO UPDATE`, so
  every row in the fetched window is rewritten (re-adjusted); the earlier statement here that
  "stored history is mixed until a refresh" was wrong. The precise risk is in "Independent review".

**Company feed coverage** (`backend/data/company_feed_log.db`, SAB):
- **Dividend history is complete and dated.** 18 cash-dividend events, ex-dates 2018-01-15 to
  2026-07-28, each with record date, payout date and VND per share (for example ex 2026-07-28, record
  07-29, payout 2026-08-28, 3,000). So the payment date is available once a dividend is announced. One
  share-issue event (2023-09-14).
- **Correction to the v3 and v4 briefs.** They listed only 2,000 (ex 2026-01-12) and 3,000 (ex
  2026-07-28) as "dividends since purchase" for a purchase on 2025-06-10. The feed also has 3,000 VND ex
  2025-06-30 (payout 2025-07-31), so the since-purchase total in that scenario is 8.0M, not 5.0M. The
  simulated readers who noticed that "since purchase" equalled "last 12 months" were right; the brief
  was wrong, not the feed.
- **Coverage cap.** The vendor returns at most 50 rows per call. SAB's 50 event rows reach back to
  2017; VPB's reach back only to 2022-07-19. When 50 rows are returned, the oldest event date is where
  reliable coverage starts, and a holding bought earlier has an incomplete history. That is the "covered
  period" the brief should state.
- **No earnings calendar.** Event codes for SAB: DIV (18), AGME (9), EGME (1), insider and
  major-shareholder trading DDINS / DDIND / DDRP (9 / 5 / 4), ISS (1), OTHE (2), AIS (1). So the Q3
  timing can only come from last year's filing item (news 2025-10-28, explanation of Q3 2025 profit
  variation); "date not announced; last year's was <date>" is as good as the data gets.
- **Per-stock foreign flow is a latest-session snapshot only.** `macro.py` fetches foreign buy and sell
  value per stock from VCI's price board and notes that vnstock's free providers implement no
  foreign-trade history. SAB is already in `FOREIGN_FLOW_SAMPLE`. A SAB-specific weekly figure would need a
  daily snapshot stored from now on; it cannot be backfilled on the free tier. This comes from the code
  comments, not a live probe today.

## Independent review of the recommendations (2026-10-11; four reviewer agents)

Four fresh agents (behavioural and UX; engineering feasibility with code and data checks; risk and
privacy; product contrarian) received the doc and the recommendations, read-only, and were told to
challenge. They are the same model family as the author, so shared blind spots remain. The engineering
and behavioural reviewers ran their own measurements (persona-run: proxy bands, overlapping windows).

| Recommendation | Verdict | Key point |
|---|---|---|
| Rule 6 scope (decision 6) | MODIFY | "Plain decision-support wording" is undefined and the likeliest back door for a verdict: drop it. Label every stop or target "entered by you on <date>". A "stop reached" report formalises the cost and band-edge anchoring readers already showed, so show how often a level that far away is touched. Keep `TRANSACTION_VERBS` on tool text and render the investor's own rule as a separate verbatim block. Do **not** relax: the CONFIDENCE ban, provenance labels and the model-text note, `withhold_advice` (also the injection backstop), and the "about 2 in 3" wording in any shortened disclaimer. |
| Adjusted levels (decision 7) | MODIFY | Show **no** pre-ex-date level at all. "Year low when near" is one-sided framing (the near-low reader was "tempted to buy more"), and "adjusted" is jargon. |
| Foreign-flow snapshots (decision 8) | REVISE to defer | Real cost: about 150 lines plus tests plus an OpenSpec change; it needs a daily job after 15:15 ICT (mid-session values read -9% against -24% final) and the repo has no scheduler, so a missed day is unrecoverable; it must not go in `company_feed_log.db` (a test asserts its exact tables); vnai's analytics posts function arguments (tickers) to the vendor. The brief does not depend on it. |
| One frequency, by-period detail moved out | AGREE, with a fix | The v4 template still stated three frequencies ("2 in 3", "1 in 3", "3 weeks out of 10"), so the doc's claim of one frequency was wrong. Remove the "misses in about 3 weeks out of 10 ... does not mean the tool is broken" sentence: it is a third number and a sedative. |
| Drop yield; verify dividend coverage | AGREE, rule fails | The "50-row cap" coverage rule fails at: announcement-to-ex lag up to 85 days (SAB announced 2022-12-07, ex 2023-03-02), ties on the boundary day, and "under 50 rows means full history" (unsupported). Stock events (`ISS`; SAB 100% bonus ex 2023-09-14, VPB 26.04% stock dividend ex 2026-09-24) change share count and cost basis, so a dividend-inclusive total is unsafe. |
| Re-read on "any day's close outside the range" | **REJECT** | See the measurements below: it fires about 1 week in 3 per stock. |
| Rank sentence ("only 7 of 104 weeks") | Drop | n = 7 and it stressed a reader; keep "last week's range held / did not hold". |
| Cut list | Ranked, do not spec-chase | See below. |
| Purpose and weekly cadence | AGREE, with kill criteria | "Worth a weekend, not worth another month." |

**Trigger measurements (persona-run, proxy band, not the production band)**: SAB, fixed ±2.7%, 748
overlapping windows since 2023-10: an any-day close outside the range in 42% of windows against 29% for
the week-end close. Twelve tickers (SAB, VPB, VIB, FPT, VNM, HPG, MWG, VCB, PVD, KBC, DPM, SSI), weeks
ending 2023-10 to 2026-09, n = 1,792, band = 20-session stdev x sqrt 5: week-end / any-close outside
27.0% / 37.7% (k = 1.0) and 21.1% / 29.5% (k = 1.19, the production multiplier). At least one of SAB,
VPB, VIB fires in 68% of weeks (k = 1.0) and 59% (k = 1.19). Any close beyond 1.5 times the k = 1.19
band: 13.4%; beyond 2 times: 6.7%. Caveats: proxy band, standard error about 3.7 points per ticker,
market-correlated weeks, one regime period. Decision: the brief compares the week-end close with the
issued range, and mid-week prompts are limited to new announcements and the investor's own levels.

**Corrections to earlier statements in this doc**
- A refresh rewrites every fetched row (`ON CONFLICT DO UPDATE`); rows older than the fetched window are
  untouched. The precise risks: `score_debates` reads `close_asof` and `close_t5` from the current
  `ohlcv`, so the scored move excludes the dividend whenever an ex-date falls in (as_of, t5], while the
  logged `close_at_asof` stays on the old basis; and after a refresh the printed close and levels of an
  issued brief sit above the new adjusted history, which can give false "reached" results for own
  levels. Fix: the brief logs its own issued close, band and levels and compares in return space (or
  only bars after the last ex-date). A refresh of every held ticker before each run is mandatory: 9 of
  12 sampled tickers ended at 2026-09-07.
- The band's "validated asset" is weaker than stated. `openspec/changes/archive/2026-10-07-calibrate-volatility-range/design.md`
  records the HAR band's out-of-time correlation with realised volatility at 0.431 against 0.424 for a
  plain `log(rv20)` baseline (0.432 against 0.423 on the 2024 test set), and the first walk-forward run
  was refused by the baseline gate (pooled 0.4500 against 0.4533), described there as "indistinguishable
  out of time on this history". So the band is volatility clustering that a trailing standard deviation
  reproduces; use the existing range service because it exists and is calibrated, not because it is
  special.
- Own-level checks on adjusted prices are not safe in VND space after an ex-date (see above).

**Smallest v1 and kill criteria (contrarian reviewer; assistant concurs)**
- One script, run on Friday, reading a small holdings file (ticker, shares, cost). Per holding: close,
  the week's % move, next week's band in VND per share and on the shares, the ex-dividend shift and
  payout date when an ex-date is in the window, ex-dates, AGMs, share issues and announcement titles
  from the feed already ingested, the investor's own stop or target with reached / not reached, "last
  week's range held / did not hold", one fixed "does not predict direction" sentence and the short
  disclaimer. Not in v1: verdict, Agreement, agents, model-written text, macro, Fibonacci, 52-week
  levels, yield, tax and fees, dividend-inclusive totals, scoreboard, frontend. Output is a markdown file
  or the terminal.
- Kill criteria after 4 weeks of real use: (1) the owner cannot name one week where the brief surfaced
  something the broker app and its notices did not, or opened it unprompted in fewer than 3 of 4 weeks;
  (2) over the modelled tickers the band is no better than a constant ±2.5% range or a trailing
  20-day-stdev band (the repo's own numbers above suggest it may already be no better).
- Do not spend weeks on specs and rule-edit proposals to delete old parts; stop displaying them and
  delete after the 4 weeks if the brief survives. The reviewer counted 80 commits, 37 in the last 2
  days, against 10 report files and 10 debate-log rows: building outruns use. Fee and tax setup, Q3-date
  guessing, yield, a regime label, foreign snapshots and acceptance tests for a vote already being cut
  were flagged as scope creep.

**Cut list, ranked safest first (engineering reviewer; dependencies read from the code)**
1. Delete `data/models/pooled_xgb_model.json` (gitignored, unused). Keep `app/ml/training.py`:
   `feature_rows.py` takes `FEATURE_COLUMNS` from it and `api/tickers.py` uses `TRAINING_TICKERS`.
2. Experiment scripts to notebooks (Fibonacci, cross-sectional momentum with 2 tests and 1 spec,
   baseline diagnostics, `probe_advice_language`, `verify_*_claims`, `measure_*`); keep
   `evaluate_vol_range`, `evaluate_band_coverage_by_regime`, `train_har_rv`, `score_debates`.
3. Stance chips, `DebateMatrix`, `VerdictPanel` (about 2,600 frontend lines plus tests); rehost
   `RangeBlock`, keep `lib/verdictState.js` (imported by `useTickerContext`).
4. Macro as a voter (a 5-line change; keep the context lines). 5. The Technical vote (`technical.py`
   also carries band evidence into the log).
6. Engine, synthesiser, runner, LLM client, export (about 2,170 backend lines). Entangled: `debate_log`
   has `verdict` and `eligible` NOT NULL and `outcome_log.py` imports engine types, so a band-only
   writer is needed first; `news_feeds.py` must stay (imported by `data_eligibility.py` and the company
   feed); `main.py` imports the runner; `test_debate_export_api` and `test_domain_rules_in_sync` guard the
   old wording. Cutting the News agent also removes the only LLM caller.

**Risk and privacy (not legal advice)**
- **Biggest unnamed risk: the "personal use" premise is unverified and carries Rule 6, the vendor
  licence and data confidentiality at once.** This session runs under organization-level instructions,
  the git identity is a personal address, `claude_cli` uses "the user's Claude login" whose account type
  is unknown, and vnstock 4.0.5 is licensed "personal, research, non-commercial" while
  `company_feed_log.db` is marked not to be shared. Confirm the account and machine ownership, and
  confirm with legal or compliance before anyone else receives the output or it runs on employer
  equipment or accounts.
- `reports/` is built for NotebookLM ingestion (README, `debate-report-export` spec), i.e. designed to be
  uploaded to a third party. Keep the brief out of `reports/`, and keep the full disclaimer on anything
  exported.
- Holdings are personal financial data. `.gitignore` covers only `reports/*.md` and `data/*.db*`; a
  `holdings.*` file under `reports/`, `backend/` or `backend/data/` is **not** ignored. Minimum: the file
  outside the repo (for example `~/.config/<app>/`, directory mode 700, file mode 600) plus a `holdings*`
  line in `.gitignore`; never in `app.db` (rebuildable, and tests run against the real DB); never through
  the API (unauthenticated, no Host check). The v1 script imports no language-model client, so no leak
  path exists there; an import-scan test is the cheap guard if that changes.
- vnai's analytics (reviewer's reading of the code, traffic not tested) posts function arguments
  (tickers), a machine fingerprint and a commercial-usage probability to the vendor, so daily
  held-ticker calls would reveal the held set. Holdings typed into dev sessions, IDE context or agent
  memory leave the machine whatever the code does.
- Third-party text (announcement titles, headlines): the existing `_clean` and `fence` leave unclosed
  tags, markdown links and `|` intact; React escapes them, but markdown export, NotebookLM or an HTML brief
  do not. Feed items are stored to 500 characters with the source link kept unchecked. Any future model
  summary needs the same fence, cap and `withhold_advice`.
- `backend/.env` exists with mode 644; contents not read. Check it holds no secret that another local
  user could read.

**The test cannot discriminate** (behavioural reviewer): the control also held in S1, S2 and S4; only S3
changed the action, and it had a real calendar fact; the author and the reader are the same model and
the quiz is open-book. Cheap discriminating scenarios: (a) the investor's own written rule ("trim 30% if
close below 41.74") is triggered by the close, so a good brief reports the rule hit and the reader
follows it; (b) the v4 brief with versus without its reassurance lines, to see whether the sedative
overrides a pre-commitment; (c) a material filing (stake sale, share issue) against a routine AGM
notice, where only the first should change the action.

**Behavioural gaps the reader simulations missed** (behavioural reviewer): reassurance sedation (every
conditional resolves toward holding); cost anchoring and a "total" that resets the reference point;
overconfidence from two-decimal precision with no tail line; narrow framing (per ticker, no portfolio
view; "share of portfolio" was dropped from v4); absence read as evidence ("no announcement found" while
the feed's last item was 2026-08-28 and coverage is partial). Suggested: remove the sedative sentence,
add one portfolio line, and state when the feed was checked and the date of its latest item.

## Open questions for the owner

*Update 2026-10-12: the list below was written before v5 to v5.3 and is kept as written. Where it stands now:
**resolved** are the revisions to decisions 6 and 7 (in the Rule 6 text and v5 to v5.3), one frequency ("about 2
weeks in 3"; the by-period hit-rate line is not in the brief from v5 on), dropping the yield, the re-read
trigger (week-end close against the issued range; mid-week prompts only for announcements and the investor's
own levels), fee and tax (not in the brief; no verified rates), the own-rule field (a holdings file outside the
repo; the journal is the issued-brief log) and the cut list (now C1 and C2). **Still open** are the
personal-use premise, the decision 8 deferral, how dividend completeness is established (the net line is shown
only when the list is complete; the rule itself is unverified), and the v1 scope and kill criteria, which the
status record carries forward.*

- Confirm the revisions the review proposes to decisions 6, 7 and 8 (drop "plain decision-support
  wording"; show no pre-ex-date levels at all; defer the foreign-flow snapshot), and the v1 scope and
  kill criteria above.
- Confirm the "personal use" premise (account, machine, vendor licence) before relying on the Rule 6
  relaxation; see the risk notes.
- One frequency policy: which single number does the brief show (the band's measured hit-rate for the
  ticker, or the pooled one)?
- Where does the by-period hit-rate disclosure go (it confused 4 of 4 readers in v4)?
- Drop the trailing dividend-yield percentage?
- How is dividend completeness established per holding (the covered period), and what does the brief
  say when the purchase predates it?
- What does the re-read prompt compare against (weekly end point, or any day's close), and what
  trigger rate is acceptable?
- Fee and tax setup: how does the investor enter rates, and who verifies them?
- Where does the investor's own-rule field and outcome journal (role D) live, and is it local only?
- Cut list (candidates, dependencies unchecked): debate engine and synthesiser, Macro as a voter,
  Technical vote (maybe a plain "price state" line), stance chips, retired XGBoost serving path,
  experiment scripts moved to notebooks.

## Not verified

- Vendor adjustment lag after an ex-date, and whether tickers other than SAB and VPB are adjusted the
  same way (the review saw no gap for SAB's 2023-09-14 bonus issue or VPB's 2026-09-24 stock dividend).
- The implied VN-Index window return (index not in `ohlcv`).
- Persona-run figures above use proxies and were not rerun on production code.
- Whether `score_debates.py` dedupes re-run rows, and whether the debate log would double-count them.
- HOSE price limit and settlement rules, dividend tax and selling tax and fees: not looked up; confirm
  with the broker.
- Whether the feed's dividend history is complete for tickers other than SAB (VPB's event rows reach
  back only to 2022-07-19 because of the 50-row cap), and whether the foreign-flow statement in
  `macro.py` still holds on the live vendor.
- Real investor behaviour: all reader results are role-played.

## Reproducing (measured items)

All read-only: `sqlite3 -readonly backend/data/app.db`.
- Closes: `select date, close from ohlcv where ticker='SAB' order by date desc limit 14;`
- Weekly move counts (104 weeks of Friday-to-Friday closes from 2024-10-01, grouped by `%Y-%W`, last
  trading day of each group): 7 weeks with |move| at or above 4.7%, 23 at or above 2.7%.
- 20-session average volume 425,500; 52-week range from `high`/`low` since 2025-10-10: 39.34 to 53.42.
- Company feed: `backend/data/company_feed_log.db`, table `company_feed_item`, ticker SAB; last news
  2026-08-28; Q3 2025 explanation item 2025-10-28.
- `backend/data/debate_log.db`, table `debate_log`: SAB rows by `as_of`, `run_at`, `verdict`.
- Adjustment check: attach `company_feed_log.db` to `app.db`; take SAB `event_code = 'DIV'` rows
  (`$.exright_date`, `$.value_per_share`), join the `ohlcv` row on that date, and compare
  `open / previous close - 1` with `-dividend / previous close` (prices are in thousand VND, so divide
  VND per share by 1,000).
- Feed coverage: group SAB `kind = 'events'` rows by `$.event_code`; list the `DIV` rows with
  `$.exright_date`, `$.record_date`, `$.payout_date`, `$.value_per_share`.

## Appendix: brief v3 template (hypothetical position inputs)

```
WEEKLY CHECK · <TICKER> · <Friday> close · for the 5 trading days <Mon> to <Fri>

YOUR POSITION (your entries: <shares>, bought <date> at <cost>)
Price now <close>, so your shares are worth <value>.
Gain/loss on price: <amount> (<pct>).
Cash dividends since purchase found in the company-announcement source: <amount>
  (<per-share, ex-dates>), before tax. The list may be incomplete.
Total so far: <amount>, before selling fees and tax. Your selling-cost rates: <not set | set>.

THIS WEEK'S MOVE
<ticker> went <prev> -> <close> (<pct>), about <x> times the usual weekly swing.
Lowest / highest price in the last year: <lo> / <hi>.

WHAT A NORMAL NEXT WEEK LOOKS LIKE
<ticker> usually moves within ±<band>% over 5 trading days: about <lo> to <hi> per share
(about ±<amount> on your shares). About 1 week in 3 goes beyond a range like this; that is normal.
This range says nothing about direction. These readings have not shown a measured ability
to tell whether the price will rise or fall.
[Dividend effect, only when an ex-date is inside the window: the range above excludes the
ex-dividend drop; from <ex-date> the same range shifted down by the dividend is <lo> to <hi>.]

COMPANY
Coming in the next 5 trading days: <events | nothing found | feed returned nothing>.
Q3 results: <date | not announced>. Last year's was filed on <date>.
New announcements since last week: <titles with dates | none; latest was <date>>.

WHY DID THE PRICE MOVE?
<No <ticker>-specific announcement or headline found | what was found>. <Relative to the market,
measured, if available.> Market summary (written by a language model; whole market, not <ticker>).

YOUR RULES
<none set | the investor's own rule>. Next week's brief shows whether it happened.
Re-read this brief before trading if: a new announcement appears; the price closes outside the range
above; or your own rule triggers. This is a prompt to re-read, not a price to sell at.

DETAILS
How often the real weekly move stayed inside a range sized like this, by period (measured; an
estimate, not a promise).
Technical observation, not investment advice. [full disclaimer from docs/DISCLAIMER.md]
```

v3 problems to resolve before reuse: the three frequencies, the two ranges, the "x times" jargon, the
52-week high, the "closes outside" ambiguity, and the optimistic dividend total. Superseded by
Appendix B.

## Appendix B: brief v4 template (supersedes v3; hypothetical position inputs)

```
WEEKLY CHECK · <TICKER> · <Friday> close · for the 5 trading days <Mon> to <Fri>

YOUR POSITION (your entries: <shares>, bought <date> at <cost>)
Price now <close>, so your shares are worth <value>.
Price gain/loss: <amount> (<pct>).
  [Only when an ex-date is inside the window: After <ex-date> this will fall by about the dividend
   (<per share>) while the dividend arrives as cash, so your total stays about the same.]
Dividends paid since purchase, per the company-announcement source: <amount> (before tax).
  This list may be incomplete.
Total if that list is complete: <amount>. Not included: selling fees and tax (<your rates are not set>).

THIS WEEK
<ticker> moved <pct> (<prev> -> <close>): a <small | large> week for <ticker>.
  [Large week only: only <n> of its last <m> weeks moved this much or more. Last week's range
   (<lo> to <hi>) did not contain it. A range like this misses in about 3 weeks out of 10, so a miss
   is expected sometimes; it does not mean the tool is broken. <Relative to the market, measured.>]

NEXT WEEK'S USUAL RANGE
About <lo> to <hi> per share (±<band>%; about ±<amount> on your shares).
  [Ex-date inside the window: ... until <day before>. From <ex-date>, the whole range moves down by
   the dividend: about <lo> to <hi>.]
In about 2 weeks out of 3 the real move stays inside a range like this; in about 1 week out of 3 it
goes beyond it, up or down. That is normal.
The ends of the range are not targets or prices to act on. The range says nothing about whether the
price will go up or down; these readings have not shown a measured ability to tell.

COMPANY
Coming in the next 5 trading days: <events | nothing found>.
Q3 results: <date | not announced> (last year's were filed <date>).
New announcements since last week: <titles with dates | none; latest <date>>.
Dividends in the last 12 months per the source: <per share, dates>, if the list is complete.

WHY DID THE PRICE MOVE?
<No <ticker>-specific announcement or headline found this week. | what was found.>

YOUR RULES
<none set | the investor's rule>. Before the week starts you may write one (for example: "If ___
happens I will re-read this brief first, then decide"). Next week's brief shows whether it happened.
Re-read this brief before trading if: a new announcement appears, any day's close is outside the
range above, or your own rule triggers.

DETAILS
Lowest / highest price in the last year; your shares as a share of average daily volume; by-period
band hit-rate (measured on price history, across stocks; an estimate, not a promise).
Technical observation, not investment advice. [full disclaimer from docs/DISCLAIMER.md]
```

v4 problems to resolve before reuse are listed under "Round 4" above: remove or relocate the
by-period hit-rate, show the dividend source's covered period, drop the yield percentage, supply
verified fee and tax rates, add total as % of cost, surface the year low only when near it and drop the
high and month-ago lines, measure the re-read trigger rate, and reword the "not shown a measured
ability" sentence. Superseded by Appendix C.

## Appendix C: brief v5 (draft; first read by simulated readers in Appendix D)

Built from the independent review above: one script, one frequency, week-end comparison only, no
dividend-inclusive total, no pre-ex-date levels, no model text, the investor's own levels labelled as
theirs. Wording inside `<>` is a placeholder. The size words are provisional and volatility-relative
(Rule 3): "small" below 0.5 times the band, "large" at 1.5 times the band or more, "usual" between.

```
WEEKLY CHECK · <Friday date> · covers the next 5 trading days (<Mon> to <Fri>)
Prices refreshed <timestamp>; last bar for every holding is <date>.   [warn per holding if older]
This brief does not update during the week. It does not predict direction.

HOLDINGS LISTED (<n>): <ticker> <pct>% of their value, ...
If every holding moved to the edge of its own range in the same direction, the listed holdings would
move about <y>% (an upper bound, not a forecast).

--- <TICKER> · <shares> shares · cost <cost> (entered by you on <date>) ---
Close <close> · value <value> · gain/loss against your cost <amount> (<pct>), price only; dividends
are not included.
This week: <pct> (<prev> -> <close>), a <small | usual | large> week for <ticker>.
Last week's range (<lo> to <hi>): <held | did not hold>.   [first brief: no previous range]

NEXT 5 TRADING DAYS
Usual range: about <lo> to <hi> per share (±<band>%; about ±<amount> on your <shares> shares).
About 2 weeks in 3 stay inside a range like this; the others go beyond it, with no upper limit.
[Ex-date in the window: Ex-dividend <date>, <per share> per share. From that day the whole range moves
 down by the dividend: about <lo> to <hi>. Record date <date>; payout <date | not announced>.]
[Share issue in the window: your share count and cost change on <date>; update your entries.]

COMPANY (company-announcement source checked <date>; latest item <date>)
Scheduled: <ex-dates, AGMs, share issues in the window | none found>.
New since the last brief: <titles with dates, original language | none>.
Last dividend: ex <date>, <per share>, paid <date>.

YOUR LEVELS (entered by you)
<stop <level>, entered <date>: reached | not reached; <pct> from the close> | none set.

Look again before trading if: a new announcement for a holding appears, or one of your levels is
reached. Re-run this brief to refresh.
Technical observation, not investment advice. Figures can be wrong or incomplete. "About 2 weeks in 3"
is an estimate from price history, not a promise.
```

**Filled example** (real SAB market numbers for the Friday 2026-10-09 close; the holding and the level
are hypothetical):

```
WEEKLY CHECK · Fri 2026-10-09 · covers the next 5 trading days (Mon 10-12 to Fri 10-16)
Prices refreshed <timestamp>; last bar for every holding is 2026-10-09.
This brief does not update during the week. It does not predict direction.

HOLDINGS LISTED (1): SAB 100%.
If every holding moved to the edge of its own range in the same direction, the listed holdings would
move about 2.7% (an upper bound, not a forecast).

--- SAB · 1,000 shares · cost 41.80 (entered by you on 2026-10-02) ---
Close 42.90 · value 42.90M VND · gain/loss against your cost +1.10M VND (+2.6%), price only; dividends
are not included.
This week: +1.1% (42.45 -> 42.90), a small week for SAB.
Last week's range: no previous range (first brief).

NEXT 5 TRADING DAYS
Usual range: about 41.74 to 44.06 per share (±2.7%; about ±1.16M VND on your 1,000 shares).
About 2 weeks in 3 stay inside a range like this; the others go beyond it, with no upper limit.

COMPANY (company-announcement source checked 2026-10-11; latest item 2026-08-28)
Scheduled: none found.
New since the last brief: none.
Last dividend: ex 2026-07-28, 3,000 VND per share, paid 2026-08-28.

YOUR LEVELS (entered by you)
Stop 41.00, entered 2026-10-02: not reached; 4.4% below the close.

Look again before trading if: a new announcement for a holding appears, or one of your levels is
reached. Re-run this brief to refresh.
Technical observation, not investment advice. Figures can be wrong or incomplete. "About 2 weeks in 3"
is an estimate from price history, not a promise.
```

**What v5 deliberately leaves out, and why**: verdict, Agreement and agents (decision 3); model-written
text (also closes the only language-model path); macro and market sentences (readers deleted or feared
them); 52-week and pre-ex-date levels (regret, adjusted prices); trailing yield (buying nudge);
dividend-inclusive total and dividends since purchase (share-issue events and the 50-row coverage rule
break the count); fees and tax (no verified rates); rank sentence and the "a miss is expected" sentence
(third frequency, sedative); any-day-close trigger (fires about 1 week in 3); scoreboard (too few scored
weeks to mean anything); foreign flow (deferred).

**Build notes (from the engineering review)**
- Refresh every held ticker before computing (`load_ticker` rewrites history). Log the brief's own issued
  close, band and levels, and compare next week in return space or on bars after the last ex-date.
- Band in VND from `compute_range` (close x (1 +/- `range_5s_pct`/100)); the week-end comparison, not the
  daily closes, decides "held / did not hold".
- Events come from the company feed's latest items. `tests/test_company_feed_isolation.py` and the
  company-feed spec forbid any consumer outside the package except the snapshot script, so both need
  amending.
- Holdings and levels live in a file outside the repo (mode 600) and never reach a language model; the v1
  script imports no model client.
- The brief is not written under `reports/` (that directory is built for third-party ingestion).
- Open in this draft: the small / usual / large cut-offs (provisional); an optional line saying how often
  a level that far from the close was touched in past weeks (omitted until measured); the exact portfolio
  upper-bound wording; Vietnamese titles shown as the original (earlier decision, no gist).

## Appendix D: v5 discriminating test (2026-10-11; simulated readers, one per cell)

The behavioural reviewer's point was that "hold" in 12 of 12 runs could not tell a good brief from a bad
one. This round used scenarios where a good brief should change what the reader does. One fresh reader per
cell; same model as the author; position, rule and the two filings are hypothetical (SAB market numbers
are real). Format: Appendix C, except cell 6 (current report) and cell 3 (v5 plus the reassurance
sentences the reviewer called a sedative).

| Cell | Setup | Action | Urgency 0 to 10 | Reader's driver |
|---|---|---|---|---|
| 1 Rule hit, v5 | Own rule "trim 300 if the Friday close is below 41.74"; close 41.50 | Sell 300 | 4 | The REACHED line: "if I ignore my own rule the first time it triggers, there was no point writing it" |
| 2 Rule miss, v5 | Same rule; close 42.90 | Hold | 1 | "Not reached" |
| 3 Rule hit + reassurance | As cell 1 plus "that is normal ... a miss is expected sometimes" | Sell 300 | 3 | REACHED; said the reassurance sentence "is exactly the kind of sentence I'd grab to talk myself out of it" and read the two messages as mixed |
| 4 Material filing, v5 | No levels; title: a major shareholder registers to sell 30,000,000 shares | Hold, conditional plan | 4; announcement 7 of 10 | Would open the notice before the open; would sell 300 Monday if it is a large near-term sale |
| 5 Routine filing, v5 | No levels; title: change of the information-disclosure authorised person | Hold | 2; announcement 2 of 10 | "Paperwork"; would check it is not the CEO or chairman |
| 6 Control: current report + remembered rule | Rule hit; verdict "Bearish lean" | Sell 300 | 4 | The rule and the verdict; "the report agreeing made it easy ... if it had said Bullish I'd probably have talked myself out of it" |

What this shows (n = 1 per cell, so direction only):
- **v5 discriminates where it should.** Rule hit against rule miss moved the action (sell 300 against
  hold) and urgency (3 to 4 against 1). Material against routine filing moved the stated seriousness (7
  against 2) and the planned next step, though both held.
- **The reassurance sentences did not override the pre-written rule**, but the reader named them as the
  excuse he would reach for, and read them as mixed with a "REACHED" line. Keep them out (as v5 does).
- **The control matched on action, but not on cause.** The control reader leaned on the verdict as a
  permission slip and said a bullish verdict would have let him skip his rule. v5 has no verdict to
  override. This is a hypothesis from self-report; the clean test is the control with a "Bullish lean"
  verdict (not run).
- **Limits**: the rule level (41.74) was set equal to last week's range floor, so "did not hold" and
  "REACHED" were the same event and two readers said so, and one suspected the tool had suggested the
  level; rule-following is easy for a simulated reader when the line says REACHED, and a real investor
  may not follow it.

Defects the cells exposed in v5, with a proposed edit for each:
- "This week: -3.3%" sitting under "covers the next 5 trading days" was first read as a forecast. Separate
  "LAST WEEK" and "NEXT WEEK" headings.
- "A usual week" next to "last week's range did not hold" was unreadable (-3.3% is 1.2 times the band, so
  "usual", yet outside the range). Drop the small / usual / large words; show this week's move against
  last week's range (for example "-3.3% against ±2.7%").
- "Cost entered by you on 10-02" confused readers who had held longer. Ask for the purchase date and the
  entry date separately.
- "Price only; dividends are not included" made 3 of 6 readers do the dividend arithmetic themselves
  (one used it to justify following his rule). Candidate: a per-share list of dividends with ex-dates after
  the purchase date, no total, with the feed's covered period (see the review's coverage findings).
- "About 2 weeks in 3 ... with no upper limit" read as scary to 3 readers and "is the range a safety net or a
  warning?" Candidate: "about 2 weeks in 3 stay inside; about 1 in 3 is bigger, sometimes much bigger".
- "Does not predict direction" annoyed one reader and looked odd beside a sell rule. Candidate: label the
  rule block "your rule (you wrote it; the brief only checks it)".
- "Latest item 2026-08-28" made two readers suspect the source was stale rather than quiet. Show whether
  the source answered and how many items it returned, not only the newest date.
- The "if every holding moved to the range edge" line was ignored by every one-holding reader. Show it
  only with two or more holdings.
- Material-filing cell: the reader noticed that the range comes from price history and does not reflect
  the announcement, and that the brief's own "look again if a new announcement appears" had just fired.
  Add a line when a filing of a major-shareholder, insider or share-issue type is new: "The range is from
  price history and does not reflect this announcement." The reader also wanted the size of 30,000,000
  shares against the shares outstanding; whether the feed can supply that is not verified (the feed gives
  titles only).
- Do not let the tool suggest levels at the range edge: a reader suspected the tool had chosen 41.74.

## Appendix E: Appendix D replicated at five readers per cell (2026-10-11; 35 simulated readers)

Method: seven conditions by five reader profiles, each a fresh agent that read one file and answered in a
fixed format (action, urgency 0 to 10, followed own rule, seriousness of any new announcement 0 to 10,
driver, reason, confusion). Profiles (same in every cell): anxious novice who hates realising a loss;
experienced rule-writer; retired income investor; 28-year-old overconfident trader; time-poor
professional who trusts the tool. Cells 1 to 6 are those of Appendix D (v5 and the current-report control);
cell 7 is new: the current report with a "Bullish lean" verdict, the same remembered trim rule, and the
close below it (the control the first round lacked; its report numbers are invented). Same model wrote the
briefs and plays the readers, so the profiles are caricatures and the spread is smaller than among real
people.

| Cell | Sold 300 or more of 1,000 | Held | Urgency mean (range) | Other |
|---|---|---|---|---|
| 1 Rule hit, v5 | 5 of 5 (all 300) | 0 | 6.0 (4 to 8) | followed rule 5 of 5 |
| 2 Rule miss, v5 | 0 | 5 of 5 | 1.4 (0 to 3) | |
| 3 Rule hit + reassurance | 5 of 5 (all 300) | 0 | 5.4 (4 to 7) | followed rule 5 of 5 |
| 4 Material filing, v5 | 2 of 5 (500 and 600) | 3 | 5.2 (4 to 7) | announcement 7.2 (6 to 8) |
| 5 Routine filing, v5 | 0 | 5 of 5 | 1.4 (0 to 3) | announcement 2.6 (2 to 3) |
| 6 Control, bearish verdict | 5 of 5 (all 300) | 0 | 5.4 (4 to 7) | followed rule 5 of 5; verdict named as extra support by 4 of 5 |
| 7 Control, bullish verdict | 4 of 5 (all 300) | 1 | 4.4 (4 to 6) | followed rule 4 of 5 |

Reading (n = 5 per cell; counts are of readers, no significance tests were run):
- **Pre-commitment works in v5.** Rule hit against rule miss separated completely on action (5 of 5
  against 0 of 5 sold) and on urgency (lowest hit 4, highest miss 3). With the old format and a remembered
  rule the action was also the same, so the brief's gain is in where the reasoning comes from (the
  rule line, "I wrote it when I was calm"), not in the action.
- **The filing distinction holds.** Seriousness of the material filing (6 to 8) and the routine one (2 to
  3) did not overlap; urgency likewise (4 to 7 against 0 to 3).
- **New risk that n = 1 hid.** On the material headline, 2 of 5 sold half or more of the position
  (500 and 600 of 1,000: the anxious novice and the overconfident trader) before reading the notice. All
  5 said the title alone did not tell them what it means: 4 of 5 asked how big 30,000,000 shares is
  against the shares outstanding, the same 4 asked whether "registered to sell" means done or planned, and
  the fifth asked whether it is bad for the price. v5 gave a bare title. Candidate: tag the announcement type (planned sale registration, share issue, routine
  administrative) with plain words, state "planned, not executed" where the title says so, and show the
  size against shares outstanding if the data can supply it. Nobody over-reacted to the routine notice.
- **Reassurance sentences did not override the rule** (5 of 5 still sold; mean urgency 5.4 against 6.0, a
  difference well within the spread). The first-round worry that they sedate pre-commitment is not
  supported at this sample size.
- **The verdict as a permission slip: weak support.** With a bearish verdict, 4 of 5 readers cited it as
  extra backing for selling. With a bullish verdict, 1 of 5 (the anxious, loss-averse novice, who sold in
  the bearish cell) skipped his rule, saying "the report says bullish lean ... this dip is just noise".
  4 of 5 noticed the verdict contradicted their rule. 4 of 5 against 5 of 5 following the rule is not a
  significant difference, but the one flip is the profile the hypothesis predicts, and v5 has no verdict
  to offer as an excuse.
- **Current-format defects recur**: 5 of 10 control readers read `[ticker]` or `[market]` as a template
  bug (3 of 5 in cell 6, 2 of 5 in cell 7); 4 of 5 in cell 6 leaned on "Bearish lean" or "2 of 3".
- **v5 wording problems recur** (counts of 15 readers in cells 1 to 3, unless stated): "a usual week" read as
  odd or contradictory beside "did not hold" (5 of 15; 4 of 5 in cell 1, which has the -3.3% week);
  "41.74 equals last week's range floor" noticed (6 of 15, two of whom doubted who chose it; one said it
  sat close to the cost so he was "not sure whether I'm protecting anything"); "about 2 weeks in 3 ... with
  no upper limit" scary or vague (9 of 25 across cells 1 to 5); the "all holdings at the range edge" line
  pointless or ignored with one holding (2 of 5 in cell 2); the "look again if a new announcement
  appears" footer ambiguous once an announcement is present (4 of 10 across cells 4 and 5, one reader:
  "stop telling me when to look again").
- **Asked for again**: the dividend schedule and the "gain excludes dividends" arithmetic (cell 5);
  that selling 300 cuts dividend income (cell 3).

Not changed by the replication: every conclusion of Appendix D points the same way; what is new is the
tail risk on the material headline (2 of 5), the weak and single-profile support for the permission-slip
hypothesis, and the removal of the sedation worry. A real-user check is still the only thing that answers
whether real investors follow their own rules; these runs cannot.

Cost note: the 35 readers used about 61,000 tokens each, around 2.1 million tokens in all.

## Appendix F: brief v5.1 (draft; applies Appendices D and E; not yet read by simulated readers)

**Edits applied to v5, with the evidence for each**

| # | Edit | Evidence |
|---|---|---|
| 1 | "LAST WEEK" and "NEXT 5 TRADING DAYS" become separate blocks, last week first | "-3.3%" under "covers the next 5 trading days" was read as a forecast (App. D) |
| 2 | Drop the small / usual / large words. Show the move against last week's range and say "inside" or "outside" | "A usual week" beside "did not hold" read as contradictory by 5 of 15 (App. E) |
| 3 | Purchase date is a separate field from the date the entry was written | "Cost entered by you on 10-02" confused readers who had held longer (App. D) |
| 4 | Dividends: a per-share list of cash dividends with ex-dates after the purchase date, the feed's covered period, never added into a total; share issues listed separately | 3 of 6 readers did the dividend sum themselves; share-issue events and the 50-row cap break any total (review) |
| 5 | Frequency sentence: "about 2 weeks in 3 stay inside; about 1 in 3 is bigger, sometimes much bigger" (no "no upper limit") | "No upper limit" and "2 weeks in 3" were scary or vague for 9 of 25 (App. E) |
| 6 | Levels block says "you wrote these; the brief only checks them against the Friday close". The tool never pre-fills a level, least of all at the range edge | One reader asked whether REACHED means must or may; 6 of 15 noticed 41.74 equals the range floor and two doubted who chose it |
| 7 | Source line: answered on <date>, <n> items returned, newest <date> | "Latest item 2026-08-28" made readers suspect a stale source (App. D) |
| 8 | The "all holdings at the range edge" line only with two or more holdings | Ignored by every one-holding reader (App. D, E) |
| 9 | Announcements carry a type tag and are split into "needs a look" and "for information". Planned sales are marked "registered, planned, not executed"; the quantity is shown; the line "the range does not reflect this" is added | 2 of 5 sold 500 to 600 of 1,000 on a bare headline; 4 of 5 asked how big it is, the same 4 whether it is done or planned (App. E) |
| 10 | The footer names what triggers a re-read: an insider or major-shareholder trade registration, a share issue or capital change, or one of your levels. Other new announcements are "for information" | The generic "look again if a new announcement appears" was ambiguous for 4 of 10 (App. E) |
| 11 | Unchanged from v5: no verdict, no model text, no reassurance sentences, no 52-week or pre-ex-date levels, no yield, no dividend total, no tool-suggested levels | App. C, D, E |

**Check run for edit 9 (announcement tags; read-only, 2026-10-11)**
- The structured events feed already records insider and major-shareholder trades: category
  `MAJOR_SHAREHOLDER_TRADING`, event codes `DDIND`, `DDINS`, `DDRP`, with an action type ("Buy" or "Sell"),
  a start and end date, and the quantity inside the title ("<name> - Đăng kí Mua 30,000,000 <TICKER>",
  where "Đăng kí" means registered). So this tag comes from the event record, not from keywords, and
  "registered, planned" can be stated. The 100 stored news titles for SAB and VPB contain no such item.
  VPB has such events (the engineering review counted 35 of its 50 stored event rows as insider rows; I
  did not recount). This check did not tabulate buy against sell, or what `DDINS` and `DDRP` each mean
  (not verified).
- The feed gives no shares outstanding, so the share of the company cannot be computed from it. Where that
  comes from is open.
- A provisional keyword classifier (script in the scratchpad, not in the repo) assigned a class to 97 of
  the 100 stored news titles; **only coverage was checked, not whether each class is right.** The three
  unclassified included "<TICKER>: notice of receiving a tax-authority penalty decision" (a tax-authority
  penalty decision), which is the kind of item a "routine" label would bury.
- Design consequences: never use a "routine" label. My provisional "routine administrative" keyword bucket
  caught 43 of the 100 titles, and it includes board resolutions (`Nghị quyết HĐQT`), which can carry real
  transactions (for example VPB's resolutions on bond buy-backs and syndicated loans). Tag only a few classes with confidence (insider trade
  registration, share issue or capital change, dividend, shareholder meeting, results, personnel or
  disclosure officer) and show everything else as "other announcement, not classified: read the notice".
  A title that starts with the ticker and a colon is a company filing; others are press and may concern
  another company (a press item naming a different company appears under SAB).

**v5.1 template**

```
WEEKLY CHECK · <Friday date> · covers the next 5 trading days (<Mon> to <Fri>)
Prices refreshed <timestamp>; last bar for every holding is <date>.   [warn per holding if older]
This brief does not update during the week. It does not predict direction.
[Two or more holdings only: HOLDINGS LISTED (<n>): <ticker> <pct>% ...
 If every holding moved to the edge of its own range in the same direction, the listed holdings would
 move about <y>% (an upper bound, not a forecast).]

--- <TICKER> · <shares> shares · cost <cost> · bought <purchase date | not entered> ---
Close <close> · value <value> · gain/loss against your cost <amount> (<pct>), price only.

LAST WEEK
This week's move: <pct> (<prev> -> <close>). Last week's range was ±<band>% (<lo> to <hi>): the close was
<inside | outside> it.   [first brief: no previous range]

NEXT 5 TRADING DAYS
Usual range: about <lo> to <hi> per share (±<band>%; about ±<amount> on your <shares> shares).
About 2 weeks in 3 stay inside a range like this; about 1 in 3 is bigger, sometimes much bigger.
[Ex-date in the window: Ex-dividend <date>, <per share>. From that day the whole range moves down by the
 dividend: about <lo> to <hi>. Record date <date>; payout <date | not announced>.]
[Share issue in the window: your share count and cost change on <date>; update your entries.]

COMPANY (announcement source answered <date>; <n> items returned; newest <date>)
Needs a look since the last brief:
  <date> · <type tag> · <detail from the record, e.g. registered to SELL 30,000,000 (planned; window <start> to
  <end>); share of shares outstanding: not available | none>
  [For an insider or major-shareholder trade, share issue or capital change: The range above comes from
   price history and does not reflect this.]
For information: <title with date, original language | none>
Scheduled: <ex-dates, meetings, share issues in the window | none found>.
Dividends, cash, per share, ex-dates since your purchase date (source covers from <date>): <list | none
found>. Not added up.

YOUR LEVELS (you wrote these; the brief only checks them against the Friday close)
<Trim 300 shares if the Friday close is below 41.74 (entered <date>): REACHED | not reached; <pct> from the
close> | none set.

Look again before trading if: an insider or major-shareholder trade registration, a share issue or capital
change, or one of your levels appears or is reached. Other new announcements are listed for information.
Re-run this brief to refresh.
Technical observation, not investment advice. Figures can be wrong or incomplete. "About 2 weeks in 3" is
an estimate from price history, not a promise.
```

Type tags (provisional): insider or major-shareholder trade (event record: registered buy or sell,
quantity, window); share issue or capital change; dividend; shareholder meeting; results; personnel or
disclosure officer; other announcement, not classified. No "routine" tag.

**Filled example A** (real SAB market numbers for the Friday 2026-10-09 close; the holding and the level
are hypothetical; no insider event, so "Needs a look" is empty):

```
WEEKLY CHECK · Fri 2026-10-09 · covers the next 5 trading days (Mon 10-12 to Fri 10-16)
Prices refreshed <timestamp>; last bar for every holding is 2026-10-09.
This brief does not update during the week. It does not predict direction.

--- SAB · 1,000 shares · cost 41.80 · bought 2025-06-10 ---
Close 42.90 · value 42.90M VND · gain/loss against your cost +1.10M VND (+2.6%), price only.

LAST WEEK
This week's move: +1.1% (42.45 -> 42.90). No previous range (first brief).

NEXT 5 TRADING DAYS
Usual range: about 41.74 to 44.06 per share (±2.7%; about ±1.16M VND on your 1,000 shares).
About 2 weeks in 3 stay inside a range like this; about 1 in 3 is bigger, sometimes much bigger.

COMPANY (announcement source answered 2026-10-11; <n> items returned; newest 2026-08-28)
Needs a look since the last brief: none.
For information: none.
Scheduled: none found.
Dividends, cash, per share, ex-dates since your purchase date (source covers from 2017): 3,000 VND (ex
2025-06-30), 2,000 VND (ex 2026-01-12), 3,000 VND (ex 2026-07-28). Not added up.

YOUR LEVELS (you wrote these; the brief only checks them against the Friday close)
Stop 41.00 (entered 2026-10-02): not reached; 4.4% below the close.

Look again before trading if: an insider or major-shareholder trade registration, a share issue or capital
change, or one of your levels appears or is reached. Other new announcements are listed for information.
Re-run this brief to refresh.
Technical observation, not investment advice. Figures can be wrong or incomplete. "About 2 weeks in 3" is
an estimate from price history, not a promise.
```

**Filled example B** (same, with a hypothetical registered sale; the "Needs a look" block):

```
COMPANY (announcement source answered 2026-10-09; <n> items returned; newest 2026-10-08)
Needs a look since the last brief:
  2026-10-08 · Insider or major-shareholder trade · registered to SELL 30,000,000 SAB (planned, not yet
  executed; window 2026-10-12 to 2026-10-23); share of shares outstanding: not available.
  The range above comes from price history and does not reflect this.
For information: none.
```

**Still open in v5.1**: where shares outstanding comes from; what `DDINS` and `DDRP` mean and whether
only `DDIND` carries a buy or sell action; whether a registered-sale record is dated when registered or
when executed; the accuracy (not only the coverage) of the keyword classes; the source-health wording
when the feed answers but returns an old newest item; and a human check, since every reading so far is
simulated. The v1 script still needs the Appendix C build notes (refresh before computing, issued-brief
log, file outside the repo, nothing under `reports/`).

## Appendix G: v5.1 read by 20 simulated readers (2026-10-11; one planned condition not run)

Method as Appendix E (same five profiles, fixed answer format), with a short comprehension line added.
Conditions: rule hit, rule miss, material insider sale, routine personnel notice, each on the v5.1 template
(Appendix F). One scenario change: the investor's own level is 41.60, not 41.74, so it no longer equals the
range floor (the confound several readers flagged). The controls were not re-run (Appendix E still
applies). A fifth condition (an unclassified but potentially material notice, a tax-authority penalty
decision, shown under "For information") was **not run**: five of the 25 launches were refused by the
harness's 20-concurrent-agent limit, and the refusal said not to retry. Same model wrote the brief and plays
the readers; counts are of readers, no significance tests.

| Condition (v5.1) | Sold | Held | Urgency mean (range) | Other | v5 in Appendix E |
|---|---|---|---|---|---|
| Rule hit (level 41.60; close 41.50) | 4 of 5 sold 300 | 1 (skipped his rule) | 5.8 (5 to 7) | last week's close "outside": 5 of 5 correct | 5 of 5 sold 300; 6.0 |
| Rule miss | 0 | 5 of 5 | 1.2 (1 to 2) | | 0; 1.4 |
| Material insider sale (typed, planned, window shown) | **2 of 5 sold all 1,000** | 3 | 6.2 (5 to 8) | seriousness 7.8 (6 to 9); "planned": 5 of 5 correct | 2 of 5 sold 500 and 600; 5.2; 7.2 |
| Routine personnel notice (typed, "for information") | 0 | 5 of 5 | 0.8 (0 to 2) | seriousness 1.4 (1 to 2) | 0; 1.4; 2.6 |

Comprehension (open-book): all 20 answered "3 weeks in 10" and "does not predict direction".

**What v5.1 fixed**
- The "a usual week" against "did not hold" contradiction: 0 of 5 in the rule-hit condition (4 of 5 in v5).
- Readers doubting the source because the newest item was old: 0 of 20 (2 in v5). One said "looks stale,
  but it says nothing new has appeared since".
- Whether a planned sale is executed: 5 of 5 correct (4 of 5 asked in v5).
- The routine notice now reads as routine: seriousness 1.4 against 2.6, urgency 0.8 against 1.4.

**What it did not fix, or made worse**
- **The material headline is more alarming, not less.** Both readers who sold this time sold everything (the
  anxious novice: "selling everything before Monday feels safest"; the overconfident trader: "I'd rather
  bank it Monday"), against 500 and 600 in v5, and mean urgency rose from 5.2 to 6.2. The tag removed the
  uncertainty about status, but all 5 still could not size the sale ("share of shares outstanding: not
  available"), and 4 of 5 were puzzled by "the range above does not reflect this" (is the real swing
  bigger than ±2.7%?). A dated window plus an unsized quantity reads as an imminent dump.
- **"Not added up" for dividends: 12 of 20 asked for the total** or added it themselves (one got 8,000 VND a
  share). The decision to show no total backfires: the arithmetic is on the reader anyway.
- **Pre-commitment slipped for the loss-averse reader**: 4 of 5 followed the rule against 5 of 5 in v5. The
  one who skipped said "the dividends I got probably cover it" and "selling at 41.50 locks in a loss". One
  draw, so this may be noise, but the dividend list is the mechanism he named.
- **"About 1 in 3 is bigger, sometimes much bigger"**: still vague or worrying for 6 of 20 (8 counting mild
  cases); 3 asked whether "bigger" means up or down. No better than v5 ("no upper limit": 9 of 25).
- Smaller: one reader did not know what "an insider or major-shareholder trade registration" means; one
  assumed REACHED meant the tool had already sold; one asked what "look again" asks of him now that his
  level was reached; one asked why last week's range was ±2.7% and this week's ±2.8%; one noticed the
  41.60 level sits just under the usual range floor.

**Proposed v5.2 edits (not applied; owner to confirm)**
1. **Dividends**: show a per-share running total of the cash dividends since the purchase date, labelled "if
   the list is complete and your share count has not changed; share issues are listed separately". This
   reverses the v5.1 "not added up" choice, on 12 of 20 readers.
2. **Material insider or major-shareholder trade**: do not show the dated window and the quantity without
   proportion. Until shares outstanding is available, show a checklist in place of a bare alarm: "To size
   this, read the notice: who is selling, how many shares in total against the shares outstanding, how it
   will be sold, and the window." Options to test, not yet recommended: the quantity as days of average
   volume (30,000,000 shares against about 425,500 a day is about 70 days, which is alarming and ignores
   block trades), or the quantity as a share of shares outstanding once a source is found.
3. **Reword "the range does not reflect this"** to "The usual range is built from past prices only. It does
   not account for this announcement, so the real swing could be larger."
4. **Replace "sometimes much bigger" with a measured tail fact**, for example "In the last 2 years, SAB's
   biggest weekly fall was -12.1% (week ending 2025-04-04) and its biggest rise +13.0% (week ending
   2025-04-11)". Measured on 104 Friday-to-Friday weeks; both fall in the April 2025 market shock. It could
   stress the anxious profile; test it before adopting.
5. **Plain footer**: "a registered sale or purchase by a major shareholder or insider".
6. **"Bigger, in either direction"** wherever the 1-in-3 sentence appears.
7. **REACHED line**: add "(this brief does not place orders)" and say what the investor does next is theirs.
8. **Watch the loss-averse reader's rule-following** with a larger sample before deciding whether the dividend
   list erodes pre-commitment.

**Still not run**: the unclassified-notice condition (does "for information" bury a potentially material
notice?); and nothing here says whether real investors follow their own rules.

## Appendix H: a source for shares outstanding (2026-10-11; measured)

The v5.1 readers could not size a registered sale because the feed carries no shares outstanding (5 of 5).
This appendix records where to get it.

**Method.** Searched the stored data first: no column in `app.db` holds a share count, and no news title or
event record carries one (the events record only a ratio for share issues). Then read the earlier vnstock
probes in `DISCUSSION_describe_not_vote_redesign.md`, which had already named two fields. Then one live
check of both, for SAB and VPB, through the project's guard (`app.vnstock_guard.install()` before the
import) in a throwaway home and working directory. The repo is unchanged by the probe (`git status` shows
only this doc); vnstock's state files landed in the throwaway home.

**Result: two fields from the same VCI company object (`Company(source="vci", symbol=S)`).**

| Field | SAB | VPB |
|---|---|---|
| `ratio_summary()["number_of_shares_mkt_cap"]`, latest quarter (2026-Q2) | 1,282,562,372 (same value for every quarter from 2025-Q3) | 10,000,000,000 (was 7,933,923,601 through 2026-Q1) |
| `overview()["issue_share"]` | 1,282,562,372 in all four duplicate columns | 10,000,000,000 in some columns and 7,933,923,601 in others |
| `ratio_summary()["market_cap"]`, 2026-Q2 | 5.502193e13 VND, which is 42,900 VND a share, exactly the 2026-10-09 close | 2.38e14 VND |

- **The two fields agree for SAB** and match the 1,282,562,372 recorded in the earlier probe (EPS check:
  four-quarter parent profit over that count gave the vendor's trailing EPS).
- **The count follows a stock dividend within about two weeks.** VPB's feed event shows a 26.04104% share issue
  (ex-date 2026-09-24, filing 2026-10-01). 7,933,923,601 times 1.2604104 is 9,999,999,820, which the vendor
  shows as 10,000,000,000 on 2026-10-11. While a count is changing, `overview()`'s duplicate columns can
  disagree (VPB), whereas `ratio_summary()`'s latest row had already moved.
- **The count is quarterly in form** (one row per quarter), so it carries an "as of" date, and an issue
  after that date is not in it until the vendor updates (one example only, VPB).

**Sizing a registered sale (the 30,000,000-share example).**
- 30,000,000 SAB shares are **2.34%** of 1,282,562,372.
- For context from the stored events (parsed from titles, 2017 onward, up to the 50-row cap): SAB has 13
  registrations with a stated quantity, median 0.0016% of today's share count, one larger than 30M (the
  Ministry of Industry and Trade selling 343,662,587 shares in 2018, which is 26.8% of today's count but
  about 53.6% of the 641,281,186 shares outstanding then; quantities before the 2023 bonus issue must be
  divided by the count of their own date). VPB: 27 with quantity, median 0.0016%, largest 0.70%.
- Event codes (inferred from the titles, not verified): `DDIND` individuals, `DDINS` institutions, `DDRP`
  related persons. All three carry a Buy or Sell action and a quantity in the title.

**Proposed brief line (replaces the v5.1 "share of shares outstanding: not available")**:
"registered to SELL 30,000,000 SAB (planned, not yet executed; window 2026-10-12 to 2026-10-23): 2.3% of
its 1,282,562,372 shares (vendor count as of 2026-Q2). Earlier registrations of this kind in the source were
mostly far smaller."
The last sentence needs a stated basis (the 13 SAB registrations with a quantity since 2017) and the
pre-bonus caveat if it ever names a larger past event.

**Build notes**
- Fetch per held ticker at run time (two vendor calls per ticker, or `ratio_summary()` alone), cache the last
  value with its quarter in the local state file; no schema change. Use `ratio_summary()`'s latest row, and
  treat `overview()` as a cross-check: when they disagree, or when a share-issue event is dated after the
  quarter, show "share count is changing (issue on <date>)" and withhold the percentage.
- Any new module importing vnstock must call the guard first (a repo test enforces it); run the check as its
  own process (vnai's rate limiter exits the process).
- Percentages for registrations dated before a share issue need the count at that date.

**Open**
- `ratio_summary()` is a VCI-only route; whether it sits inside the vendor's free-tier terms was not
  checked (the earlier note left this open, and the owner decided personal use fits the library licence).
- One live probe on two tickers on one day. Not checked: tickers other than SAB and VPB, how long after an
  ex-date the count updates in other cases, and what happens to the `ratio_summary()` series for tickers
  with no recent quarter row.
- The vnai analytics noted in the review may have sent the two tickers to the vendor during the probe
  (traffic not inspected); the probe ran in a throwaway home with the guard installed.
- Whether the v5.2 wording (a sized line) fixes the over-reaction seen in v5.1 is untested.

## Appendix I: brief v5.2 (draft; applies Appendices G and H; not yet read by simulated readers)

**Edits applied to v5.1, with the evidence for each**

| # | Edit | Evidence |
|---|---|---|
| 1 | Dividends: a per-share total since the purchase date, also as an amount on the investor's shares (before tax), with the caveat "if the list is complete and your share count has not changed". Shown on its own line, **not added into the price gain/loss** | 12 of 20 v5.1 readers asked for the total or added it up themselves (App. G); keeping it separate avoids resetting the reference point (App. D review) |
| 2 | A registered insider or major-shareholder trade is shown with its size: percentage of shares outstanding, the vendor count and its quarter. When the share count is changing (a share issue dated after the quarter), the percentage is withheld and a read-the-notice checklist is shown instead | 5 of 5 readers could not size the sale and 2 of 5 sold everything (App. G); the count is available (App. H) |
| 3 | Reworded: "The usual range is built from past prices only. It does not account for this announcement, so the real swing could be larger." | 4 of 5 were puzzled by "the range above does not reflect this" (App. G) |
| 4 | "About 1 in 3 is bigger, up or down" (no "sometimes much bigger"). An optional measured tail line is included **but marked: test before adopting** | "Sometimes much bigger" vague or worrying for 6 of 20; 3 asked about direction (App. G) |
| 5 | Footer in plain words: "a registered sale or purchase by a major shareholder or insider" | One reader did not know "insider or major-shareholder trade registration" (App. G) |
| 6 | The REACHED line adds "This brief does not place orders; what you do is your decision." | One reader assumed the tool had already sold (App. G) |
| 7 | Unchanged from v5.1: layout, no size words, source line, tags, levels block, no verdict, no model text, no 52-week or pre-ex-date levels, no yield | App. F, G |

**v5.2 template**

```
WEEKLY CHECK · <Friday date> · covers the next 5 trading days (<Mon> to <Fri>)
Prices refreshed <timestamp>; last bar for every holding is <date>.   [warn per holding if older]
This brief does not update during the week. It does not predict direction.
[Two or more holdings only: HOLDINGS LISTED (<n>): <ticker> <pct>% ...
 If every holding moved to the edge of its own range in the same direction, the listed holdings would
 move about <y>% (an upper bound, not a forecast).]

--- <TICKER> · <shares> shares · cost <cost> · bought <purchase date | not entered> ---
Close <close> · value <value> · gain/loss on price against your cost <amount> (<pct>).
Dividends since your purchase date: <total per share> a share, about <amount> on your <shares> shares,
before tax, if the list below is complete and your share count has not changed.

LAST WEEK
This week's move: <pct> (<prev> -> <close>). Last week's range was ±<band>% (<lo> to <hi>): the close was
<inside | outside> it.   [first brief: no previous range]

NEXT 5 TRADING DAYS
Usual range: about <lo> to <hi> per share (±<band>%; about ±<amount> on your <shares> shares).
About 2 weeks in 3 stay inside a range like this; about 1 in 3 is bigger, up or down.
[OPTIONAL, TEST FIRST: In the last 2 years this stock's biggest weekly fall was <x>% (week ending <date>)
 and its biggest rise <y>% (week ending <date>).]
[Ex-date in the window: Ex-dividend <date>, <per share>. From that day the whole range moves down by the
 dividend: about <lo> to <hi>. Record date <date>; payout <date | not announced>.]
[Share issue in the window: your share count and cost change on <date>; update your entries.]

COMPANY (announcement source answered <date>; <n> items returned; newest <date>)
Needs a look since the last brief:
  <date> · <type tag> · <detail>
  [Insider or major-shareholder trade: registered to <SELL | BUY> <quantity> <TICKER> (planned, not yet
   executed; window <start> to <end>): <pct>% of its <shares outstanding> shares (vendor count as of
   <quarter>).]
  [If the share count is changing (a share issue dated after that quarter): size not shown, because the
   share count is changing (issue on <date>). To size it, read the notice: who is selling or buying, how
   many shares in total against the shares outstanding, how it will be done, and the window.]
  [For an insider or major-shareholder trade, a share issue or a capital change: The usual range is built
   from past prices only. It does not account for this announcement, so the real swing could be larger.]
  | none
For information: <title with date, original language | none>
Scheduled: <ex-dates, meetings, share issues in the window | none found>.
Dividends, cash, per share, ex-dates since your purchase date (source covers from <date>):
  <list | none found>.
Share issues since your purchase date: <list, with ratio | none>. They change your share count.

YOUR LEVELS (you wrote these; the brief only checks them against the Friday close)
<Trim 300 shares if the Friday close is below 41.60 (entered <date>): REACHED. This Friday's close, <close>,
is below it. This brief does not place orders; what you do is your decision. | not reached; the level is
<pct>% below the close> | none set.

Look again before trading if: a registered sale or purchase by a major shareholder or insider, a share issue
or capital change, or one of your levels appears or is reached. Other new announcements are listed for
information. Re-run this brief to refresh.
Technical observation, not investment advice. Figures can be wrong or incomplete. "About 2 weeks in 3" is
an estimate from price history, not a promise.
```

**Filled example A** (real SAB market and dividend figures for the Friday 2026-10-09 close; the holding and
the level are hypothetical; no insider event):

```
WEEKLY CHECK · Fri 2026-10-09 · covers the next 5 trading days (Mon 10-12 to Fri 10-16)
Prices refreshed <timestamp>; last bar for every holding is 2026-10-09.
This brief does not update during the week. It does not predict direction.

--- SAB · 1,000 shares · cost 41.80 · bought 2025-06-10 ---
Close 42.90 · value 42.90M VND · gain/loss on price against your cost +1.10M VND (+2.6%).
Dividends since your purchase date: 8,000 VND a share, about 8.0M VND on your 1,000 shares, before tax,
if the list below is complete and your share count has not changed.

LAST WEEK
This week's move: +1.1% (42.45 -> 42.90). No previous range (first brief).

NEXT 5 TRADING DAYS
Usual range: about 41.74 to 44.06 per share (±2.7%; about ±1.16M VND on your 1,000 shares).
About 2 weeks in 3 stay inside a range like this; about 1 in 3 is bigger, up or down.

COMPANY (announcement source answered 2026-10-11; <n> items returned; newest 2026-08-28)
Needs a look since the last brief: none.
For information: none.
Scheduled: none found.
Dividends, cash, per share, ex-dates since your purchase date (source covers from 2017):
  3,000 VND (ex 2025-06-30), 2,000 VND (ex 2026-01-12), 3,000 VND (ex 2026-07-28).
Share issues since your purchase date: none.

YOUR LEVELS (you wrote these; the brief only checks them against the Friday close)
Trim 300 shares if the Friday close is below 41.60 (entered 2026-10-02): not reached; the level is 3.0%
below the close.

Look again before trading if: a registered sale or purchase by a major shareholder or insider, a share issue
or capital change, or one of your levels appears or is reached. Other new announcements are listed for
information. Re-run this brief to refresh.
Technical observation, not investment advice. Figures can be wrong or incomplete. "About 2 weeks in 3" is
an estimate from price history, not a promise.
```

**Filled example B** (same, with a hypothetical registered sale; only the "Needs a look" block changes):

```
COMPANY (announcement source answered 2026-10-09; <n> items returned; newest 2026-10-08)
Needs a look since the last brief:
  2026-10-08 · Insider or major-shareholder trade · registered to SELL 30,000,000 SAB (planned, not yet
  executed; window 2026-10-12 to 2026-10-23): 2.3% of its 1,282,562,372 shares (vendor count as of 2026-Q2).
  The usual range is built from past prices only. It does not account for this announcement, so the real
  swing could be larger.
For information: none.
```

**Filled example C** (the fallback: a count that is changing, VPB-style; hypothetical dates):

```
  2026-10-08 · Insider or major-shareholder trade · registered to BUY 30,000,000 VPB (planned, not yet
  executed; window 2026-10-12 to 2026-10-23): size not shown, because the share count is changing (issue
  on 2026-09-24). To size it, read the notice: who is buying, how many shares in total against the shares
  outstanding, how it will be done, and the window.
```

**Not built or not verified before v5.2 can run**
- The shares-outstanding fetch (Appendix H) and its "changing" rule; one live check on two tickers only.
- Parsing the quantity and window from the event record for every code (`DDIND`, `DDINS`, `DDRP`); the code
  meanings are inferred from titles.
- The per-share dividend total needs the share-issue handling: a bonus or stock dividend after the purchase
  date changes the share count, so the "on your shares" amount is only right if the entered share count is the
  count held at the time of each dividend. The brief says so; whether that caveat is enough is untested.
- The optional tail line (biggest weekly fall and rise in two years, measured on 104 Friday-to-Friday weeks:
  -12.1% and +13.0%, both in April 2025) is untested for stress on the anxious profile.
- The 41.60 level in the examples is set by the investor, not suggested by the tool.
- No simulated reader has seen v5.2; the unclassified-notice condition has still never run; nothing here says
  how real investors read it.

## Appendix J: v5.2 read by 30 simulated readers (2026-10-11; three batches of ten)

Method as Appendices E and G (same five profiles, fixed answer format), run in three batches of ten to stay
under the 20-concurrent-agent limit (no refusals). Six conditions on the v5.2 template (Appendix I): rule hit,
rule miss, a registered sale with its size, a routine personnel notice, an **unclassified** notice (the tax
authority penalty decision; never run before), and the **fallback** (size not shown because the share count
is changing, with a hypothetical 10-for-100 share issue). The investor's own level is 41.60 as in
Appendix G. The quiz now also asks whether the size of a trade is known and the dividends per share since
purchase. Same model wrote the briefs and plays the readers; counts are of readers.

| Condition (v5.2) | Sold | Held | Urgency mean (range) | Announcement mean (range) |
|---|---|---|---|---|
| Rule hit (close 41.50, level 41.60) | 5 of 5 sold 300 | 0 | 5.6 (4 to 7) | n/a |
| Rule miss | 0 | 5 of 5 | 1.4 (1 to 2) | n/a |
| Registered sale, **sized** (2.3% of shares) | **1 of 5 sold 400** | 4 | 4.6 (3 to 6) | 6.0 (5 to 7) |
| Routine personnel notice | 0 | 5 of 5 | 1.2 (0 to 3) | 1.2 (1 to 2) |
| Unclassified tax-penalty notice | 0 | 5 of 5 | 1.8 (1 to 3) | 3.6 (3 to 5) |
| Registered sale, **fallback** (size not shown) | 1 of 5 sold 500 | 4 | 4.6 (3 to 7) | 6.4 (5 to 8) |

Earlier rounds on the same conditions: sale with no size, v5: 2 of 5 sold 500 and 600, urgency 5.2, seriousness
7.2; v5.1: 2 of 5 sold all 1,000, urgency 6.2, seriousness 7.8. Rule hit, v5.1: 4 of 5 sold (the loss-averse
reader skipped his rule).

Comprehension (open-book): 30 of 30 answered "3 weeks in 10", "does not predict direction", and **8,000 VND a
share** for the dividends since purchase; 5 of 5 correct on last week's close ("outside"); 10 of 10 correct on
"planned" for the sale; 5 of 5 correct that the size is known (sized) and 5 of 5 that it is not (fallback).

**What v5.2 fixed**
- **Rule-following is back to 5 of 5.** The loss-averse reader who skipped his rule in v5.1 followed it; his
  reason cites the dividends ("the dividends make me up overall"). So the dividend line can support following the
  rule as well as eroding it.
- **The material-sale response is smaller**: one reader sold 400 (not all 1,000), mean urgency 4.6 (6.2 in
  v5.1), seriousness 6.0 (7.8).
- **The unclassified notice is visible but calm**: seriousness 3.6 against 1.2 for the routine notice; nobody
  acted; the readers said they would open it. "For information" did not bury it. All 5 asked how large the
  penalty is, and 3 called "not classified" vague.
- **Dividends are understood**: 30 of 30 got the per-share figure; the "not added up" complaint of v5.1 is gone
  as a request for a total.

**What this does not show**
- **The size line did not beat the fallback**: sized and fallback gave the same sell rate (1 of 5 each) and the
  same urgency (4.6). So the improvement over v5.1 is not attributable to the percentage. Other v5.2 changes
  (the rewritten "range does not account for this" sentence, the dividend line, the wording) and draw noise are
  equally plausible.
- **Dividends were used as comfort against a planned sale** by 4 of the 10 sale readers ("8,000 a share already
  came in", "I'm comfortable"). Past income has no bearing on the risk of a planned sale; this is a possible
  anchoring effect of the new dividend line, not a measured one.

**What still confuses readers, with counts**
- **The seller is not named (5 of 5 in the sized condition)**, although the event record's title carries the name
  ("<name> - Đăng kí Bán 30,000,000 SAB"). The brief omitted it.
- **2.3% has no benchmark (3 of 5 "don't know if 2.3% is big")**. The line "earlier registrations of this kind
  were mostly far smaller" from Appendix H was left out of the template for lack of a stated basis; it was needed.
- **The sale window runs longer than the 5-day range (4 of 10)** and 3 of 5 asked how much bigger the real swing
  could be given the range ignores the sale.
- **A changing share count (5 of 5 in the fallback condition)**: readers asked whether they now hold 1,100
  shares and whether their cost and the 42.90 close are adjusted. The brief said "they change your share count"
  but not what the new count is.
- **Price gain and dividends are read separately but combined mentally**: 5 of 30 unsure what the "real
  result" is; 5 of 30 asked about tax or net cash.
- **The "LAST WEEK" heading** holds "This week's move" (3 of 30 found it muddled).
- **"Look again before trading if" reads like an instruction (2)**; "read the notice" the same (1).
- Smaller: the 41.60 level sits just under the range floor (2 of 30); "about 2 weeks in 3" took a second read (2);
  "bigger, up or down" scary or unclear (3); "Scheduled: none found" unclear whether no dividend is due (1).

**Proposed v5.3 edits (not applied; owner to confirm)**
1. **Name the seller or buyer** from the event title, with the event code's class (individual, institution or
   related person; mapping inferred, unverified).
2. **Add a benchmark with a stated basis** to the size line, for example "larger than every earlier registration
   of this kind in the source except one in 2018 (13 with a stated quantity, 2017 onward; counts before the 2023
   bonus issue are against the share count of their own date)". If the source lacks a clean comparison, say what
   it is compared with, or omit.
3. **Say the window is longer than the brief**: "the window runs two weeks; this brief covers one".
4. **Show the share count after a share issue** in the position block: "after the 2026-09-24 issue of 10 new shares
   per 100 held: 1,100 shares, cost 38.00 a share (from your entry of 1,000 at 41.80)", marked as calculated and
   to be checked against the broker; ask for "shares as of <date>" in the holdings entry. This also settles
   whether the closing price is adjusted for the issue.
5. **Rename the "LAST WEEK" block** "THE WEEK JUST ENDED (Mon <date> to Fri <date>)".
6. **Show a net line**: "price gain/loss plus dividends: <amount>, before tax and selling costs", labelled, and
   keep the separate dividend line. Tax stays unverified.
7. **Reword the footer** from "Look again before trading if" to "These are the things that would make a re-read
   worthwhile" and the notice prompt to "The title does not give the amount; the notice does."
8. **For an unclassified notice, say what is missing**: "not classified; the title gives no amount".
9. **Watch the dividend line as a comfort cue** against material events; consider placing it below the
   company block.

**Still not run or not known**: the effect of any v5.3 wording; real investors' behaviour; whether the size
percentage helps at all (the data above says it did not, at n = 5); the two unverified inputs (the event-code
meanings, and the share-count update lag beyond VPB).

## Appendix K: brief v5.3 (draft; applies Appendix J; not read by simulated readers)

Wording iteration stops here by agreement: the remaining open points need real people, not more simulated
readers (all counts so far are from the same model that wrote the briefs).

**Edits applied to v5.2, with the evidence for each**

| # | Edit | Evidence (App. J) |
|---|---|---|
| 1 | An insider or major-shareholder trade names the seller or buyer, taken from the event title | The seller was not named for 5 of 5 readers of the sized sale, though the record carries the name |
| 2 | The size line carries a benchmark with its stated basis | 3 of 5 "don't know if 2.3% is big" |
| 3 | The line says the trade window is longer than the brief | 4 of 10 noted the window runs past the 5-day range |
| 4 | After a share issue the brief shows the investor's share count and cost per share as calculated, marked to be checked against the broker; the holdings entry asks for "shares as of <date>" | 5 of 5 fallback readers asked whether they now hold 1,100 shares and whether cost and price are adjusted |
| 5 | The block "LAST WEEK" is renamed "THE WEEK JUST ENDED" and carries its dates | 3 of 30 found "This week's move" under "LAST WEEK" muddled |
| 6 | A labelled net line: price gain or loss plus dividends, before tax and selling costs, only when the dividend list is complete | 5 of 30 were unsure what the real result is; 5 of 30 asked about tax or net cash |
| 7 | Footer and notice prompts reworded: "These would make a re-read worthwhile" and "The title does not give the amount; the notice does." | The footer read like an instruction (2); "read the notice" the same (1) |
| 8 | An unclassified notice says what is missing: "not classified; the title gives no amount" | All 5 asked how large the penalty was; 3 called "not classified" vague |
| 9 | The dividend list moves to its own DIVIDENDS block below COMPANY; the position block keeps only the net line | Dividends were cited as comfort against a planned sale by 4 of 10 sale readers; **the placement is untested** |
| 10 | Unchanged from v5.2: no verdict, no model text, no 52-week or pre-ex-date levels, no yield, levels block, source line, type tags | App. F, G, I, J |

**v5.3 template**

```
WEEKLY CHECK · <Friday date> · covers the next 5 trading days (<Mon> to <Fri>)
Prices refreshed <timestamp>; last bar for every holding is <date>.   [warn per holding if older]
This brief does not update during the week. It does not predict direction.
[Two or more holdings only: HOLDINGS LISTED (<n>): <ticker> <pct>% ...
 If every holding moved to the edge of its own range in the same direction, the listed holdings would
 move about <y>% (an upper bound, not a forecast).]

--- <TICKER> · <shares> shares · cost <cost> · bought <purchase date | not entered> ---
Close <close> · value <value> · gain/loss on price against your cost <amount> (<pct>).
[Complete dividend list only: Price gain/loss plus dividends since your purchase: <amount>, before tax and
 selling costs (the dividends are in the DIVIDENDS block below).]
[After a share issue dated after your entry: Share issue ex <date>, <n> new shares per <m> held. Your shares
 after it: <count> and your cost per share <cost>, calculated from your entry of <shares> as of <date>.
 Check these against your broker.]

THE WEEK JUST ENDED (<Mon> to <Fri>)
Move: <pct> (<prev> -> <close>). Last week's range was ±<band>% (<lo> to <hi>): the close was
<inside | outside> it.   [first brief: no previous range]

NEXT 5 TRADING DAYS
Usual range: about <lo> to <hi> per share (±<band>%; about ±<amount> on your <shares> shares).
About 2 weeks in 3 stay inside a range like this; about 1 in 3 is bigger, up or down.
[OPTIONAL, TEST FIRST: In the last 2 years this stock's biggest weekly fall was <x>% (week ending <date>)
 and its biggest rise <y>% (week ending <date>).]
[Ex-date in the window: ...]  [Share issue in the window: ...]

COMPANY (announcement source answered <date>; <n> items returned; newest <date>)
Needs a look since the last brief:
  <date> · <type tag> · <detail>
  [Insider or major-shareholder trade: <name> registered to <SELL | BUY> <quantity> <TICKER> (planned, not
   yet executed; window <start> to <end>): <pct>% of its <shares outstanding> shares (vendor count as of
   <quarter>). The window runs <n> weeks; this brief covers one.
   Earlier registrations of this kind in the source (<k> with a stated quantity, <from year> onward):
   <j> were larger than this; <comparison sentence with its basis>.]
  [If the share count is changing: size not shown, because the share count is changing (issue on <date>). To
   size it, read the notice: who, how many shares in total against the shares outstanding, how it will be
   done, and the window.]
  [For an insider or major-shareholder trade, a share issue or a capital change: The usual range is built
   from past prices only. It does not account for this announcement, so the real swing could be larger.]
  | none
For information: <date · type tag · title in original language, then: "The title does not give the amount;
  the notice does." | none>
  [Unclassified: <date> · Other announcement, not classified; the title gives no amount · <title>]
Scheduled: <ex-dates, meetings, share issues in the window | none found (no dividend or meeting is dated in
  the source yet)>.

DIVIDENDS
Cash, per share, ex-dates since your purchase date (source covers from <date>): <list | none found>.
Total per share: <amount>, about <amount> on your <shares> shares, before tax, if the list is complete and
your share count has not changed.
Share issues since your purchase date: <list, with ratio | none>. They change your share count.

YOUR LEVELS (you wrote these; the brief only checks them against the Friday close)
<Trim 300 shares if the Friday close is below 41.60 (entered <date>): REACHED. This Friday's close, <close>,
is below it. This brief does not place orders; what you do is your decision. | not reached; the level is
<pct>% below the close> | none set.

These would make a re-read worthwhile: a registered sale or purchase by a major shareholder or insider, a
share issue or capital change, or one of your levels appearing or being reached. Other new announcements are
listed for information. Re-run this brief to refresh.
Technical observation, not investment advice. Figures can be wrong or incomplete. "About 2 weeks in 3" is
an estimate from price history, not a promise.
```

**Filled example A** (real SAB market and dividend figures for the Friday 2026-10-09 close; the holding and
the level are hypothetical; no insider event):

```
WEEKLY CHECK · Fri 2026-10-09 · covers the next 5 trading days (Mon 10-12 to Fri 10-16)
Prices refreshed <timestamp>; last bar for every holding is 2026-10-09.
This brief does not update during the week. It does not predict direction.

--- SAB · 1,000 shares · cost 41.80 · bought 2025-06-10 ---
Close 42.90 · value 42.90M VND · gain/loss on price against your cost +1.10M VND (+2.6%).
Price gain/loss plus dividends since your purchase: +9.10M VND, before tax and selling costs (the dividends
are in the DIVIDENDS block below).

THE WEEK JUST ENDED (Mon 10-05 to Fri 10-09)
Move: +1.1% (42.45 -> 42.90). No previous range (first brief).

NEXT 5 TRADING DAYS
Usual range: about 41.74 to 44.06 per share (±2.7%; about ±1.16M VND on your 1,000 shares).
About 2 weeks in 3 stay inside a range like this; about 1 in 3 is bigger, up or down.

COMPANY (announcement source answered 2026-10-11; <n> items returned; newest 2026-08-28)
Needs a look since the last brief: none.
For information: none.
Scheduled: none found (no dividend or meeting is dated in the source yet).

DIVIDENDS
Cash, per share, ex-dates since your purchase date (source covers from 2017): 3,000 VND (ex 2025-06-30),
2,000 VND (ex 2026-01-12), 3,000 VND (ex 2026-07-28).
Total per share: 8,000 VND, about 8.0M VND on your 1,000 shares, before tax, if the list is complete and
your share count has not changed.
Share issues since your purchase date: none.

YOUR LEVELS (you wrote these; the brief only checks them against the Friday close)
Trim 300 shares if the Friday close is below 41.60 (entered 2026-10-02): not reached; the level is 3.0%
below the close.

These would make a re-read worthwhile: a registered sale or purchase by a major shareholder or insider, a
share issue or capital change, or one of your levels appearing or being reached. Other new announcements are
listed for information. Re-run this brief to refresh.
Technical observation, not investment advice. Figures can be wrong or incomplete. "About 2 weeks in 3" is
an estimate from price history, not a promise.
```

**Filled example B** (only the "Needs a look" block; a hypothetical registration by a fictional institution):

```
Needs a look since the last brief:
  2026-10-08 · Insider or major-shareholder trade · Example Holdings Ltd registered to SELL 30,000,000 SAB
  (planned, not yet executed; window 2026-10-12 to 2026-10-23): 2.3% of its 1,282,562,372 shares (vendor
  count as of 2026-Q2). The window runs two weeks; this brief covers one.
  Earlier registrations of this kind in the source (13 with a stated quantity, 2017 onward): 1 was larger
  than this (2018, 53.6% of the shares then); all the others were below 0.02% of the shares.
  The usual range is built from past prices only. It does not account for this announcement, so the real
  swing could be larger.
```
The basis for the benchmark sentence: the 13 SAB registrations with a stated quantity in the stored event
rows, the largest being the 2018 sale of 343,662,587 shares against 641,281,186 shares outstanding then; the
next largest are 100,000 and 80,000 shares (0.016% and 0.012% of the shares then). The pre-2023 share count is
today's count divided by the bonus-issue ratio (a 100% issue, ex 2023-09-14).

**Filled example C** (the fallback with the share count after an issue; numbers are illustrative):

```
Share issue ex 2026-09-24, 10 new shares per 100 held. Your shares after it: 1,100 and your cost per share
38.00, calculated from your entry of 1,000 as of 2026-09-01. Check these against your broker.
...
  2026-10-08 · Insider or major-shareholder trade · Example Holdings Ltd registered to SELL 30,000,000 SAB
  (planned, not yet executed; window 2026-10-12 to 2026-10-23): size not shown, because the share count is
  changing (issue on 2026-09-24). To size it, read the notice: who is selling, how many shares in total
  against the shares outstanding, how it will be sold, and the window.
```

**Filled example D** (an unclassified notice, "For information"):

```
For information:
  2026-10-08 · Other announcement, not classified; the title gives no amount · <TICKER>: notice of receiving
  a tax-authority penalty decision
  The title does not give the amount; the notice does.
```

**Build notes added by v5.3**
- The holdings entry gains "shares as of <date>"; a share issue with an ex-date after that date adjusts the count and
  the cost per share (issue ratio from the event record), and the VND amounts use the adjusted count.
- The benchmark needs the share count at each event's own date: today's count divided by the product of
  (1 + ratio) over share issues after that date. Quantities come from the event titles.
- The seller or buyer name is the text before " - Đăng kí" in the event title; the class (individual,
  institution, related person) comes from the event code only once the code meanings are verified.
- The net line is shown only when the dividend list is complete for the period (the covered-period rule and its
  failure cases are in the engineering review above), otherwise only the DIVIDENDS block appears.

**Untested in v5.3**: every edit above, since no reader has seen this version; the DIVIDENDS-block placement;
the benchmark sentence (3 of 5 earlier readers wanted it, but its effect on selling is unknown); the optional
tail line; the share-count display (a hypothetical issue only); and everything about real investors. Unverified
inputs: the event-code meanings, the share-count update lag beyond VPB, `ratio_summary()` under the vendor's
terms, and the dividend-completeness rule.

## Appendix L: helper agents for reading a brief (draft files, 2026-10-11)

Three project agents were drafted in `.claude/agents/` (new directory; uncommitted, not yet exercised):
`brief-explainer` (plain-language reading of a redacted brief; never predicts direction), `brief-auditor`
(read-only check of the brief's market-data numbers against `app.db`, `company_feed_log.db` and `debate_log.db`;
`Bash(sqlite3:*)` only, always `-readonly`) and `reader-sim` (development-only persona reader with the fixed
five-line answer format used in Appendices E, G and J).

Limits to keep in view:
- **Redaction is enforced by the file the user hands over, not by the agent.** Once an agent reads a file its
  contents are in a model's context. The brief script therefore needs a `--redact` mode (percentages and range
  widths only; no share counts, cost, purchase date or VND amounts on the holding) before these agents are used
  on a real brief; until then only hypothetical briefs should be passed. This is also the open premise question
  (account and machine ownership) from the risk review.
- `reader-sim` output is simulated and must not be used to interpret a real brief or to decide anything.
- `brief-auditor` cannot check the vendor share count offline, nor anything that needs the holdings.
- The agents describe the v5.3 draft; they should be re-read when the real brief format is built (the last task
  of the `add-weekly-holdings-brief` change).
- The `Bash(sqlite3:*)` tool pattern and the frontmatter fields follow the form of other agents in this
  environment; they were not exercised, so the first run should confirm the tool restriction behaves as written.

**Update (2026-10-11, same day): profile files.** `reader-sim` now reads its profiles from the shared
`docs/READER_PROFILES.md` (two Reads: profiles file and brief file; P1 to P5 are frozen because Appendices E, G
and J used those exact texts, new profiles get new ids). `brief-explainer` accepts an optional owner-written
investor profile (template `docs/INVESTOR_PROFILE.template.md`; the real file lives outside the repo, mode 600)
and uses it only to add one-sentence factual notes where the brief meets a habit the owner listed. It must not
treat the simulated profiles as the owner. The profile is personal data and goes to a model like the brief does,
so the same redaction rule applies. Neither change has been run (the agents do not load until a new session).

**Update (2026-10-11): rules change applied.** `openspec/changes/align-rules-with-weekly-brief`: the owner approved the
Rule 4, 5 and 6 texts (Rule 6 with the tightening that the tool's own words in a line about the investor's own level
are limited to reached or not reached and the distance). `CLAUDE.md` and `openspec/config.yaml` were edited in
lockstep (`backend/tests/test_domain_rules_in_sync.py` passes) and `docs/DISCLAIMER.md` gained a "Brief version"
section. The personal-use premise (task 1.2) is deferred: confirm it before anyone else receives output.

## Status record (2026-10-12)

Written to consolidate what is done and what is left. Statuses were checked against `openspec list`, the archive
folder and the working tree on this date; they were not re-verified against the code beyond that.

**Done.** `align-rules-with-weekly-brief` (R1) is archived as
`openspec/changes/archive/2026-10-12-align-rules-with-weekly-brief/` and its spec is synced to
`openspec/specs/domain-rules/`. The other earlier changes (`evaluate-band-coverage-by-market-regime`,
`retire-debate-round-two-and-model-prose`, `add-company-feed-news-and-events`) are archived too. `openspec list`
shows no active change.

**Proposals still to do**

| Order | Change | Holds | Depends on | Status |
|---|---|---|---|---|
| 1 | `add-weekly-holdings-brief` (N1) | Core script: holdings file outside the repo plus a `.gitignore` line, refresh before computing, band in VND, the week just ended and whether last week's range held, issued-brief log, the investor's levels checked against the Friday close, fixed sentences, output not under `reports/`, no model call. Also `--redact` mode, the brief-disclaimer guard test, narrowing `TRANSACTION_VERBS`, re-reading the three agents. | R1 (done) | Next; not started |
| 2 | `add-dividend-and-ex-date-lines` (N2a) | **Split from N2 on 2026-10-12** (see "N1 and N2 shaping session" at the end). One feed adapter, dividend list since purchase, ex-date and share-issue lines with the shifted range, feed "last fetched" line, "level set before ex-date" note, the count-changing-issue rule, the week-1 recompute fallback. Amends the company-feed spec and its isolation test. | N1 | Not started |
| 2b | `add-dividend-totals-and-share-count` (N2b) | Net line, dividends times running share count, share count and cost per share after an issue. | N2a, 4-week check | Gated (owner may pull forward) |
| 3 | `add-announcement-tags-and-insider-sizing` (N3) | Type tags, "needs a look" versus "for information", insider event parsing, shares outstanding from `ratio_summary()` cross-checked with `overview()`, benchmark and fallback, source-health line. | N1, N2a (not N2b) | Not started |
| any | `evaluate-band-against-trailing-stdev` (E1) | Read-only study with a kill criterion stated first; the band may be no better than a plain trailing-stdev band (0.431 vs 0.424). | none | **Run 2026-10-12** (208 symbols, 2020 to 2026, 334,341 windows). Against the trailing 20-session band: `NOT_BETTER` (relative gain +0.6%, 97.5% month-block interval -0.4% to +1.7%, so the study neither shows the HAR band better nor the trailing band better; the pre-registered 2% margin is ruled out). Against the fitted constant band: `HAR_BETTER` (+9.0%, +7.0% to +11.1%, positive in 7 of 7 years). Per the pre-registered consequence this allows a follow-up change that swaps in the simpler trailing band, only if the owner decides; it does not stop the weekly brief. Detail: the change's `design.md` ("Result" and "Decision record") and `docs/MODEL_CARD.md`. |
| gate | `retire-debate-engine-and-verdict-ui` (C1) | Removes the debate engine and verdict UI; needs a band-only log writer first; must also delete the Agreement clause of Rule 4 and the "agreement label is transitional" requirement. | 4-week check | Waiting |
| gate | `archive-experiments-and-dead-model` (C2) | Small cleanup of the retired XGBoost code and one-off scripts. Scope is a guess from file names only: `backend/app/ml/training.py`, `feature_engineering.py`, `docs/MODEL_CARD.md`, and the one-off scripts in `backend/scripts/`. HAR-RV (`volatility.py`, `train_har_rv.py`) stays. Needs a read-only inventory of what imports what before it is written. | 4-week check | Waiting |

**Small tasks (not proposals)**
- Replace the "TBD" Purpose line in `openspec/specs/domain-rules/spec.md`.
- Fix the stale Rule 6 quote in the docstring at `backend/app/services/debate/prompt_safety.py:2`.
- Commit the working tree in separate commits (rules and disclaimer; archives and spec syncs; agents and
  discussion docs). Nothing is committed yet.

**Open items outside the proposals**
- Personal-use premise (task 1.2 of R1, deferred): confirm account and machine ownership, the vendor licence and the
  "not to be shared" note on the company-feed log with legal or compliance before anyone else receives output.
- The 3-question real-people check of the brief has not been run; only simulated readers have tried it, and they
  are not evidence about real users.
- The 4-week check needs real briefs, so N1 starts that clock.

**Suggested order:** small tasks and commits, then N1, then N2 and N3, E1 whenever convenient; C1 and C2 wait for
the check.

### Where each part of the v5.3 brief goes (added 2026-10-12)

The status table above names the proposals; this maps Appendix K's template and build notes onto them. It is a
proposed split, not decided.

| v5.3 part | Proposal |
|---|---|
| Header lines (refresh time, per-holding warning when the last bar is old, "does not update during the week", "does not predict direction") | N1 |
| HOLDINGS LISTED line and its upper-bound sentence (two or more holdings) | N1 |
| Position block: close, value, gain/loss on price | N1 |
| THE WEEK JUST ENDED, including the first-brief case with no previous range | N1 (needs the issued-brief log) |
| NEXT 5 TRADING DAYS: range in VND, "about 2 weeks in 3" | N1 |
| Optional "biggest weekly fall or rise in 2 years" line | Off until measured and read by real people; not in N1 |
| YOUR LEVELS, footer, short disclaimer | N1 |
| Holdings entry: ticker, shares, cost, purchase date, "shares as of <date>", levels with entry dates | N1 |
| Not-a-feature work: refresh before compute, issued-brief log, file outside the repo plus `.gitignore`, output outside `reports/`, `--redact`, no model client, brief-disclaimer guard test, `TRANSACTION_VERBS` narrowing, agents re-read | N1 |
| DIVIDENDS block, net line (only when the dividend list is complete), share issues since purchase | N2 |
| Position block after a share issue (count and cost per share, calculated, check with broker) | N2 |
| "Ex-date in the window" and "Share issue in the window" lines | N2. Their wording is elided ("...") in the v5.3 template; take it from Appendices B and C. |
| COMPANY block: needs a look / for information / scheduled, type tags, unclassified notice, source line | N3 |
| Insider or major-shareholder trade: name from the title, size against shares outstanding, benchmark with its basis, "window runs longer than this brief", "does not account for this announcement" | N3 |
| Fallback when the share count is changing | N3 (uses N2's share-issue handling) |

Note for the N1 design: the v5.3 footer mentions announcements. Until N3 lands, the N1 footer must mention only
the investor's own levels.

### Items from the early plan ("Proposed changes, in order") (added 2026-10-12)

| Early item | What became of it |
|---|---|
| 1. Headline block | Replaced by the brief (N1) |
| 2. Stability: Macro volatility-relative thresholds, window-start sensitivity, "changed since last week", acceptance tests | Matters only while the debate verdict is displayed, so it goes away with C1. "Changed since last week" is covered by THE WEEK JUST ENDED. The acceptance tests were called scope creep by the review. Not scheduled. |
| 3. Company calendar line | N3. The Q3-date guess was cut (no earnings calendar in the feed; scope creep). |
| 4. Holdings input, dividend-aware P/L | N1 and N2. User-entered selling-cost and tax rates were cut (no verified rates). |
| 5. Scoreboard, dedupe of re-run rows | Deferred until 30 or more scored reports exist. The dedupe (5 duplicate rows for 2026-10-07) belongs with C1's log writer. |
| 6. Defer: band touch-rate, Fibonacci, regime label | Unchanged |

### v1 kill criteria (from the review; carried forward, added 2026-10-12)

After 4 weeks of real use, stop or rethink if: (1) the owner cannot name one week where the brief showed
something the broker app and its notices did not, or opened it unprompted in fewer than 3 of 4 weeks; or (2)
over the modelled tickers the band is no better than a constant ±2.5% range or a trailing 20-day-stdev band
(E1 tests this). These are the gate for C1 and C2.

### Corrections to the first version of this status record (added 2026-10-12)

- Decision 8 (foreign-flow snapshots) is not simply missing from the proposals. The review revised it to
  "defer" and every brief draft from v5 on lists it as deferred. What is missing is the owner's recorded
  confirmation of the deferral; see decision 8 above.

### N1 and N2 shaping session (added 2026-10-12)

**Decided by the owner**
- N2 is split into N2a and N2b (status table). N2b waits for the 4-week check unless the owner pulls it forward. N3's
  fallback needs only N2a's count-changing-issue rule.
- Holdings live in a TOML file outside the repo (file mode 600, directory 700), never in `app.db` or any database
  (`app.db` is rebuildable, pytest's lifespan runs against the real file, the API has no auth). The issued-brief log is
  a JSONL file in the same directory. Neither is under `reports/`.
- The redacted copy (`--redact`) keeps tickers and drops everything derived from holdings.
- Week-1 recompute: percent only, labelled "recomputed today from prices up to <date>; not an issued range", never
  written to the issued-brief log. **Placed in N2a, not N1**, because of the test below. N1 prints "first brief: no
  previous range".

**Measured 2026-10-12 (read-only; scripts were in the scratchpad, not the repo)**
- Recompute against issued bands: for 6 distinct ticker and date pairs in `debate_log` (SAB 10-07, 10-08, 10-09; VPB
  10-05, 10-07; ABS 10-07) the band recomputed from today's stored closes up to `as_of`, with the current model, equals
  the issued band to two decimals. A constant rescale of earlier closes cannot change log returns, so a later ex-date
  does not change the band percentage.
- Ex-date after the issue (SAB ex 2026-07-28, 3,000 VND; raw prev close implied 46.60, factor 0.9356): band percentage
  identical (2.77 and 2.71), but the recomputed VND range is 6.4% lower than the one an investor would have seen
  (as_of 07-23: 45.69 to 48.30 issued, 42.75 to 45.19 recomputed), and for the window containing the ex-date the board
  move was -7.65% (outside the band) against -1.30% (inside) in adjusted terms. **A recompute or an adjusted-space
  comparison reports "inside" for a week where the broker shows a large fall, unless the ex-date is stated.** Detecting
  the ex-date needs the feed, so the fallback and the dividend-aware wording of THE WEEK JUST ENDED belong to N2a; N1
  compares in adjusted return space (stored closes) and does not claim more.
- Retrain: the model's per-year fold `k` ranges 1.186 to 1.260 (served 1.1927); SAB's latest band would be 2.68% to
  2.84% against 2.69% served. Small, nonzero. The issued-brief log should store the model version (`debate_log` stores
  `model_sha256`).
- Provisional close: VPB 2026-10-05 has two logged rows with closes 22.90 and 23.00 (stored final 23.00), consistent
  with a run before the close. The brief should be run after the close and log what it issued. (Inference.)

**Code findings for the N1 proposal (read from the code 2026-10-12)**
1. `load_ticker` catches only `RateLimitError`; vnai's limiter `sys.exit`s. Wrap each refresh with the existing
   `_is_rate_limit_exit` and degrade to "refresh failed; last bar <date>".
2. `compute_range` has five non-happy statuses; each holding needs plain wording and must not vanish. `uncalibrated`
   has a band but no `range_coverage`, so the "about 2 weeks in 3" sentence cannot be shown for it. SAB, VPB and VIB are
   in the 208-ticker universe (coverage 0.68).
3. Derive the coverage sentence from `coverage_phrase`; the brief disclaimer hard-codes "About 2 weeks in 3", so its
   guard test compares with `docs/DISCLAIMER.md` and also ties the phrase to `model.range_coverage`.
4. No trading calendar exists (`macro.py` says so). Anchor on the last bar date ("the 5 sessions after <date>"), not
   "Mon to Fri"; the week just ended is the last 5 stored sessions.
5. `--redact` as drafted is reversible: gain or loss percent plus the close gives the cost, and "level N% below the
   close" gives the level. Drop cost-derived and level-derived percentages, weights, amounts and the free-text rule.
   Test that no holdings-derived number survives.
6. `TRANSACTION_VERBS` has one user, the debate export test; it never sees the brief. N1 needs a new guard over the
   brief's tool text with the investor's verbatim rule block stripped first. The old test goes with C1. Confirm when
   writing the proposal.
7. The "no model client" check is feasible: `compute_range`'s import closure reaches `news_feeds` (httpx, defusedxml
   only) and `debate/__init__.py` is a comment; scan `sys.modules` after importing the brief.
8. Holdings entry: TOML (`tomllib`), fields ticker, shares, shares_as_of (default purchase date), cost,
   purchase_date, and levels (comparator, price, entry date, verbatim text). Refuse to read a file that is group or
   world readable.
9. Layout follows `snapshot_company_feed.py`: a package `backend/app/services/brief/` plus a thin script. Run after the
   close.

**N2a rules proposed (from stored data; small samples)**
- Dividend completeness: complete for a holding iff `purchase_date >= oldest stored event published_at + MAX_LAG`.
  Announcement to ex-date lag over stored DIV events: SAB 8 to 85 days (n = 18), VPB 2 to 20 (n = 4); two tickers only.
  SAB's oldest event is 2017-05-15, VPB's 2022-07-19.
- Count-changing issue: `event_code = 'ISS'`, non-null `exright_date`, `exercise_ratio > 0`. Separates all four stored
  ISS rows (SAB 100% bonus ex 2023-09-14 and VPB 26.04% stock dividend ex 2026-09-24 change the count; VPB's private
  placement and employee issue, both without an ex-date, do not). No rights issue is stored, so the "calculated,
  check with broker" label stays.
- Isolation test: `test_company_feed_isolation.py` fails in two places if the brief package references the feed
  (`test_no_module_outside_the_package_references_the_company_feed` and
  `test_only_the_script_and_the_tests_import_the_package_outside_it`). Amend both to allowlist one adapter file; keep
  the no-route, no-startup and no-debate tests. The spec's "read by nothing else" becomes "the snapshot script and the
  brief's one adapter".
- Freshness: the log holds SAB and VPB only (none for VIB); the last fetch was 2026-10-10 and the snapshot runs only by
  hand. The DIVIDENDS and "Scheduled" lines must say when the feed was last fetched, and distinguish "never fetched"
  from "nothing found". The brief may print the snapshot command but must not run it.
- "Ex-date in the window" cannot use a trading calendar; approximate with calendar days and print the exact date.

**Not verified**: vendor adjustment lag after an ex-date (the log-ratio detector for re-adjusted prices depends on it);
the 85-day maximum lag beyond SAB; behaviour for a rights issue; a retrain on live data.

**Verification results (added 2026-10-12; live probes and a wider feed snapshot)**
Probe scripts live outside the repo in `~/stock-foresight-probes/`. They were run with a persistent vnai home, pauses
between calls and no retry; the feed log gained VIB, FPT, VNM, HPG, MWG, VCB, KBC and SSI (16 calls through the
project's own snapshot script).
- `ratio_summary()` (`Company(source="vci", symbol=S)`, 41 rows by 61 columns for SAB and VPB): period columns are
  `year_report` (int) and `quarter` (int); `year` is a string, do not sort by it. The count is
  `number_of_shares_mkt_cap` (int64). `ratio_type` is `RATIO_TTM` (33 rows) or `RATIO_YEAR` (8 rows, annual, with
  quarter = 5). Take the latest **`RATIO_TTM`** row; an unfiltered sort by year and quarter would pick an annual row.
- The latest TTM row is live, not "as of the quarter": VPB's 2026-Q2 row already shows 10,000,000,000 after the
  2026-09-24 stock dividend. Label the count "latest-quarter row, fetched <date>", not "as of <quarter>".
- `overview()` returns four `issue_share` columns (duplicate names; read by position). SAB: all four equal the
  ratio_summary count. VPB on 2026-10-12, 18 days after the ex-date: two columns 10,000,000,000 and two
  7,933,923,601, while ratio_summary already shows 10,000,000,000. So the vendor updates the sources at different
  times, the disagreement rule fires, and it is a real signal. When both sources are still equal and old right after
  an issue, only a settling window catches it (one example, so the length is a policy, not a measurement).
- Announcement-to-ex lag over 44 cash dividends in 9 tickers: maximum 85 days (SAB; the next is SAB at 81), every
  other ticker 21 days or fewer (VCB 21, SSI 17, VPB 20). The 120-day `MAX_LAG_DAYS` margin stands, and the long lags
  look like a SAB trait.
- **The N2a count-changing rule (ISS, non-null ex-date, ratio above 0) is wrong.** Against 40 stored issue rows (an earlier draft of this note said 41; a recount gives 40) from
  10 tickers it also fires for employee issues ("Phát hành cho CBCNV", FPT, MWG, SSI, VIB, ratios 0.1% to 0.5%, most with
  an ex-date), for KBC's private placement (ex 2025-06-24, ratio 32.6%), and for SSI's rights offer to existing
  shareholders (ex 2025-12-08, ratio 20%), none of which change an existing holder's share count automatically. It
  also misses VCB's 12.8% bonus announced 2026-04-28 with no ex-date yet. What fits: only titles for a bonus issue
  ("Cổ phiếu thưởng") or a stock dividend ("Trả Cổ tức bằng Cổ phiếu") change the count, and only once an ex-date is
  set; a rights offer is shown as "read the notice", never calculated; the rest are listed, not applied. N3's widened
  denominator rule (any ISS or AIS after the quarter) would withhold sizing after every trivial employee issue; a size
  threshold or the disagreement rule alone would be better.
- Adjustment lag, upper bounds only: MWG's cash dividend (1,000 VND, ex 2026-10-07) was already applied in vendor
  history when fetched on 2026-10-12 around 11:50 ICT, at most 3 sessions later (ratio to the stored closes 0.9867 to
  0.9869, constant across bars); FPT's 10% bonus (ex 2026-09-21) shows exactly 1/1.1 (0.9091); SSI, VIB and VPB were
  already adjusted by their stored load times (+21, +25 and +13 days). Conventions confirmed: stock factor 1/(1+ratio),
  cash factor (price minus dividend) over price, a constant rescale of every earlier bar. **No lower bound exists
  yet**; the feed holds no future ex-dates today, so `adjustment_lag.py` has nothing to watch until the next
  announcement.
- Still open: a lower bound on the adjustment lag; whether the 85-day maximum and the title classes hold beyond these
  10 tickers; how long the settling window after an issue should be.

**Owner decisions on the four proposals (added 2026-10-12)**
Five simulated readers (P1 to P5, one per profile, same model as the author, caricatures, n = 1 each) answered ten
investor-facing choices from a neutral pack. Their answers informed the defaults below; they are not evidence about
real investors. (The pack's Q5 example mixed numbers: 46.60 to 43.40 with a 3,000 VND dividend gives about -0.5%
excluding the dividend, not the -1.3% printed; it did not change the picks.)
- Personal use confirmed by the owner: the tool is used by the owner only, not commercially. No Rule change.
- N1: narrower ignore patterns (`holdings*.toml`, `holdings*.jsonl`, `holdings*.json`); VND range edges as
  `close x exp(-/+ band/100)`; label "Usual range (typical 5-session move)"; unit line; `cost` required;
  `--no-refresh`; staleness 5 days; provisional-bar warning at the top of the brief and "(provisional)" on the close,
  never a refusal; a counts-only line of re-read triggers near the top, with no judgement words.
- N2a: the level note stays on its own line under the level; UNCLEAR threshold is 2 daily sigmas (Rule 3); both moves
  shown for an ex-date week with the dividend explanation in the same line as the board move; undated announcements
  shown 365 days, then one line saying how many older ones are no longer shown; `MAX_LAG_DAYS` 120.
- N3: no Rule 6 carve-out; a registered trade reads "filed a notice of a sale (or purchase) of <qty> <TICKER> shares
  (window ...; status: not started, under way or ended)"; sizing on by default with `--no-sizing` (the `ratio_summary`
  free-tier terms stay unchecked, accepted for personal use); stored titles shown (personal use); 30-day settling
  window and 1% materiality; small share issues summarised in one counted line; the triggers line extended with
  announcement triggers.
- E1: margin 0.02, the fitted constant decides, a MODEL_CARD paragraph for every outcome, month blocks, flag-only after
  a "not better than constant" result, independent of N1.
- Not adopted: showing an adjusted version of the investor's level (the tool never adjusts it), and computing what
  following the investor's own rule would realise (Rule 6 limits the tool's words about a level to reached or not
  reached and the distance).
- Foreign-flow snapshots (decision 8) stay deferred; the 4-week check remains the gate for N2b, C1 and C2.
- Remaining open items resolved the same day, as recommended by the assistant: the triggers-line banned-word list
  keeps its words and adds "recommend" and "consider", matched as whole words (a substring ban on "act" would reject
  "exact" or "contact"); levels that could not be checked are appended to the triggers line as a count with the
  reason; `AIS` listings go to "For information" and are not counted; employee issues of missing or zero ratio are
  counted in the quiet summary as "under 1% of the shares or of unstated size"; the redacted copy gets no
  announcement-only line; the week line stays percent only; the older-announcements line does not say whether items
  lapsed. DISCLAIMER.md's heading "Brief version" is authoritative; the `domain-rules` spec's "Brief disclaimer" wording
  is aligned by the small tasks below, not inside any of the four changes.
- **N1 applied 2026-10-12** (`add-weekly-holdings-brief`): all 42 tasks ticked, full backend suite 1,788 passed,
  line coverage of `app/services/brief` about 96% (measured with a trace script; `pytest-cov` is not installed). A
  security review and a code review ran on the code before N2a started and their fixes are applied (recorded in the
  change's design.md, "Review fixes 2026-10-12"): the issued log no longer stores levels, `--out` is refused anywhere in
  the repo, the redacted copy drops all log-derived week text, and the log and holdings files are opened without
  following symlinks. No Open Question defaults were needed (all were answered). The 4-week clock starts at the first
  real run, which has not happened: no real holdings file exists yet. Decisions still pending from the reviews: quoting
  the investor's level text, and restricting `brief-auditor`'s tools (`Bash(sqlite3:*)` can read any file with
  `readfile()`).
- **N2a applied 2026-10-12** (`add-dividend-and-ex-date-lines`), after a re-diff against N1's final, review-fixed
  code: full backend suite 2,049 passed. The brief gains the feed adapter (`feed_source.py`, the only brief file that
  references the company feed; `test_company_feed_isolation.py` now allowlists exactly it), dividend and share-issue
  lines, an ex-date window with the shifted range, the combined week line, the adjustment-status check, the
  "older announcements no longer shown" line and the week-1 recompute. Real-data checks (read-only, counts only):
  the keyword classes over 40 stored issue rows are BONUS 10, STOCK_DIVIDEND 8, PRIVATE_PLACEMENT 8, EMPLOYEE 13,
  RIGHTS_OFFER 1, OTHER 0, with no row matching two classes (15 count-changing); the adjustment-status check over 59
  stored events gives 36 ADJUSTED, 20 UNCLEAR, 0 NOT_YET_ADJUSTED and 3 with no stored ex-date bar; the week-1
  recompute equals the issued band in 5 of 6 `debate_log` pairs (VPB 2026-10-07 differs, 3.45 against 3.41, because
  the issued run used a provisional close). The real feed log was not changed by the apply or the test run. The
  `openspec/specs` are not synced: N1 must be synced before N2a.
- **N3 applied 2026-10-12 to 2026-10-13** (`add-announcement-tags-and-insider-sizing`), after a re-diff against N1 and
  N2a as built, then a security review whose fixes are applied: the Rule 6 scan now exempts the investor's level text
  by position (a one-character level text could hide a tool word under the earlier substring removal), the
  third-party sanitiser strips invisible variation and filler characters and maps look-alike quotes, the redacted copy
  shows no title and no counterparty name (it goes to a language model; the full copy still shows them for personal
  use), any `SystemExit` from the share-count call degrades to "size not shown", and the first vendor failure in a
  run stops further share-count calls. Full backend suite 2,852 passed, 10 skipped. A scan of every changed or new
  file against all 1,040 stored titles and 134 counterparty names found no hit. Task 2.4 done 2026-10-13: the keyword classes capital,
  meeting and personnel are enabled after a labelled check (38, 28 and 7 claimed titles, none wrong); dividend (2 wrong)
  and results (9 wrong) stay disabled; the labels were written by an AI model at the owner's request, not by the owner,
  and only claimed titles were labelled, so missed titles are unmeasured. Still pending: task 5.2 (a run on real holdings, never
  done by an agent). Done 2026-10-13: the three agent definitions were re-read against the finished brief (task 5.4);
  `brief-auditor` lost `Bash(sqlite3:*)`, `Grep` and `Glob` (the `sqlite3` CLI reads any file with `readfile()`) and now
  queries only through `backend/scripts/brief_audit_query.py` (three fixed databases, `mode=ro`, one SELECT, an
  authoriser that refuses everything but reading; 20 tests); `reader-sim`'s `ANNOUNCEMENT_STATUS` now takes "not started,
  under way, ended" (earlier runs used planned, executed, unclear). `Read` is still granted to the auditor and cannot be
  limited to one path in an agent definition: a Read deny rule for `~/.config/stock-foresight/**` in the owner's own
  settings would close that, and is not set. The effect of the sized line against the fallback remains untested with real
  people, and the 4-week check will include whether the owner used the COMPANY block (task 5.5).
- **Security finding, history (added 2026-10-13):** earlier versions of this file, already pushed to `origin/main`
  (commit 308aa45), quoted a stored insider-trade title that names a private individual with a share quantity, and
  two company announcement titles. They are replaced by placeholders in the working tree; git history still holds the
  originals. Whether the repository is public is unchecked, and rewriting history is the owner's decision. A press
  headline in `DISCUSSION_describe_not_vote_redesign.md` and a real-looking sample row in
  `backend/tests/company_feed_helpers.py` (both older) were not changed.
- Small tasks (not proposals), done 2026-10-12: the "TBD" Purpose line in `openspec/specs/domain-rules/spec.md` is
  replaced and its "Brief disclaimer" wording now says "Brief version"; the Rule 6 quote in the docstring at
  `backend/app/services/debate/prompt_safety.py:2` now matches the current rule (`test_domain_rules_in_sync.py` and
  `test_prompt_safety.py` pass, 68 tests). Still to do: commit the working tree in separate commits (the three edited
  files and the four change folders).

**Consolidated handover (added 2026-10-13):** `docs/WEEKLY_BRIEF_HANDOVER_2026-10-13.md` summarises what was built, the evidence, the reviews, the concerns and the open items, and records the deferred idea of entering holdings through a database and UI.
