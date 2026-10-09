# Discussion: The agents say little, the verdict is a vote nothing supports — toward "describe, not vote" (2026-10-08)

Raised on 2026-10-08 while reading `reports/2026-10-08_SAB.md`. The owner's concerns: the
News Context and Macro agents are weak and give no meaningful context, and Technical Signal
uses only three indicators. An exploration session followed. This file records what was
found, what the owner decided, what is only proposed, what was left open and what to do
next, so a later session can continue without redoing it.

**Status**: open. Nothing here is implemented except one read-only study script and its tests
(`backend/scripts/evaluate_fibonacci_levels.py`, `backend/tests/test_evaluate_fibonacci_levels.py`),
untracked at the time of writing. Items that change a rule or the shape of the product are
`/opsx:propose` territory (`CLAUDE.md`: ask before changing a domain rule).

**How to read the numbers.** Everything marked *measured* came from read-only queries, live
probes or scripts run on 2026-10-08 (database opened `mode=ro`). Figures from other docs are
cited as such. The scratch probe scripts for `vnstock` and the SAB Fibonacci example were not
kept; the calls to reproduce them are in "Reproducing". The Fibonacci study script is in the
repo. Anything under "Not verified" was not checked.

**Independently checked.** After this file was first written, three fresh agents (no memory of
the session) cold-read it, fact-checked it against the repo, and reproduced its `vnstock`
probes. Their corrections are folded in below; "Verification notes" at the end lists what each
found and what was not fixed.

**Second opinion.** On 2026-10-09 one more fresh agent answered three of this file's questions
without seeing the assistant's answers and re-checked seven of its facts; see "Second opinion
and revised order". It proposes a different order of work. On 2026-10-09 the owner confirmed
the scope of step 1, the interim state, the parts headline and eight recommended defaults; see
"Settled for step 1" and "Decided 2026-10-09". The
proposals to run, and which can start in parallel, are in "Proposal breakdown and parallel
start".

## Glossary

- **SAB** Sabeco (beer), **VPB** VPBank: the two tickers used as examples. **HOSE** Ho Chi Minh
  exchange. VND amounts: "B" = billion.
- **VCI, KBS**: data providers reached through the `vnstock` library (sources `"vci"`, `"kbs"`).
- **`[ticker]` / `[sector]` / `[market]`**: tags the News agent puts on headlines: names the
  stock / about its sector / market-wide or macro.
- **Tenkan-sen, Kijun-sen, Ichimoku**: fast and slow lines of the Ichimoku indicator (rolling
  highs/lows); **RSI** momentum oscillator; **MACD histogram** momentum difference; **OBV**
  on-balance volume; **ATR** average true range; **Bollinger** volatility bands.
- **Typical 5-session move**: the range the HAR-RV volatility model gives, e.g. ±2.9%, with its
  stated coverage ("about 2 in 3 recent moves inside"); daily σ in this doc is either the model's
  forecast (1.09% for SAB) or a trailing 60-session standard deviation of daily log returns
  (1.24%, used by the Fibonacci work). They are different estimates.
- **TTM P/E, EPS**: price over the last four quarters' earnings per share.
- **Ex-dividend (ex-right) date**: from which a buyer no longer receives the dividend. **AGM**
  annual general meeting.
- **IC / effective breadth**: rank correlation of a signal with outcomes / the number of
  independent bets in a universe (both from `DISCUSSION_model_direction.md`).
- **Zigzag, scale m**: a swing detector; a pivot is confirmed after a reversal of `m` × daily σ.
  **Leg**: the move between two confirmed pivots.
- **Placebo, excess hold rate**: the Fibonacci study compares Fibonacci ratios with nearby
  non-Fibonacci ratios; "excess" is the difference in how often a level held. **Ticker-year**:
  one ticker's one year of sessions. **Modelling universe**: the 208 tickers the system models.
- **Setup**: the proposed descriptive headline label (draft: Quiet / Active / Event-driven /
  Stressed). Not a trading "setup".
- **Rail, Stage, Verdict panel, Debate matrix**: the dashboard's ticker list, chart area, right
  panel and the grid of agent cards.
- **Fencing**: wrapping third-party text in delimiters so a prompt treats it as data
  (`prompt_safety.fence`). **`claude_cli`**: the language-model provider that runs a debate in
  about 45 s. **Kill criterion**: the result that stops an idea.

## Summary

1. For SAB on 2026-10-08 the report gives an investor little beyond the typical-move range
   (±2.9%). Its own text says "no stock-specific evidence from any agent". "Majority (2 of 3)"
   was two neutral votes, neither backed by stock-specific evidence, not agreement.
2. The three agents are not three independent sources. Technical reads one price history three
   ways, Macro reads market-wide numbers identical for every stock (plus one relative-price
   signal), and News (three general RSS feeds) found zero SAB/Sabeco items.
3. The repo's own evidence says price indicators carry no usable directional edge (a small,
   sign-stable cross-sectional momentum effect at 5–10 sessions was judged not usable); volatility
   is the only thing found predictable. More directional indicators would probably add correlated
   noise (asserted from that evidence, not tested here).
4. A per-ticker company-news source exists in `vnstock` (VCI `Company.news()` / `events()`),
   and a working valuation series (`Company.ratio_summary()`). The library's `Finance.ratio` is
   broken for VCI and KBS labels are wrong (see probes).
5. Owner direction: stop voting and describe; a rule-assigned **Setup** label whose job is
   testable. See "Decisions" for what the owner chose literally versus what was proposed.
6. Fibonacci retracement/extension levels can be shown as descriptive reference levels. A
   placebo study found no consistent special behaviour at Fibonacci ratios under one definition
   (2 of 20 cells nominally significant, about 1 expected by chance, not replicated early).

## Trigger: the SAB report (2026-10-08)

- Verdict "Observe", Agreement "Majority (2 of 3)". Technical ↓ Bear, News → Neutral,
  Macro → Neutral. Typical 5-session move ±2.9% (about 2 in 3 recent moves inside).
- Technical: RSI 41.4, MACD histogram -0.0652, Tenkan 43.08 < Kijun 43.97. Its own bullets
  call the magnitudes small and the confidence moderate.
- News: all ten headlines tagged `[market]`; none `[ticker]` or `[sector]`.
- Macro: VN-Index down over 20 sessions, SAB +1.19% relative to the index, USD/VND +0.06%
  over 5 sessions, 30 large caps net foreign selling 134B VND (5.5% of gross).
- Key Tension (language-model text) says no agent had stock-specific evidence that separates a
  SAB downtrend from the soft market.
- Round 2 is circular: Macro cites "the News agent's data supports this" and News cites Macro.
- The two foreign-flow figures in the report (134B over 30 large caps, 415B in the news
  headline) are different universes and read as a contradiction.

## Findings

### Technical Signal (`backend/app/services/debate/technical.py`)

- Stance = bull if more of three signs are bullish than bearish (bear likewise; ties neutral):
  RSI vs fixed 55/45 (between them casts no sign), MACD histogram sign, Tenkan vs Kijun sign.
  Magnitude of MACD and Ichimoku is ignored, so a -0.065 histogram on a price near 43 counts
  fully.
- RSI and MACD are transforms of the close, Tenkan/Kijun of rolling highs and lows: one price
  history, so extra oscillators add correlated votes, not information.
- Columns already in `features` and unused by the agent: `obv`, `atr`, `bb_upper/middle/lower`.
- **Existing evidence (cited, not re-run)**: `docs/DISCUSSION_model_direction.md` Findings 3, 4,
  5 and 9: stationary technical features (RSI, Bollinger, ATR, momentum) predict 5-session
  direction at about zero with unstable sign; no horizon from 5 to 252 sessions beats "always
  up"; cross-sectional momentum at 208 symbols has a small sign-stable effect at 5–10 sessions
  (IC 0.03–0.04) with effective breadth ≈ 3.2, judged "not usable"; volatility is predictable
  (corr ≈ 0.44–0.48 for the better approaches).
  `docs/DISCUSSION_post_pivot_review.md` Finding 4 measured the RSI/MACD/Ichimoku vote at 49.2%
  hit-rate (n=330,617) vs a 48.7% base rate. That review predates several refactors; the
  directional numbers were not re-run.

### Macro (`macro.py`)

- Four signals: VN-Index 20-session slope, ticker 20-session return minus VN-Index return
  (same two dates), USD/VND 5-session change, summed foreign net flow over a 30-stock sample
  (latest session only). The foreign-flow signal does not vote on weekdays between 09:00 and
  15:15 Vietnam time while the board settles, and does vote at any other time (before 09:00,
  after 15:15, weekends).
- The 2026-10-08 neutral was four signals netting to zero (per the debate log's stored
  evidence): VN-Index slope -1; SAB relative return +1.19 pts, above a fixed 1-point threshold,
  +1; USD/VND 0; foreign flow -5.5% of gross, inside ±10%, 0. So Macro was not abstaining; its
  signals cancelled. Note the fixed thresholds in `macro.py` (1 point for relative return, 0.5%
  for USD/VND) are not volatility-relative, which sits uneasily with Rule 3.
- Identical for every ticker except the relative-to-index signal, which is really a price
  signal. No rates, breadth, liquidity trend or valuation. The News agent surfaced turnover at
  about half last year's level and a possible Fed hike; Macro never sees either.
- `_get_sector_closes` (macro.py) always returns `None` and is not called: dead code.

### News Context (`news.py`, `news_feeds.py`)

- Sources: `vnexpress.net/rss/kinh-doanh.rss`, `cafef.vn/thi-truong-chung-khoan.rss`,
  `vietstock.vn/830/chung-khoan/co-phieu.rss`. 7-day window; the feeds themselves held items from
  only 2026-10-05 to 10-08 when measured. Tags: ticker (symbol as a whole word in title/snippet),
  sector (keyword list), market (regex). Caps: 5 / 4 / 10.
- **Measured 2026-10-08, reproduced by a second agent**: 60 + 50 + 20 = 130 items across the three
  feeds; zero contain "SAB" or "Sabeco" in title or description, zero titles contain "bia". One
  ticker and one day: for a mid-cap the agent will often see only `[market]` items. The open
  "company aliases" question (archived design) would not have helped here: the cause is source
  breadth.
- With no stock-specific headlines the agent still votes neutral, and that neutral counts
  toward "Majority".

### Vote and verdict mechanics (`engine.py`, `synthesiser.py`)

- Already present (confirmed): `AgentPosition.degraded_reason` (`agent_error | no_input |
  llm_failed | round2_failed`); a degraded agent does not vote; fewer than two live agents gives
  `INSUFFICIENT_DATA` with no language-model call; two live agents agree → "majority" at most,
  disagree → `SPLIT`; `agents_degraded` and `data_age_sessions` are in `DebateResult`; ineligible
  tickers abstain before any agent runs. So abstention alone is a small change (a new degraded
  reason, e.g. `no_evidence`).
- **Interaction problem**: if News abstains for lack of stock-specific evidence and Macro stops
  voting, only Technical is left and the existing rule returns `INSUFFICIENT_DATA`. If only
  News abstains, SAB today becomes Technical bear vs Macro neutral = `SPLIT`, which implies two
  equal opinions disagreeing although Macro's neutral is not stock-specific. This is why the
  vote itself is proposed to go (see Decisions).
- The API `Verdict` enum keys still read `STRONG_BUY_SIGNAL / BUY_SIGNAL / CAUTION_SIGNAL /
  STRONG_CAUTION_SIGNAL`. **Display labels** (`frontend/src/lib/debateText.js` `VERDICT_CONFIG`,
  identical to `export.py`): Strong bullish lean, Bullish lean, Observe, Bearish lean, Strong
  bearish lean, Split — no consensus, Insufficient data. No buy/sell/hold wording, so
  `DISCUSSION_post_pivot_review.md` Finding 7 is fixed on the display side; the "lean" labels and
  their arrows are still directional wording that a describe-only design would replace.
- A debate is 8 language-model calls (3 agents × Round 1, 3 × Round 2, 2 synthesis), about
  45 s (`TYPICAL_ANALYSIS_SECONDS = 45`).

### Outcome tracking

- `backend/data/debate_log.db` has 9 rows (`as_of` 2026-10-05 … 2026-10-08) but only 4 distinct
  (ticker, `as_of`) pairs (the rest are re-runs); `outcome_status` is NULL on all; verdicts are
  OBSERVE ×4 and CAUTION_SIGNAL ×5. The first can be scored around 2026-10-12 (five sessions after
  Monday 2026-10-05). `backend/scripts/score_debates.py` already scores the band hit-rate and
  has a verdict/directional section (`_directional_section`). Whether `score_debates.py` drops
  re-runs was reported by the fact-check, not re-verified.

## Data-source probes (`vnstock` 4.0.5, community tier, measured 2026-10-08)

- **VCI `Company(source="vci", symbol=S).news()`**: 50 rows per call, titles and dates only (body,
  source, link, author columns are empty in all rows checked), company announcements and some
  press, no API key, 0.1–2.3 s. SAB: 2025-04-24 to 2026-08-28 (quiet since); 43 of 50 titles start
  with "SAB:", and whole-word `SAB|Sabeco` matches 49 of 50 (7 are press titles like "Sabeco
  (SAB) …"; one match target was another company's story, "Bia Sài Gòn - Miền Trung (SMB)", so
  matching needs care). VPB: 2026-06-10 to 2026-10-07; 48 of 50 titles start with "VPB:", all
  50 contain "VPB". The `ticker` column is `None`. The text is third-party and must go through
  the same fencing/cleaning as the RSS headlines (only the title needs it).
- **VCI `events()`**: dividends (`event_code == "DIV"`), AGMs, share issues, director deals, with
  `exright_date` (a string column with NaN: convert with `pd.to_datetime` before `.max()`).
  SAB: cash dividends 3,000 VND (ex-date 2026-07-28, record 2026-07-29, payout 2026-08-28) and
  2,000 VND (ex-date 2026-01-12); Q2 results filed 2026-07-23. No future-dated events.
- **VCI `Finance.income_statement(period="quarter")`**: the latest 4 quarters (2026-Q2 …
  2025-Q3); values in VND, expenses negative. The vnai patch caps statements by tier: guest 4
  periods, free-with-API-key 8, higher tiers uncapped (the key path was not tested). With 4
  periods there is no year-on-year view (matters for a seasonal business like beer).
- **VCI `Finance.ratio(...)` is a library bug, not a tier limit**: it returned 2018-Q1…Q4 (the
  oldest four) because `vnstock/explorer/vci/financial.py` does `combined_df.head(effective_limit)`
  (default 4) on an ascending list, and `ratio()` has no `limit` argument; `period="year"` gives 19
  columns because the four duplicate "2018" labels expand 4×4. **Use
  `Company(source="vci", symbol=S).ratio_summary()` instead**: the full quarterly TTM series since
  2018 (41 rows, newest last; pe, pb, ps, roe, roa, market_cap, shares). SAB latest (2026-Q2): P/E
  11.51, P/B 2.81, market cap 5.4958e13 at the latest price. That removes the need for daily
  valuation snapshots, but whether this route sits inside the vendor's free-tier terms was not
  checked (see Open questions).
- **KBS `ratio` / `income_statement` are unusable through the library**: the paged response's
  head and value arrays do not line up (duplicate head ids, "2025 Quý 4" twice) and the library
  pairs labels to values by position from page 1 only. Its "2026-Q2" revenue (6.509e12) is VCI's
  2025-Q3. **Settled in favour of VCI's labels (about 90–95% confidence)** by: the Q1 headlines
  (profit about 1,200B VND on 2026-04-28; "+55%" on 2026-05-06 fits VCI Q1'26 net profit 1.2454e12
  against the unlabelled column read as Q1'25, +55.8%); KBS's own report dates (Q2'26 on
  2026-07-23, the SAB filing date); four-quarter parent profit over 1,282,562,372 shares = 3,722.7
  VND = KBS's raw page-2 trailing EPS 3,722.67; and book value dropping where the 2,000 and 3,000
  VND dividends were announced. Remaining doubt: the unlabelled quarter is inferred. SAB's own
  published statement would close it.
- **TTM P/E for SAB**: parent net profit (`attributable_to_parent_company`) of the last four
  quarters = 4.7746e12 VND; EPS 3,722.7; P/E 11.55 at our 2026-10-08 close (43.0 = 43,000 VND),
  11.51 at the vendor's 42,850. Pitfalls: our `ohlcv` prices are in thousand VND, vendor price and
  market cap in VND; KBS expenses are positive where VCI's are negative and KBS EPS is ×1000; the
  share count was 641M before the 2023 bonus issue (using it doubles EPS); `Company.overview()`
  has four `issue_share` columns (equal); use parent, not consolidated, profit (consolidated gives
  P/E 11.0 and is not what the vendor uses).
- Ratio field sets differ by sector (VPB has NIM, NPL, LDR; SAB has margins, turnover; the
  other sector's fields are zero). Banks, real estate and securities are a large share of
  the 208 symbols.
- Any new module importing `vnstock` must call `app.vnstock_guard.install()` first; a repo test
  enforces it (`docs/KNOWN_ISSUES.md`). Importing `vnstock` prints a promo box and community-tier
  notices to stdout.

## Fibonacci reference levels

The owner trades with Fibonacci retracement and extension, uses extensions as both targets and
stop zones, has no fixed anchor ("can we see more than one anchor? find what works best").

- **Design**: anchors by a causal zigzag whose reversal is `m × trailing-60-session daily σ`
  (Rule 3: volatility-relative), plus the 52-week high/low. Levels of the last completed leg.
- **SAB example (measured, close 43.0, σ 1.24%; scales m=4, 8, 16 — not the recommended
  3, 6, 12, which were not computed)**: short (m=4, 5% reversal) up leg 43.10→45.50 (Sep 11→Sep
  18), price at 104% retracement, i.e. fully retraced; medium (m=8) up leg 39.34→47.20 (Mar
  30→Aug 20), price at 53%, levels 38.2% 44.20 / 50% 43.27 / 61.8% 42.34, 127.2% extension 49.34;
  long (m=16) = 52-week leg down 53.42→39.34 (Jan 15→Mar 30), price at 26%, 127.2% extension
  35.51. The long and 52-week anchors coincided.
- **Density warning**: about 11 retracement levels from three anchors fall between 42 and 46
  (about 0.8% apart), so "price is at a confluence" is almost always true. Any test needs a
  null with the same level density. (Not independently re-derived.)
- **Study** (`evaluate_fibonacci_levels.py`, 208 modelling-universe tickers, 1,598
  ticker-years, early < 2023 / late ≥ 2023; re-run by another agent, headline numbers match): at
  the first touch of each level not yet reached (touch detected on the day's high/low), does the
  close move one typical 5-session move back (hold) or through (break) within 10 sessions
  (decided on closes)? Fibonacci ratios vs a dense grid of non-Fibonacci ratios (local baseline,
  placebo p-values).
  - Excess hold rate of Fibonacci ratios: within about ±2 points (largest +2.02, extension m=6
    late). The sign flips between periods for all retracement scales and extension m=6, but not
    for extension m=2–4 (+0.01 to +0.30 in both). Base hold rate 43.6–52.0% across the 20
    reported cells.
  - 2 of 20 testable cells reach one-sided p < 0.05 (about 1 expected by chance): extension
    levels at m=3 (p=0.027) and m=6 (p=0.038), both late-period only; the m=6 early effect has
    the opposite sign. Nothing qualified in the early period (best p=0.074), so no scale could be
    "selected".
  - Extension levels otherwise behave like any other level (excess ≈ 0 at m=2–4).
  - Scales m ≥ 16 (≤ 1.1 legs per ticker-year) and extensions at m ≥ 8 have too few events;
    the long/52-week anchor is untestable here, not shown useless. The recommended m=12 is
    therefore untested for extensions.
  - Legs per ticker-year / median leg size: m=2 54 / 8%; 3 29 / 12%; 4 17 / 15%; 6 7.4 / 23%;
    8 4.3 / 31%; 12 1.9 / 44%.
- **Limits**: one hold/break definition (barrier = one typical 5-session move, 10 sessions);
  wicks, zones, volume and intraday untested; other level types (prior swings, round numbers)
  untested; overlapping events understate uncertainty.
- **Scale recommendation (readability, not edge)**: m = 3, 6, 12, plus the 52-week range.
  Show levels inside about 1–2× the typical move in the report; the full set on the chart.
- **Rule 6 issue**: "target" and "stop zone" are instructions. Proposed wording: "reference
  levels" with % distance from price and distance as a share of the typical move; no
  "target", "stop", "support" or "resistance" (Rule 6's own text names buy, sell, hold or "other
  instruction"; the last three words are this discussion's additions). Needs an owner ruling.

## Decisions

**Chosen by the owner, literally**

1. Verdict shape (assistant's option 2): stop using a vote count; show each agent's evidence
   coverage rather than a vote. "Technical: describe the state, no bull/bear call"
   (assistant's recommended option A) was chosen with it, so Technical has no stance.
2. Headline: the assistant's recommended descriptive **Setup** label (rule-assigned, option B)
   plus a "what's notable" sentence beneath ("just go as your recommendation"). *Superseded
   2026-10-09 by the owner's choice of independent parts; see "Settled for step 1".*
3. Fibonacci: apply it, with several anchors; no fixed scale, "find what works best" (the data
   did not choose; see above). Use as extensions both targets and stops: owner's own practice.
4. Preserve the Fibonacci study script and tests in the repo, and write this note.

**Proposed by the assistant, not yet confirmed by the owner**

- Remove Round 2 and the debate framing; Macro becomes context, not a voter; drop the Agreement
  label entirely (a consequence of no vote, needs Rule 4 sign-off).
- Scales m = 3, 6, 12 for readability; reference-level wording; report shows levels within 1–2×
  the typical move.
- The six-step order below, including folding company news and fundamentals into the redesign.

## Proposed design (not implemented)

- **Coverage line** per source: stock-specific / sector-level / market-only / none. Replaces
  "Agreement". A source without stock-specific evidence says so instead of voting neutral. (Whether
  sources stay as three "agents" or become "readings" cards is open; the mock-up groups by data
  source.)
- **Readings** (facts, past/present, never a forecast): price and volume state, volatility
  regime vs the stock's own history, 52-week position, Fibonacci reference levels, calendar
  (ex-dividend dates, filings), fundamentals facts (latest-quarter trend, TTM P/E), news
  items that are stock- or sector-specific, market backdrop.
- **Setup label (draft vocabulary)**: Quiet / Active / Event-driven / Stressed, assigned by
  rules from the volatility regime against the stock's own history (Rule 3), volume, upcoming
  events and market stress. No buy/sell wording. Thresholds do not exist yet and the form of the
  rule (mutually exclusive? precedence? what counts as "market stress"?) is undecided. "Stressed"
  can read as bearish; "Setup" has a trading-entry meaning that may also need a Rule 6 look.
- **"What's notable"**: deterministic facts picked from the readings. **"Where the readings pull
  apart"**: language-model text written from structured readings, marked as such (Rule 5).
- **Round 2 debate removed** (no stances to rebut). Fewer language-model calls and a faster
  run are expected (today 8 calls, about 45 s on `claude_cli`); not designed or measured.
- **How it would be judged**: band hit-rate (already scored); whether Setup labels separate
  realised 5-session moves (backtest on stored price/volume now; news, fundamentals and
  events only forward); whether flagged events occurred. No direction is claimed, so none is
  scored.
- **Backtest design caution**: volatility is predictable (corr ≈ 0.44–0.48), so a label built
  from the volatility regime will correlate with realised move size almost by construction. The
  test has to show the label adds something beyond the range model's own σ (for example by
  checking calibration of the band inside each label), choose thresholds on an early period and
  check them on a late one (as the Fibonacci study did), and define "separate" (effect size,
  baseline, universe) before running. None of that is decided.

### Mock-up of the report

Illustrative. Values in `<>` are placeholders; the Setup label does not exist yet.

```
# SAB · 2026-10-08
Setup: <label>          Data as of 2026-10-08 (current)
Typical 5-session move: ±2.9% (about 2 in 3 recent moves inside, as the band states; larger moves happen)
Evidence coverage
  Price & volume   stock-specific
  Company filings  stock-specific, last item 2026-08-28
  Fundamentals     latest 4 quarters; TTM P/E 11.5
  Sector news      none found this week
  Market backdrop  market-wide only
What's notable
  Price 43.0 is 2.2% under Kijun-sen 43.97 and Tenkan-sen 43.08 is below it; RSI 41.4
  Volatility: model daily 1.09%, <percentile of own history>
  Calendar: last ex-dividend 2026-07-28 (3,000 VND); Q3 results date not announced
  Market: VN-Index down 20 sessions; SAB +1.19% vs index
Where the readings pull apart  (language-model text)
```

### Dashboard (components read, not seen running)

| Today | After |
|---|---|
| `VerdictPanel`: `VerdictBadge` ("Observe" etc.), `agreementText`, `StanceChips`, Key tension, Synthesis, data line, report-saved line, Re-analyse | Setup badge, coverage chips, "What's notable", Synthesis kept; stance chips and Agreement removed; whether the data line, report-saved line and Re-analyse stay is not decided |
| `DebateMatrix`: 6 `AgentCard`s (3 agents × 2 rounds) | "Readings": about 4 cards, one round, each with its evidence basis |
| `RangeBlock`, `ChartPanel` range band, `Rail` rows (no stance or direction marks by design) | Unchanged; optional Fibonacci toggle and event markers on the chart; optional Setup chip in the Rail only after the backtest and a decision against the Rail's no-marks design |
| Disclaimer in every state | Unchanged (Rule 6) |

Code touched: `engine.py` (`Verdict`, `AgreementLevel`, `SynthesisResult`), `synthesiser.py`,
`export.py`, `outcome_log.py`, `scripts/score_debates.py`, `VerdictParts.jsx`,
`lib/debateText` (`VERDICT_CONFIG`, `agreementText`, `stanceMark`), `lib/verdictState`,
`DebateMatrix/*`, `VerdictPanel.test.jsx` (864 lines) and the specs `debate-engine`,
`debate-synthesiser`, `debate-panel-ui`, `technical-agent`, `dashboard-ui` and their docs. The
CodeGraph index listed 11 callers of `SynthesisResult`.

## Expected outcome (stated plainly)

- **Honest**: no more "Majority" built from votes with no stock-specific evidence; the reader sees
  what each source had.
- **Modestly more useful** (a judgement, not measured): dated facts (filings, dividend dates, a
  results date when known) beat an RSI sign. For a news-rich stock (VPB: bond-issue resolutions,
  share dividend, syndicated loans in October) the report would plausibly read "Event-driven" with
  a dense calendar; no thresholds exist, so this is hypothetical.
- **Measurable**: the first headline that is itself a scoreable claim (Setup), and no unscoreable
  one (direction); the band is already scored. Evidence accrues slowly: 4 distinct log
  ticker-days today; a nightly basket of about 25 tickers would be needed for months-scale
  samples.
- **Not predictive**: no forward direction, and nothing here claims better returns. The investor
  still decides alone.
- Mixed reception likely: informed users get a pre-trade checklist; others may miss a
  decisive-sounding verdict, and the Setup label needs a one-line explanation.

## Risks and concerns

- The Setup label may not separate realised moves beyond what the range already says; then fall
  back to no label (headline = range + notable sentence).
- A Setup label can read as direction ("Stressed") or as a trade pattern ("Setup"); Rule 6 check.
- Free-tier fundamentals are shaky (guest tier 4 periods, `Finance.ratio` bug, KBS labels wrong);
  coverage will vary by sector, so reports will look uneven. Make coverage visible rather than
  hiding it. `ratio_summary()` may be a loophole in the vendor's tier model; check terms first.
- Removing the vote and Agreement touches Rule 4 and Rule 6 (both name Agreement) in both
  `CLAUDE.md` and `openspec/config.yaml` (they must change together) and the
  `dashboard-ui`/`debate-*` specs. "Debate" stops being the right name.
- Fibonacci: levels carpet the chart; users may read extensions as targets despite the
  wording; the study does not show them useful as barriers.
- Company announcements are untrusted third-party text going into prompts (titles only today);
  each new `vnstock` importer needs the guard; sending ticker context to a third-party model API
  is already a data-handling point in `KNOWN_ISSUES.md` terms.
- Announcement-driven news is quiet for many mid-caps (SAB: nothing since 2026-08-28); the
  News block will often say "none", which is correct but looks empty.

## Rules impact

| Rule | Effect |
|---|---|
| 1 horizon (5 sessions) | The horizon is unchanged and levels/notability are filtered to the typical move. But Rule 1's text says "Ranges and verdicts are scored against the realised `outcome_t`"; if the verdict becomes a Setup label scored on move size, that sentence needs rewording (sign-off) |
| 2 no raw log return | Unchanged; distances shown in %, and as a share of the typical move |
| 3 volatility-relative thresholds | Setup thresholds and the zigzag reversal are volatility-relative; the Setup thresholds are new and provisional. Existing fixed thresholds in `macro.py` (1 point, 0.5%) are in tension with it |
| 4 reliability measured; Agreement | Agreement removed (no vote); the range hit-rate stays the only reliability figure; Fibonacci levels carry none. Needs sign-off |
| 5 label by provenance | Rule 5's text lists the three agents (Technical Signal, News Context, Macro) and defines the technical proxy as RSI, MACD, Ichimoku, so it needs editing if Technical stops voting and Macro becomes context; also new labels (Fundamentals, Company filings, a name for Setup). "Market Sentiment" stays reserved for the technical proxy |
| 6 not advice | Rule 6's trigger names "a verdict, Agreement, a range or agent reasoning" (Agreement goes). Proposed wording for levels (no target/stop/support/resistance) is this discussion's addition; disclaimer wherever readings, range or reasoning appear |

Agreement is also named in the per-artifact `tasks` rule at `openspec/config.yaml:160-163`
("verdict, Agreement, … verdict labels from the `debate-synthesiser` display label table"), which
would need the same edit. `CLAUDE.md` and `openspec/config.yaml` carry the six rules word for word
(checked), so they must change together.

## Proposed order (each its own `/opsx:propose`; owner to confirm)

*A revised order, proposed on 2026-10-09, is in "Second opinion and revised order". This list is
kept as first written.*

1. **Setup-label backtest** (read-only script, like `evaluate_vol_range.py`) on stored price
   and volume, following the caution above (early/late split, a defined "separate", beyond the
   range model's σ). Kill criterion: if the label does not separate, drop it. Also decide
   thresholds here.
2. **Verdict shape change**: drop the vote and Agreement, add coverage line, Setup label,
   readings; rule edits in `CLAUDE.md` and `openspec/config.yaml` in lockstep; update specs,
   the panel, export, outcome log and `score_debates.py`.
3. **Company news and events from VCI** (augments the RSS feeds for `[ticker]`; match titles with
   `\bSAB\b|Sabeco`-style rules, not a title prefix).
4. **Fundamentals** v1: facts only (latest-quarter trend, dividend dates, TTM P/E from
   `ratio_summary()` or computed from four quarters of parent profit), non-financial sectors first.
   VCI labels are the ones to use (settled above); check vendor terms for `ratio_summary()`.
5. **Fibonacci reference levels** at m = 3, 6, 12 and the 52-week range, behind a chart
   toggle, wording per the Rule 6 ruling.
6. **Outcome tracking at scale** (nightly basket) so the band and Setup can be scored.

Items from the archived debate designs that stay open and are not addressed here (per
`CLAUDE.md`'s backlog pointer): prompt language, the unmeasured board-settle time (15:00–15:12),
`[ticker]` company aliases (partly overtaken by the VCI source), the rolling foreign-flow window,
removal of `/insight` and the feature flag.

## Second opinion and revised order (2026-10-09)

**Status**: recommendations, not owner decisions. Where they differ from "Decisions" above (the
owner chose a rule-assigned Setup label), the owner's choice stands until the owner changes it.
Nothing here is implemented.

**How it was run.** A fresh agent with no memory of the session got the files and three
questions (is model-written text needed, one label or several parts, does the redesign improve
the product), answered them without seeing the assistant's answers, then checked seven facts the
assistant had relied on. Limits: same model family, so shared blind spots are possible; its
fact-checks were primed with the claims; nobody ran the `vnstock` API, `evaluate_vol_range.py` or
the Fibonacci script. Figures marked *reviewer* are that agent's read of the repo and were not
re-verified by the assistant.

### Evidence added

- **Round 2 never changed a position** (*measured*): the stance in the Round 1 and Round 2
  headings is identical in all 9 saved reports (27 positions; 3 tickers, 5 dates, SAB repeated).
  The reviewer found the same in the 9 `debate_log.db` rows.
- **Round 2 can overturn a rule** (*read in code*): Technical's Round 1 stance is computed from
  indicators (`technical.py:195`) and Macro's from summed signals (`macro.py:388-389`). Both
  `respond` methods take the Round 2 stance from the first line of the model's reply
  (`technical.py:251`, `macro.py:424`), and the verdict votes on Round 2 stances
  (`synthesiser.py:187`).
- **A deterministic form of the reasoning already exists**: when the model call fails, Technical
  and Macro fall back to listing the values (`technical.py:290`, `macro.py:451-456`).
- **Model text drifts past the guards.** The VPB 2026-10-07 synthesis ends "net view is a
  cautiously constructive but unconfirmed stance … key things to watch" under an Observe verdict
  (`reports/2026-10-07_VPB.md:72`). `DESCRIBE_ONLY` is a request inside the prompt, and
  `withhold_advice` is a pattern on transaction verbs whose docstring says paraphrase gets
  through (reviewer): a gap, not a malfunction. The same report's Key Tension lists "no Ichimoku
  cloud confirmation" as a weakness of the bull case (line 23) while the agent says "I have no
  cloud data here" (line 53). The cause is input, not the stock: `technical.py:112` selects four
  columns although `features` holds `senkou_span_a/b` and `chikou_signal` (reviewer).
- **The SAB Key Tension is a coverage fact**: price signals are stock-specific, news and macro
  are market-only, relative return +1.19%. A rule can state that. The VPB one adds speculation
  ("late-stage", "may have already run ahead").
- **Stored prices are dividend-adjusted** (*measured*): SAB closed 43.60 → 43.15 (-1.0%) across
  the 2026-07-28 ex-date (3,000 VND would be about -6.9%) and 43.92 → 43.97 across 2026-01-12
  (2,000 VND, about -4.6%). `DISCUSSION_model_direction.md:317` says the same; the ex-dates are
  the ones in this file, not re-fetched. Consequences: ex-dividend windows will not fake an event
  backtest pass; the band is built on adjusted closes, so at an ex-date a live price drops by the
  dividend and the band does not include it (SAB: about 7% against ±2.9%; inference); Fibonacci
  levels and the 52-week anchors are in adjusted prices and may not match an unadjusted broker
  chart (inference, not checked against raw prices or the owner's platform).
- **Band calibration** (reviewer, from the `validation` block of
  `backend/data/models/har_rv_model.json`, rounded): 7 walk-forward folds, test years 2020–2026,
  pooled coverage 0.676 (CI 0.655–0.698), nominal 0.68. By own-σ quintile 0.695 / 0.675 / 0.661 /
  0.661 / 0.689 (largest gap 0.019). By test year 0.614, 0.613, 0.619, 0.729, 0.741, 0.720, 0.701
  (gaps -0.067 to +0.061). No market-regime breakdown exists. Date-clustered coverage has sd 0.24
  (reviewer). The assistant's own read of this block was stopped by a secret-scan hook, probably
  a false positive on long floats.
- **Sector mix** (*measured*; code mapping per `news_feeds.py:94-113`, reviewer): 208 symbols;
  ICB 8600 real estate 44, 8700 financial services 15 (mostly securities), 8300 banking 14, 8500
  insurance 3. Banking + financial services + insurance = 32 (about 15%); real estate = 44
  (about 21%).
- **Fibonacci script**: two readers found no look-ahead. Caveats (reviewer): σ at bar i includes
  bar i's close while a pivot is confirmed on the intrabar extreme (small); a level pierced on
  the confirm bar counts as unreached; the liquidity and history filters select on full history.
  A power limit (assistant): the hold/break barrier, one typical move, is wider than the gap
  between neighbouring levels at small scales, so the study cannot see narrow reactions. That
  lowers power; it does not bias the comparison.

### Revised recommendations

1. **Model-written text is not needed in v1.** Drop Round 2, the reasoning bullets (use the
   existing fallback form), Key Tension, Synthesis and the proposed "where the readings pull
   apart" paragraph. Replace the last three with a rule-written coverage and contrast table:
   which sources are stock-specific, which market-only, where two readings differ in size.
   This proposes to supersede the "Where the readings pull apart (language-model text)" item in
   "Proposed design". The News agent's Round 1 call stays until the vote goes (step 3 below),
   because the vote needs its stance; after that no model call is left.
   - Residual value: an on-demand English gist of a headline or filing, marked as model text
     (Rule 5). Not wanted: the owner decided on 2026-10-09 to show original titles only.
   - Side effects (not measured): a run takes the data-fetch time instead of about 45 s; no model
     cost, so a nightly basket is cheap; announcement text no longer reaches a prompt.
   - Revisit if the owner cannot read the headlines, full text is ingested, or the owner prefers
     the model paragraph in a blind comparison of about 20 reports.
2. **The headline is independent parts, not one Setup label.** Quiet / Active / Event-driven /
   Stressed mixes three axes (volatility, calendar, market stress) and needs an arbitrary
   precedence. The parts:
   - *Volatility*: forecast σ as a percentile of the stock's own history (relative by
     construction, Rule 3). A number; add a category only if a test earns it.
   - *Catalysts*: a dated list (ex-dividend, filings, results date); "none known" is valid.
     Includes the mechanical ex-dividend drop that the band does not contain.
   - *Market backdrop*: in index-σ units, in the page header (identical for every ticker).

   "Setup" and "Stressed" are retired as names ("Setup" has a trading-entry meaning, "Stressed"
   can read as bearish: Rule 6; Rule 5 names a label for what it reads). **Test**: coverage is
   flat across own-σ quintiles, so an own-σ category cannot improve band reliability; coverage
   varies by year, which is market-wide. So test band coverage conditional on the market regime
   (index σ percentile at t): early/late split, date-clustered intervals, effect size and pass
   level fixed before running. For events: matched event versus non-event windows (same ticker,
   same σ bucket), z = |r5| / (√5 σ), same split and clustering. VCI `events()` returns
   at most 50 rows per call; a six-ticker probe on 2026-10-09 (see "Settled for step 1") found
   dated history from about 8 months to about 9 years, so the matched test can run on history
   for a subset only, and "events only forward" in "Proposed design" is too pessimistic but not
   wrong. Any hit-rate shown stays measured and labelled (Rule 4).
3. **Revised order** (each its own `/opsx:propose`; owner to confirm):
   1. Remove Round 2, Key Tension and Synthesis; Technical and Macro bullets use the fallback
      form. No rule wording changes (none of the six rules names Round 2); the `debate-engine`,
      `debate-synthesiser` and `debate-panel-ui` specs, the panel, export, outcome log and
      `score_debates.py` still change. Agreement stays on screen, computed from Round 1 stances.
   2. VCI company news and events (old step 3), split in two: P2a, the data layer, fetches and
      stores them and starts snapshot logging now, without feeding the News agent; P2b, the
      readings, waits for step 1. (The RSS feeds
      hold about four days and cannot be backfilled; VCI `news()` returns 50 items covering 4 to
      16 months, so log those too.)
   3. Drop the vote and Agreement; rule edits in `CLAUDE.md` and `openspec/config.yaml` in
      lockstep. Needs owner sign-off, which is now off the critical path.
   4. Parts backtests (market regime against band coverage; matched event test), then
      fundamentals v1 (old step 4).
   5. Fibonacci reference levels, last or as a separate change.
   6. Nightly basket: optional, cheap without a model.

   The steps split into the changes named in "Proposal breakdown and parallel start".

   *Why the order changed.* The measured gap for SAB is source breadth (0 of 130 RSS items name
   SAB; one VCI source supplies dated items), not the vote. The first order put the largest
   blast radius (the code list under "Dashboard", 11 `SynthesisResult` callers, an 864-line panel
   test, two rule files) ahead of the data fix and made rule sign-off a dependency. *Cost of the
   new order*: until step 3 the vote and Agreement stay visible, and a Majority can still rest on
   a News neutral drawn from market-only headlines (less often once VCI items arrive).
   *Strongest argument against the redesign overall* (reviewer): it rewrites a lot for an
   unmeasured gain, and a quiet mid-cap still reads "nothing found", now honestly.

### Other items raised

- **Rule 4**: the band's "about 2 in 3" is a pooled figure; by test year coverage ran 0.61–0.74.
  A disclosure belongs wherever the band is the headline. Which on-screen sentence carries it
  (the per-ticker measured hit-rate or the nominal-coverage footer) was not checked.
- **Unused indicators**: `senkou_span_a/b` and `chikou_signal` (reviewer), as well as `obv`,
  `atr` and `bb_*`, sit in `features`. The "only three indicators" complaint is partly
  self-inflicted. The evidence says no direction edge, so any of them would be a reading, not a
  vote.
- **Macro's fixed thresholds** (`macro.py:343` 1 point, `:355` 0.5%, and
  `FOREIGN_FLOW_RATIO_THRESHOLD`) disappear with the vote. The market-backdrop reading in
  index-σ units replaces them, which also settles the Rule 3 tension noted above.

### Where the reviewer and the assistant differ

- The reviewer says news and event snapshots "cannot be backfilled". The assistant first said
  that holds for the RSS feeds only; the 2026-10-09 probe corrected it: VCI `news()` and
  `events()` are each capped at 50 items per call, so they backfill only 4 to 16 months of news
  and a ticker-dependent span of events.
- The reviewer assumed the owner reads Vietnamese. Not known.

## Settled for step 1 (2026-10-09)

What a `/opsx:propose` for step 1 ("remove Round 2 and the model-written text") can start from.
*Owner* marks an owner answer; the rest is the assistant's reading of the repo on 2026-10-09.

### Owner answers

- **Scope: pure removal** (*owner*). Remove Round 2, Key Tension and Synthesis. Technical and
  Macro reasoning become the values list that already exists as their fallback. The Debate matrix
  goes from 6 cards to 3. No new UI; the rule-written coverage table arrives with the VCI
  readings (P2b).
- **Interim state accepted** (*owner*): the vote and Agreement stay on screen, computed from
  Round 1 stances, until step 3. No domain rule changes in step 1.
- **Headline: independent parts** (*owner*): a volatility percentile as a number, a dated
  catalysts list, a market backdrop in the page header. Retires the Setup and Stressed names.
  Applies from step 4; nothing in step 1.
- **Vietnamese titles: show the original title** (*owner*), whether it is Vietnamese or English.
  No translation and no model gist anywhere. The News agent reads Vietnamese RSS headlines and
  the proposed VCI filings are Vietnamese titles; today a model reads them and writes English
  bullets, and this decision is about how they show once no model reads them for a stance. It
  does not affect step 1 (News's Round 1 call is unchanged there); after P3 no model call
  remains. The earlier default, an optional on-demand English gist, is withdrawn.

### Prerequisites

- **Backup taken**: `~/backups/stock-foresight/debate_log-2026-10-09.db` (sqlite `.backup` of
  `backend/data/debate_log.db`: 9 rows, `as_of` 2026-10-05 … 2026-10-08, integrity ok). Outside
  the repo, so `git clean -x` cannot remove it. The log is irreplaceable (`KNOWN_ISSUES.md`).
- No active OpenSpec changes (`openspec list`).
- A read-only `vnstock` probe ran with the guard installed: the six home config files kept their
  2026-08-11 timestamps and no `AGENTS.md` appeared. Those six files are still on disk, which
  `KNOWN_ISSUES.md` records as the owner's call. The assistant did not open them.
- The 9 log rows become scoreable around 2026-10-12 with the current `score_debates.py`. Step 1
  need not wait if the log columns stay as below.

### Measured 2026-10-09 (read-only vendor probe, SAB VPB VCB VHM SSI HPG)

- VCI `events()` returns at most 50 rows per call (42 for VHM). Dated ex-right history runs from
  about 8 months (SSI) to about 9 years (SAB, VCB, VHM). Cash-dividend ex-dates number 1 to 18
  per ticker. Director-deal rows crowd the cap for some tickers (SSI: 35 of 50). Columns include
  `value_per_share`, `exercise_ratio`, `exright_date`, `record_date`, `payout_date`.
- VCI `news()` returns 50 items covering 4 months (VPB, SSI) to 16 months (SAB). Columns include
  `ticker`, `news_title`, `news_source`, `news_full_content`, `public_date`.
- So history is partial for both: a complete record needs forward logging (or pagination, not
  tried). Only a subset of tickers can support a matched event test on history.

### Step 1 inventory

Specs (requirement headers in `openspec/specs/<capability>/spec.md`; counts are matching lines):
- `debate-engine` (33): REMOVE "runs a response round (Round 2) in parallel"; MODIFY the
  `DebateResult` shape, the degraded-agent definition (no `round2_failed`) and the endpoint.
- `debate-synthesiser` (40): REMOVE the key-tension requirement, "prompt instructs agents to
  maintain positions", "makes no LLM call when it abstains" (it never calls) and "prompts and
  fallback text describe the vote neutrally"; MODIFY the two vote requirements to read Round 1.
  KEEP "Verdict display labels are non-transactional (Rule 6)": the `tasks` rule in
  `openspec/config.yaml` points at that table.
- `debate-panel-ui` (37): REMOVE "Key tension is shown in the Verdict panel only"; MODIFY the
  result state, the Debate matrix (three agents, one round), the language-model marking and
  the unavailable-agents requirements.
- `debate-report-export` (18): MODIFY the structure (no Round 2, Key Tension or Synthesis) and
  "Report marks language-model-written sections (Rule 5)". After step 1 only News bullets are
  model text, so the fixed line "Reasoning, key tension and synthesis are written by a language
  model" must change to keep provenance accurate.
- `debate-runtime` (26): REMOVE "Independent synthesiser calls run concurrently" and "Unusable
  synthesis text is reported as unavailable"; MODIFY the time budget, the progress stages
  (`STAGES` in `runner.py:51`), fencing and withheld wording (News prompt and bullets only).
- Small text changes: `technical-agent` (bullets become the values list; its text still says
  "the same row used by the existing insight endpoint … `backend/app/api/insight.py`", stale
  since `/insight` is retired), `debate-outcome-log` (4), `macro-agent` (2), `news-agent` (1),
  `dashboard-ui` (4), `volatility-range` (1).

Code (matching lines). Backend: `synthesiser.py` 37, `engine.py` 30, `export.py` 13, `runner.py`
6, `api/debate.py` 6, `scripts/measure_debate_runtime.py` 6, `outcome_log.py` 1,
`prompt_safety.py` 1. Backend tests: `test_debate_agents.py` 83, `test_debate_export_api.py` 26,
`test_prompt_safety.py` 15, `test_debate_runner.py` 8, `test_debate_outcome_log.py` 6,
`test_debate_log_api.py` 3, `test_score_debates.py` 2. Frontend: `VerdictPanel.test.jsx` 26,
`VerdictParts.jsx` 13, `DebateMatrix.test.jsx` 11, `debateFixtures.js` 7, `debateText.js` 5 (and
its test 5), `useDebateProgress` and its test 5, `DebateMatrix.jsx` 4, `api/tickers.js` 4,
`PanelStates.jsx` 2, plus several one-line test files.

Engine facts the design starts from: Round 2 runs only when at least two agents are live
(`engine.py:165`); with fewer, `round2` is a copy of `round1`. `agents_degraded` is read from
`round2` (`engine.py:200`). `_safe_run` applies `withhold_advice` to every position's bullets
(`engine.py:225`) and still serves the News bullets. The log writes `r1_*` and `r2_*` in one
loop (`outcome_log.py:127`).

### Constraints for the proposal's design

- **Domain rules**: all six honoured unchanged; none of the rule texts names Round 2. Rule 4:
  Agreement keeps its label. Rule 5: the marking shrinks to what is still model text. Rule 6:
  the disclaimer stays wherever a verdict, Agreement, range or agent reasoning shows; verdict
  labels come from the `debate-synthesiser` table.
- **`openspec/config.yaml` context** (lines 6-10) says "two rounds" and "a verdict by
  deterministic vote over Round 2 stances". Edit it in the same change. It is project context,
  not a rule, and `CLAUDE.md` does not repeat it.
- **Log**: keep the `r2_*` columns and write NULL for new rows; `outcome_log.py` and
  `score_debates.py` must read old and new rows. Verdicts before and after step 1 come from
  different code (Round 2 versus Round 1 stances), so any pooled verdict statistic must split on
  `code_rev`. A new column would need a migration; avoid one.
- **Safety tests**: keep the fencing, injection and withheld-wording tests that cover the News
  headline path (`test_prompt_safety.py`); delete only those for the removed prompts.
- **Technical band line** (decided, item 1 under "Decided 2026-10-09"): the deterministic
  Technical bullets carry no "Typical 5-session move" line. The `technical-agent` range
  requirement is rewritten: the range-service part stays, the prompt wording goes. Rules 1 and 2
  are honoured unchanged (the band still shows as a percentage over 5 sessions, in the range
  block and the export Summary). The daily σ figure leaves the reports until P7.
- **Cleanups in scope** (decided, item 2): delete the dead `_get_sector_closes` and fix the stale
  "insight endpoint" text in the `technical-agent` spec. The stale "Current focus" list in
  `openspec/config.yaml` waits for P3's config edit.
- **Open design choices** (the proposal's, not the owner's): drop `round2` and the synthesis
  text fields from the `POST /debate` response or keep them empty for compatibility (local
  app, one deploy, so dropping is simpler); whether `STAGES` keeps a single `round1` stage; the
  report format for new files while old files keep the old one.
- **Not in step 1**: VCI news and events, fundamentals, Fibonacci, dropping the vote and
  Agreement, any rule edit, the parts headline, a coverage table, the by-year coverage
  disclosure (a second reliability figure, so Rule 4 sign-off, with step 3).

### Backlog dispositions

- `KNOWN_ISSUES.md` #1 (RSS text in prompts), #2 (`claude_cli` subprocess), #4 (data to a
  third-party model) and the unauthenticated debate endpoint: reduced by step 1 (one model call,
  News's Round 1, instead of 8), not closed. They close when step 3 leaves no model call;
  update the entries then.
- `KNOWN_ISSUES.md` #5 (Macro fixed thresholds): unchanged by step 1, closed by step 3. The
  debate-log hazard: backup taken, the standing caution stays.
- `DISCUSSION_calendar_staleness.md` (Fresh/Stale dot): not touched by step 1; its status after the
  Rail rebuild was not re-checked. Per-source "last item" dates in P2b are the same kind of
  signal, so decide them together.
- `DISCUSSION_prediction_outcome_tracking.md`: options 2 and 3 were done by `debate-outcome-log`;
  step 1 keeps them working. Option 4 and a nightly basket stay deferred.
- Archived open questions: prompt language (unchanged, English; revisit with the Vietnamese-titles
  question), board-settle time and the rolling foreign-flow window (deferred, Macro unchanged),
  `[ticker]` aliases (deferred to P2a, partly overtaken by VCI). `/insight` and the feature
  flag: `/insight` is retired per `ticker-prediction` and `VITE_DEBATE_PANEL_ENABLED` does not
  appear in `frontend/src` (env files not read), so this looks done; the proposal should confirm
  it and not re-open it.

### Decided 2026-10-09 (owner accepted the recommended defaults)

1. **Technical band line (P1)**: omitted from the deterministic Technical bullets. The range
   block and the export Summary keep stating the band and its coverage; `AgentPosition` keeps
   its range fields. Basis: code read ([export.py:175](backend/app/services/debate/export.py#L175),
   `RangeBlock.jsx`).
2. **Cleanups in P1**: delete the dead `_get_sector_closes` (`macro.py:174`); fix the stale
   "existing insight endpoint" text in the `technical-agent` spec (`backend/app/api/` has no
   `insight.py`).
3. **Vendor terms (P2a, P4)**: proceed for personal use only. Primary source: the installed
   metadata says `vnstock` 4.0.5 is "Custom: Personal, research, non-commercial; contact
   support@vnstocks.com for other use" and `vnai` is "proprietary". VCI's own terms for the
   endpoints behind the library were not found. Work, paid or shared use is outside this: ask
   whoever owns licensing first (not legal advice). Rate limits (about 20 requests a minute
   without a key, 60 with a free key) come from a web-search summary of third-party pages and are
   unverified. No API key before the sandboxed-`HOME` test: whether the guard covers key-gated
   `vnai` paths is unverified.
4. **`vnstock` pin (P2a)**: pin `vnstock==4.0.5` and `vnai==2.5.5` exactly in
   `backend/requirements.txt` (`vnai` is transitive and unpinned today, and is the component
   that wrote the injected files). A bump is deliberate and re-tested. Unknown whether 4.0.5 is
   current: `pip index` could not list versions in this environment.
5. **P2a does not feed the News agent** (reverses an earlier recommendation). The News window is
   7 days (`MAX_AGE`, `news_feeds.py:49`) and SAB's last VCI item is 2026-08-28, so it would
   change nothing for SAB. It would change News's stance and the vote while P1 edits the same
   code, confounding any before-and-after check of P1. Titles-only filings give weak-evidence
   stances (the title mix was not classified). P2a fetches, cleans, stores and snapshots; P2b
   adds the display. Its value until then is the snapshot clock and a ready data layer.
6. **Snapshot log location (P2a)**: a separate file (for example
   `backend/data/company_feed_log.db`), not `debate_log.db` (the `debate-outcome-log` spec
   stores no third-party headline text) and not `app.db` (disposable). Add it to the backup note
   in `KNOWN_ISSUES.md`: a second irreplaceable file with no automatic backup.
7. **S1 market-regime source**: reuse the vendor index path in `macro.py`
   (`_get_vnindex_closes` reads `ohlcv` for "VNINDEX", none is stored, then falls back to the
   vendor and keeps only the last 27 closes). A proxy from the 208 stocks is circular with the
   coverage being tested. Unverified: the vendor's history depth; if it is under about six
   years, revisit.
8. **S1 pass level**: at least a 5-point coverage gap between the calmest and most volatile
   market-regime third, in both the early and late halves, with a date-clustered interval that
   excludes zero. This is a judgement (about the size of the by-year gaps of -6.7 to +6.1
   points, reviewer-reported and not verified). S1's design may revise it after seeing how few
   independent market episodes there are; the level is fixed before running.

### Not settled (later steps; none blocks step 1)

- **By-year coverage disclosure**: where it goes and in what words. It is a second reliability
  figure, so it needs Rule 4 sign-off (P3).
- **Percentile window**: `read_recent_closes` keeps at most 311 closes (`HISTORY_ROWS`,
  `volatility.py:193`), about 250 forecast values, roughly one year.
- **Fundamentals scope**: 32 of 208 symbols are banking, financial services or insurance and 44
  are real estate.

## Proposal breakdown and parallel start (2026-10-09)

The revised order splits into the changes below (each its own `/opsx:propose`; names are
suggestions). A proposal only writes planning files under `openspec/changes/<name>/`, so several
can be open at once. What must be sequenced is apply and archive when two changes edit the same
spec requirement or code file.

| # | Change | What | Depends on | Status |
|---|---|---|---|---|
| P1 | `retire-debate-round-two-and-model-prose` | step 1, pure removal ("Settled for step 1") | none | settled; start now |
| P2a | `add-company-feed-news-and-events` | VCI fetcher, title cleaning, storage, snapshot log in a separate file, `vnstock` and `vnai` pin; no News-agent feed | none | start now; decisions 3 to 6 apply |
| S1 | `evaluate-band-coverage-by-market-regime` | read-only study with a kill criterion | none | start now; decisions 7 and 8 apply |
| S2 | `evaluate-event-windows` | matched event versus non-event windows | P2a event data | after P2a |
| P2b | `show-source-readings-and-coverage` | readings cards, rule-written coverage table | P1 applied, P2a | after P1 |
| P3 | `retire-vote-and-agreement` | drop the vote and Agreement; rule edits in `CLAUDE.md` and `config.yaml` | P1, P2b; owner sign-off | after P2b |
| P4 | `add-fundamentals-readings` | latest-quarter facts, TTM P/E | P2b; vendor and key decisions | after P2b |
| P5 | `add-fibonacci-reference-levels` | chart toggle | the owner's Rule 6 ruling (first open question) | independent of the rest; blocked on the ruling |
| P7 | `add-headline-parts` | volatility percentile, catalysts list, market-backdrop header | S1, S2, P2b | later |
| P6 | `add-nightly-ticker-basket` | basket of about 25 tickers | P3 (no model cost) | optional, later |

**What to start with.** P1, P2a and S1, and no more in flight than the owner can review. P1
edits the engine, synthesiser, export and panel; P2a adds a new module, its log file and the
pin; S1 adds a script. P2b, P3, P4 and P7 edit the same specs and panel files as P1, so they
wait for it to be applied.

**Design notes for the proposals**

- P2a does not feed the News agent (decision 5), so it ships no visible change until P2b; its
  value is the snapshot clock and a ready data layer. The snapshot log lives in its own file
  (decision 6): not in `app.db`, which `KNOWN_ISSUES.md` treats as disposable, and not in
  `debate_log.db`, whose spec excludes third-party headline text.
- Every task uses the project's `vnstock` skill and none hand-rolls calls (the `tasks` rule in
  `openspec/config.yaml`); every new importer calls `app.vnstock_guard.install()` first.
- S1 and S2 follow the repo's precedent for study scripts as capabilities
  (`cross-sectional-momentum-evaluation`, and the script requirement in `volatility-range`): a
  read-only script, its own spec requirement, and the kill criterion and pass level stated before
  running.

**Before starting.** Commit this note, the Fibonacci script and its tests (untracked at the last
check, 2026-10-09), so branches and worktrees contain them and P1's proposal can read this note.
One branch per change. Archive P1 before P2b is applied.

## Open questions for the owner or the next session

- Rule 6: may extensions appear as "reference levels" with % and share-of-typical-move
  distances? Is any "target"/"stop" language acceptable (recommended: no)?
- Rule 4 (and Rule 6, Rule 5, Rule 1 wording): sign-off that Agreement is retired and the vote
  dropped (P3); the final names for the headline parts (the Setup and Stressed names are
  retired).
- What counts as "separates"? For S1 the default pass level is decided (item 8 under "Decided
  2026-10-09"); for the event test (S2) and the headline parts (P7) it is fixed in their designs.
- Fundamentals scope for v1: non-financial only, or banks too?
- Is `Company.ratio_summary()` (and any private `limit` workaround) within the vendor's terms?
  Partly answered by decision 3 (personal use fits the library licence); VCI's own terms were
  not found. Decide in P4.
- Rail: add a chip for the headline parts after S1, or keep the Rail free of marks by design?
- Does Macro stay as a context block, or gain stock-specific signals (sector index, breadth,
  liquidity trend, rates)? Should its fixed thresholds become volatility-relative?
- Another hold/break definition for the Fibonacci study (wick rejection, zones)?
- Source "agents" or readings "cards": do News, Macro, Technical, Fundamentals survive as named
  agents?
- From the second opinion (2026-10-09). Answered: removing Round 2 ahead of the rule sign-off is
  accepted; the headline becomes independent parts; Vietnamese titles show as the original title,
  no gist; vendor terms, the pin and the other defaults are decided (see "Decided 2026-10-09");
  VCI `events()` history is partial (probe in "Settled for step 1"). Still open: where the
  by-year coverage disclosure goes and in what words (needs Rule 4 sign-off).

## Not verified

- The layout of the running dashboard (components were read, not seen).
- Whether `obv`/volume history is clean enough for any volume-based reading.
- The headline parts have no thresholds yet; S1 and S2 are plans, not results.
- The vendor index endpoint's history depth (S1 needs several years).
- Whether `vnstock` 4.0.5 is the latest release (`pip index` could not list versions here).
- VCI's own terms for the endpoints behind the library (not found).
- `vnstock` behaviour on tickers other than SAB and VPB, bank and real-estate field sets, the
  API-key tier path, and free-tier limits after an upgrade.
- The technical-vote hit-rate on current data (figures above are from other docs).
- Fibonacci literature on effectiveness (not searched).
- The price limit (about ±7% a day on HOSE) effect on swing legs.
- The "about 11 levels between 42 and 46" density figure.
- How `openspec` handles two active changes that edit the same requirement (untested; run
  `openspec validate` before the first archive).

## Reproducing

- Fibonacci study: `python backend/scripts/evaluate_fibonacci_levels.py [--tickers N]`
  (about 50 s for all 208; tests: `pytest backend/tests/test_evaluate_fibonacci_levels.py`; do
  not run the whole suite for this, it touches the real database).
- `vnstock` probes: run with the repo's `backend/.venv/bin/python -I` and put `backend/` on
  `sys.path` by hand (`-I` ignores `PYTHONPATH`); call `from app.vnstock_guard import install;
  install()` before any `vnstock` import; then `from vnstock.api.company import Company` and
  `from vnstock.api.financial import Finance`. Expect promo and community-tier notices on stdout.
  - `Company(source="vci", symbol="SAB").news()`, `.events()`, `.overview()`, `.ratio_summary()`;
    `Finance(source="vci", symbol="SAB").income_statement(period="quarter")`; the net-profit row is
    `attributable_to_parent_company`.
  - The same with `source="kbs"` for the label comparison (KBS frames carry both `2025-Q4` and
    `2025-Q4_1`, and the ratio frame's column order differs from the income statement's).
- RSS check: fetch the three URLs in `news_feeds.FEEDS` with the same User-Agent and count
  `SAB` / `Sabeco` in titles and descriptions. Expected 2026-10-08: 60 / 50 / 20 items, 0 hits;
  counts drift hour to hour.
- Debate log: `sqlite3 -readonly backend/data/debate_log.db "select count(*), min(as_of),
  max(as_of) from debate_log"`. Expected: `9|2026-10-05|2026-10-08` today.

## Verification notes (2026-10-08, three fresh agents)

- **Cold read**: all ten comprehension questions were answerable from the doc alone. It flagged
  mixed "decided" vs "proposed" statements, jargon, a Setup test that would correlate with the
  range by construction, Rules 1/5/6 and `config.yaml` wording missing from the impact table,
  and a few overstatements. These are fixed above (Decisions, Glossary, backtest caution, Rules
  impact, softened Summary).
- **Fact check**: no false code claim. Corrected: the foreign-flow vote window, "majority of
  three signs" (plurality with ties neutral), base hold rate, sign-flip wording, "abstentions",
  Rule 1/5/6 and config rows, the display-label gap (now resolved), the "closes only" wording
  and the example scales. Also found: 9 log rows are 4 distinct ticker-days.
- **Reproduction**: all `vnstock` and RSS probes reproduced in spirit (counts differ by 1–2).
  Added: the `Finance.ratio` root cause, the `ratio_summary()` route, the KBS label resolution,
  the computed P/E and unit pitfalls.
- **Not fixed**: vendor terms for `ratio_summary()`; the API-key tier path; whether the Setup
  test will pass; items under "Not verified".
