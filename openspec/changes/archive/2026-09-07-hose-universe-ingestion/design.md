## Context

The database holds 15 hand-picked large-cap tickers, all still listed. Every
one was chosen for M3 training, so `TRAINING_TICKERS`, the API catalog, and
"everything the system knows about" are currently the same list. This change
separates those three things and grows the third to the full HOSE universe.

Constraints inherited from the existing system, all verified this session:

- **`vnstock.ui.Market` is the required fetch surface.** The
  `ticker-data-ingestion` spec mandates exactly one
  `mkt.equity(ticker).ohlcv(start="2000-01-01", end=today, count=5000,
  source="vci")` call per load. `Vnstock().stock(...)` was deprecated
  2025-08-31; `Market` is unaffected and stays.
- **Community tier caps history at roughly 8 years**, already recorded in
  that spec. Ingesting more symbols does not extend the window backwards.
- **`load_ticker` recomputes features from each ticker's earliest row on
  every call**, required for `obv` correctness (`DATA_DICTIONARY.md`,
  design Decision 5).
- **No scheduler exists anywhere in `backend/app`**, confirmed during the
  `ticker-manual-refresh` work and again in
  `DISCUSSION_prediction_outcome_tracking.md`.

Spike results that shaped this design, run against the live API:

| Question | Answer |
| --- | --- |
| HOSE ordinary stocks | **405** (`exchange = HSX`, `type = STOCK`) |
| Delisted ordinary stocks | **229** (the 1,637 `DELISTED` rows include CW/bond/other types) |
| Is delisted history retrievable? | **Yes** — `VSP` 1,634 rows to 2022-07-28, `VKP` 2,001 rows, `VMI` 1,636 rows |
| Is history short for some? | Yes — `XDC` returned only 68 rows |
| Industry classification | `icb_code2` present on listing rows |
| Are prices adjusted? | **Yes** — 25 price-limit violations in ~30,000 rows (0.08%), no corporate-action jumps |

## Goals / Non-Goals

**Goals:**
- A universe that can be reconstructed as of any past date without
  survivorship bias.
- Data quality established at ingestion, not discovered later by a model
  producing strange numbers.
- Batch ingestion of ~630 symbols that survives rate limits and
  interruption.
- Decouple the catalog from `TRAINING_TICKERS` without creating a second
  hand-maintained list.

**Non-Goals:**
- Any model change. The volatility pivot, interval output, holdings, and
  cross-sectional work are open and undecided (`DISCUSSION_model_direction.md`).
- Retraining on the larger universe. This change ingests; it does not
  retrain.
- HNX and UPCOM ingestion. The schema is built to accommodate them; only
  HOSE plus delisted-formerly-HOSE symbols are ingested here.
- Introducing a scheduler.

## Decisions

### Decision 1: Universe table separate from `tickers`

A new universe table holds symbol, exchange, `icb_code2`, listing status,
first/last observed session, stale-close fraction, and filter flags.
`tickers` keeps its existing load-state role unchanged.

*Alternative considered*: extending `tickers` with universe columns. Rejected
because `tickers` currently means "something we have loaded" — a row exists
only after a successful load. The universe must contain symbols that have
never been loaded and symbols that failed ingestion, so conflating them would
force `tickers` rows to exist for things that were never fetched, breaking
the existing "no row means never loaded" semantics that `ticker-catalog`
depends on.

### Decision 2: Ingest delisted symbols; do not attempt to reconstruct historical index membership

Delisted symbols are ingested and marked. Point-in-time universe
reconstruction is done from **observed session ranges** — a symbol is in the
universe as of date `D` if its first observed session is on or before `D` —
not from any historical index-membership record.

*Alternative considered*: reconstructing true historical HOSE membership.
Rejected because the listing API returns current state only; delisted rows
carry no historical exchange field. Observed-range reconstruction is
approximate at the edges (a symbol that moved exchanges mid-life is treated
as one continuous series) but it is derived from data actually in hand rather
than from assumption, and it removes survivorship bias, which is the
first-order problem.

### Decision 3: Two-tier price-limit gate

**These thresholds are new — they are not covered by domain rules 1-6, which
this change does not touch.** The exchange limits themselves are market
facts, not project choices.

- **Hard gate (exclusion)**: `|log return|` beyond the widest VN exchange
  limit, UPCOM's ±15%, plus tolerance. Rows past this are excluded from
  modelling inputs.
- **Soft flag (review)**: `|log return|` beyond the limit of the exchange the
  symbol currently trades on (HOSE ±7%, HNX ±10%, UPCOM ±15%). Recorded but
  not excluding.

Rationale, from the measured data. The hard gate catches `VHM`'s
2018-08-14 step (`60.30 -> 30.23`, a −0.69 log return, a −50% price change),
the one gate-triggering row observed, while producing **zero false
positives** on the 24 legitimate pre-migration violations from `ACB`
(−0.10), `VIB` (−0.12), and `VND` (−0.10 log return) — all of which are real
moves under their then-exchange's wider limit. A single universal ±7% gate
would have flagged all 24 as corrupt.

**What VHM's row actually is, confirmed after implementation**: not corrupt
data but a **missed 2:1 split adjustment**. The close halves and *stays*
halved, so the step is spurious while every price on either side of it is
correct. This distinction matters for what needs neutralising — see Decision
9.

*Alternative considered*: resolving the exact historical exchange per row and
applying its limit precisely. That is what the `ohlcv-quality-gate` spec
describes as the ideal. It is not achievable from the listing API today (see
Decision 2), so the soft tier records current-exchange evaluation and marks
it as the unverified fallback the `ticker-universe` spec explicitly allows.
The hard tier is what actually gates data, and it needs no dated membership
to be correct.

*Trade-off accepted*: a genuinely corrupt HOSE row with a change between 7%
and 15% passes the hard gate. Given adjusted prices and 0.08% observed
incidence, that is a smaller risk than discarding hundreds of legitimate
pre-migration sessions.

### Decision 4: Quality flags in a sidecar table, not columns on `ohlcv`

*Alternative considered*: adding flag columns to `ohlcv`. Rejected because
`ohlcv` is upserted wholesale on every reload; flags would need recomputing
and rewriting on every load of every row. A sidecar keyed by
`(ticker, date)` holding only flagged rows is far smaller — an expected few
hundred rows across the universe — and leaves the hot ingestion path
untouched.

### Decision 5: Liquidity filter enforced at the universe boundary, threshold retained

The stale-close fraction (sessions where `close == prev close`) is computed
per symbol and stored. Symbols above threshold are flagged and excluded from
the **default modelling universe**, but their data is retained.

**Threshold is new, not covered by domain rules 1-6.** It reuses
`STALE_PRICE_WARN_THRESHOLD = 0.15` from
`backend/scripts/screen_ticker_volatility.py`, promoted from a printed
warning to an enforced filter. The measured value is stored per symbol so
the threshold can be re-tuned later without re-ingesting.

*Alternative considered*: refusing to ingest illiquid symbols at all.
Rejected because the threshold is a judgement call carried over from a
screening script written for 9 candidates, not validated against 405. Storing
the measurement and filtering on read makes it revisable; discarding the data
does not.

### Decision 6: Batch runner is an operator-invoked CLI script, not a scheduler

A script under `backend/scripts/`, matching where
`screen_ticker_volatility.py` and `verify_feature_engineering.py` actually
live. Resumability comes from the universe table's own per-symbol ingestion
state, so a re-run naturally skips completed symbols with no separate
checkpoint file.

*Alternative considered*: introducing APScheduler or cron. Rejected as scope
creep — this codebase has never had a scheduled job, and
`DISCUSSION_prediction_outcome_tracking.md` already identifies "when does
this run" as a decision deserving its own change rather than being smuggled
in here.

### Decision 7 was wrong about what the batch costs — measured 2026-09-07

The prediction below was that per-ticker feature recomputation becomes the
dominant cost at scale. The first dry run (14 symbols, task 6.7) says
otherwise, by an order of magnitude:

| | measured |
| --- | --- |
| Feature recomputation | **0.2 s** per symbol (~2,000 rows) |
| Fetch, unthrottled | 0.8-3.9 s per symbol |
| vnstock guest-tier limit | **20 requests/minute**, ~2 requests per symbol |

The run stopped for a rate limit after its tenth symbol. So the binding
constraint is the throttle — roughly 10 symbols a minute, putting the full
610-symbol run at **~1 hour**, of which recomputation is about two minutes
in total. The decision itself still stands (bound recomputation to symbols
the run touched, do not build incremental `obv`), but it stands for
tidiness rather than because recomputation was ever going to be expensive.

Recorded because the reverse error would matter: anyone optimising this
later should optimise request count, not computation.

### Decision 7: Feature recomputation stays full-per-ticker, but the batch only touches changed tickers

`obv` is a cumulative sum from each ticker's earliest row, so per-ticker full
recomputation is retained for correctness. The change is that a batch run
recomputes only the symbols it actually fetched or updated, rather than the
whole universe.

*Alternative considered*: incremental `obv` with a stored running total.
Rejected as premature — it optimises a column that
`DISCUSSION_model_direction.md` Finding 2 shows is actively harmful as a
model feature (96 splits, a pure calendar-time proxy) and which a future
model change may well delete outright. Adding persistence complexity to a
column that may not survive is the wrong order of work.

### Decision 8: Catalog derives from the universe, with training membership as a flag

`GET /tickers` reads the universe table and marks which entries are in
`TRAINING_TICKERS`. The existing prohibition on a second hand-edited list is
preserved — there is still exactly one source for each fact, they are just
now two different facts.

### Decision 9: A hard flag nulls indicator columns for the longest lookback after it

Confirmed during implementation of task group 3, decided 2026-08-28.
The gate neutralises a flagged session's own return, and `compute_target`
correctly nulls the `TARGET_HORIZON` rows whose lookahead spans the step
(`target(d)` itself spans `close[d]` to `close[d+5]`, both on the far side,
and stays valid). That part is exact.

What is *not* handled: a missed split is a persistent level shift, so every
**level-based indicator** whose lookback spans the step blends pre- and
post-split prices — `bb_middle` (20 sessions), `kijun_sen` and `macd` (26),
`senkou_span_b` (78). `near_gap` does not catch this; it flags calendar
gaps, not price discontinuities.

VHM does not expose the problem because its split fell 10 sessions after
listing, inside the warm-up band `near_gap` already excludes (its first
`near_gap = 0` row is 2018-11-16). A **mid-life** split on a long-listed
ticker has no such protection, and Vietnamese companies pay stock dividends
frequently, so the batch ingest is expected to produce such cases.

Options, neither chosen:

- **(a) Widen the flag's blast radius to features.** Null indicator columns
  for the longest indicator lookback after a flagged session, mirroring what
  `near_gap` already does for warm-up. Cheap, consistent with the module's
  existing philosophy, and loses ~78 sessions per event.
- **(b) Detect and repair.** A missed split is identifiable (persistent
  level step at a near-rational ratio) and correctable by rescaling
  pre-split prices. Converts data loss into data repair and keeps the
  history usable, but means writing corrected prices into `ohlcv` — a
  materially larger commitment, and one that makes stored prices no longer
  a faithful record of what the source returned.

**This needs a decision before task group 7 runs the full batch**, because
it changes what ingestion must record. Option (a) needs only a flag; option
(b) needs the original values retained alongside the corrected ones.

*Where the blackout has to be enforced, learned while implementing it
(tasks 5.4/5.8/5.9).* Nulling the indicator columns is not self-enforcing.
Every consumer gated on `near_gap`, which the blackout deliberately does
not set, so all-null rows passed straight through — into training as
all-NaN vectors carrying valid labels, and out of both the prediction and
insight endpoints as numbers computed from nothing. There were **three**
such consumers, not the two the review found: `GET
/tickers/{ticker}/insight` was missed, and it is the worst of them, since
Advice is Rule 3 directional wording. All three now test the indicator
columns themselves rather than any flag, so the check cannot drift out of
sync with what is actually null — and it covers every cause of a null
indicator, including the short-series case in `docs/KNOWN_ISSUES.md`, not
just this blackout. The dashboard needed a fifth prediction state to say so
without a blank card.

### Decision 10 (open): the hard gate is wrong for low-priced stocks

Found by the first dry run, which ingested three delisted penny stocks.
`VKP` drew **43 hard flags** across 2,001 sessions and `VMI` three, against
one flag in the entire original 15. At 78 blacked-out sessions per flag,
`VKP`'s whole history is now void — its features are all null, and (via
task 5.4's gating) it is correctly excluded from training and serving
rather than poisoning them. So nothing is *wrong*, but nothing is usable
either, and the same will happen to every illiquid name in the 610 still
to ingest.

Whether those flags are false positives is not yet established. A stock at
0.2 (200 VND) moving to 0.1 is a legal 100-VND tick step at the exchange's
minimum tick, yet reads as −50% — the tick-rounding effect
`PRICE_LIMIT_TOLERANCE` already acknowledges, at a magnitude 0.002 cannot
absorb. It is equally possible that a delisted symbol trading off-exchange
simply is not subject to a HOSE-style limit at all.

**Resolved 2026-09-07: option (a), price-aware limit** — but from each
symbol's *own observed* price grid, not a tick table. A tick table would
have predicted 0.01 for `VKP`'s price band and changed nothing; its actual
grid is 0.1, estimated as a low percentile of its non-zero close-to-close
steps (with a minimum-observations guard, so a two-row series cannot
"establish" a grid from the very anomaly being tested). The limit becomes
`max(limit, one grid step)`. Measured effect: `VKP` 43 -> 33 hard flags,
`VMI` 3 -> 1, `VSP` 2 -> 1, and the known-answer 15 unchanged (`VHM` 1
hard, `ACB`/`VIB`/`VND` 24 soft and never hard). The 33 that remain are
two-grid-step jumps, which are anomalous at any price level.

Three responses considered:

- **(a) Price-aware limit.** Compare against
  `max(limit x reference, tick_size)`, with VN tick sizes (10/50/100 VND by
  price band). Principled, and testable against the known-answer 15, which
  are all high-priced and so should be unaffected.
- **(b) Let the liquidity filter carry it.** `VKP` measures a 0.977
  stale-close fraction and already fails the liquidity filter by a mile, so
  it would leave the modelling universe anyway. Cheapest, but leaves the
  flag counts meaningless for task 9.1's classification.
- **(c) Nothing.** Accept that penny stocks self-void. Honest, but it makes
  "hard flag" mean two different things depending on price level.

Interacts with the open question below on recursive indicators: both are
about how far one flagged session is allowed to reach.

### Decision 11 (open): the blackout does not reach the recursive indicators

Decision 9 nulls indicator columns for 78 sessions after a hard flag, on
the reasoning that the longest lookback is Senkou Span B's 78. That is
correct for the rolling-window indicators, and verified: `senkou_span_b`'s
last contaminated row is offset +76, inside a blackout covering +0..+77.

It is not correct for the recursive ones. `rsi` and `atr` use Wilder
smoothing, `macd_*` an EWM from the series start, and `obv` a cumulative
sum — none is window-bounded, so a level shift propagates past any fixed
span. Measured against a split-repaired reference series on `VHM`'s real
data, at the **first row past the blackout** (2018-12-03, `near_gap = 0`,
target non-null, so it enters training and can be served):

| column | 2018-12-03 | 2018-12-17 | 2019-09-25 |
| --- | --- | --- | --- |
| `macd_signal` | **54.5%** | 9.9% | 0.0% |
| `macd_line` | 19.5% | 7.8% | 0.0% |
| `macd_histogram` | 19.2% | 23.2% | 0.0% |
| `obv` | 20.4% | 19.9% | **12.0%** |
| `rsi` | 2.4% | 1.2% | 0.0% |
| `bb_middle`, `senkou_span_b` | 0.0% | 0.0% | 0.0% |

A synthetic mid-series 2:1 step puts `macd_histogram` at 3,578% error on
the first clear row. Decision 9's own text ("`kijun_sen` and `macd` (26)")
is simply wrong that MACD is 26-bounded, and the `ohlcv-quality-gate`
scenario "Sessions beyond the lookback are unaffected" does not hold as
written. Only `obv`'s unboundedness was documented.

**Resolved 2026-09-07: option (a), segment the series at a hard flag.**
The recursive indicators are recomputed independently on each side of a
flagged session; `target` and `near_gap` stay whole-series, since
`compute_target` already nulls exactly the rows whose lookahead spans the
step and `near_gap` means calendar gaps. Detect-and-repair stays deferred
for the reason Decision 9 gives — it would write corrected prices into
`ohlcv`. The two tests that claimed to cover this were comparing a flagged
run against an equally-contaminated baseline, so they passed while
`macd_signal` was 54% wrong; they now measure against the post-flag
segment computed alone.

Options considered:

- **(a) Segment the series at a hard flag.** Restart the recursive
  indicators after the flagged session as if it began a new series — which
  is what a persistent level shift makes it. Costs each indicator's seed
  period once per event, bounded and local, and makes the "beyond the
  lookback is unaffected" claim true.
- **(b) Detect and repair the split** (Decision 9's option b, deferred).
  Removes the cause rather than masking it, and is the only option that
  keeps the history continuous — but writes corrected prices into `ohlcv`.
- **(c) Extend the blackout to the end of the series.** Correct and
  useless: one flagged session in 2018 would void everything after it.

**Both of these need deciding before the full batch runs**, for the reason
Decision 9 already gives: they change what ingestion must record, and the
610-symbol run is what produces the mid-life cases at scale.

### Decision 12 (resolved): a zero close is absent data, not a level shift

Found by the first full ingest. **1,122 rows across 37 symbols have a close
of `0.0`**, and they arrive in long consecutive runs — `DBH` has 197 of
1,519 sessions, `AUM` 120 in a row. The zero-close fix (Decision 10's
sibling, task 5.12) correctly hard-flags them, since a price of zero is not
a price. But a hard flag carries two consequences, and only one of them
belongs here:

- Neutralising the session's return and nulling the targets that span it is
  right for every hard flag — an ±inf return would wreck a volatility
  window as thoroughly as a missed split.
- The 78-session blackout and the segmentation of the recursive indicators
  (Decisions 9 and 11) are corrections for a *change of price scale*. A
  zero close is not a change of scale; it is missing data. Applying them
  would shred `AUM`'s series into 120 one-row segments and void 78 sessions
  apiece.

**Resolved 2026-09-07**: non-priced rows are dropped from the modelled
series before indicators are computed, and only `price_limit`-reason flags
drive the blackout and segmentation (`level_shift_dates`). `ohlcv` keeps
every row the source returned, so the record stays faithful, and the run
becomes the calendar gap it actually is — which `compute_near_gap` already
excludes on its own terms, with no new mechanism. A single absent session
is correctly *not* a gap; a 30-session run is.

### Decision 13 (resolved 2026-09-11): 587 hard flags are bad prints, not missed splits

Decision 9's reopening trigger fired during ingestion. The flagged-row rate
measured **0.57%, about 7x** the 0.08% baseline over the original 15, and
the hard flags divide into three shapes rather than one:

| shape | count | what it is |
| --- | --- | --- |
| `invalid_close` | 1,122 | no price at all — handled by Decision 12 |
| `missed_split` | 706 | a persistent level step, like `VHM` 2018-08-14 |
| `bad_print` | 587 | a spike that reverts |

(Counts at 485 of 634 symbols ingested, taken mid-run;
`backend/scripts/report_ingest_outcomes.py` recomputes them and the final
run — 599 of 634 ingested — settled at 864 `missed_split` and 770
`bad_print`, in the same proportion.)

The 587 (later 770) bad prints were the open question. A reverting spike is
*one wrong price*, not a change of scale, so the two sides of it are the
same series — yet it gets the full level-shift treatment: 78 blacked-out
sessions and a segmentation boundary that reseeds every recursive
indicator. Framed at the time as "a large amount of valid history
discarded for a defect that neutralising a single return already handles."

**That framing turned out to be wrong, and it was wrong because it looked
at the flags in isolation from the liquidity filter (Decision 5) that
already runs beside them.** Measured against the actual modelling universe
(`fails_liquidity_filter = 0 AND below_minimum_history = 0`, 208 of 599
ingested symbols at the shipped 0.15 threshold):

| shape | total | inside modelling universe | % inside |
| --- | --- | --- | --- |
| `invalid_close` | 1,127 | 0 | 0.0% |
| `missed_split` | 864 | 19 | 2.2% |
| `bad_print` | 770 | 16 | 2.1% |

Bad prints are overwhelmingly a symptom of thin trading — confirmed
separately by `stale_close_fraction`'s correlation with average volume
(−0.84 across 573 symbols with enough history to measure it, decile 1
medians at 0.972, essentially never trading). The liquidity filter was
already excluding almost every symbol where a bad print would occur, for a
reason unrelated to the print itself. **16 events across 7 symbols**
remain inside the modelling universe — at 78 sessions each, at most 1,248
session-rows (less with overlap) against 255,467 usable modelling rows:
well under 0.5%. The "large amount of valid history" the original framing
worried about was never inside the set anything will train on.

**Decided: option (c), leave it**, on the strength of that measurement
rather than as a default. Options (a) (classify bad prints as their own
reason, giving them only return-neutralisation, not the blackout) and (b)
(repair by interpolation, rejected on the same grounds Decision 9 rejected
it for splits) remain available if the scope changes — see below — but
building either now would spend real work narrowing a defect that already
touches under 0.5% of what matters.

**This resolution is coupled to the liquidity threshold, not independent
of it.** Decision 13's scope is a direct function of where that threshold
sits, and it is not flat:

| liquidity threshold | symbols in universe | `bad_print` events | `missed_split` events |
| --- | --- | --- | --- |
| 0.15 (shipped) | 208 | 16 | 19 |
| 0.20 | 269 | 19 | 24 |
| 0.25 | 310 | 32 | 36 |
| 0.35 | 368 | 62 | 56 |
| 0.50 | 417 | 205 | 164 |
| 0.70 | 455 | 384 | 315 |
| disabled | 573 | 755 | 861 |

Past roughly 0.35–0.50 the counts climb sharply and this decision comes
back into play. **Loosening the liquidity threshold (Decision 5) must
reopen this decision, not be treated as independent of it** — the two were
resolved together by the same measurement, and revisiting one without the
other would silently reintroduce the discarded-history cost this
resolution just measured away. If the threshold is loosened, re-run
`report_ingest_outcomes.py`'s classification against the new modelling
universe *before* retraining on it, so that a change in results can be
attributed to one change at a time rather than two landing together.

## Risks / Trade-offs

- **A ~630-symbol batch is a long, rate-limited run that may take hours** →
  Resumable by construction (Decision 6); per-symbol failures recorded and
  skipped rather than aborting the run.
- **Observed-range universe reconstruction is approximate for symbols that
  changed exchange mid-life** → Accepted. It is strictly better than
  survivor-only, and Decision 2 records why exact reconstruction is not
  available.
- **The hard gate misses corrupt HOSE rows between 7% and 15%** → Accepted
  and quantified in Decision 3; the soft flag surfaces them for review even
  though it does not exclude them.
- **`STALE_PRICE_WARN_THRESHOLD = 0.15` was never validated beyond 9
  large-caps and may exclude too much or too little across 405 names** →
  Measurement stored per symbol so the threshold is re-tunable without
  re-ingestion (Decision 5).
- **DB grows ~10 MB → ~250-300 MB, and full-universe feature recomputation
  becomes expensive** → Decision 7 bounds recomputation to changed tickers;
  SQLite handles this row count comfortably.
- **`vnstock`/`vnai` prompt-injection regression** → `KNOWN_ISSUES.md`
  records that the patch lives only in the gitignored `backend/.venv` and is
  lost on any reinstall. This change involves heavy vnstock use and probable
  environment work. The durable fix should land before the batch runs, not
  after — see Migration Plan step 0.
- **Mid-life missed split adjustments corrupt level-based indicators for up
  to 78 sessions** → Resolved by Decision 9: indicator columns are nulled
  for that lookback. Residual risk is that the flag rate at 405 tickers is
  far above the 1-in-15-tickers rate measured here, making the ~0.26% data
  cost materially larger; task 9.1 measures it and Decision 9 names that as
  the trigger to reconsider detect-and-repair.
- **Delisted-symbol history availability could change** → Verified working
  for 8 of 8 sampled symbols, but it is an undocumented behaviour of a
  third-party free tier. If it regresses, the universe silently reverts to
  survivor-only. Recording per-symbol ingestion outcomes (Decision 1) makes
  that visible rather than silent.

## Migration Plan

0. **Land the `vnstock`/`vnai` durable fix first** (`KNOWN_ISSUES.md`).
   Non-negotiable ordering — a fresh venv during this work silently
   reintroduces the injection writes.
1. Add the universe table and the quality-flag sidecar. Additive only; no
   existing table is altered.
2. Build universe construction and populate it from the listing. No OHLCV
   fetching yet — this step is verifiable on its own.
3. Add the quality gate and wire it into `load_ticker`. Verify against the
   existing 15 tickers, where the expected result is known exactly: `VHM`
   2018-08-14 hard-flagged, the 24 `ACB`/`VIB`/`VND` pre-migration rows soft-
   flagged only, 11 tickers entirely clean.
4. Backfill universe metadata for the 15 already-loaded tickers. This is
   also the first exercise of the flag-persistence path — after step 3 the
   sidecar and `stale_close_fraction` were both still empty, so steps 1-3
   leave the exclusion machinery wired but inert.
5. Run the batch ingestion.
6. Pick both thresholds from the observed distribution across the ingested
   universe, then enforce the filters. **Must follow step 5**:
   `observed_session_count` and `stale_close_fraction` are populated by
   ingestion, not by universe construction, so neither threshold can be
   chosen empirically before the data exists.
7. Switch `GET /tickers` to the universe-derived catalog. **Must follow
   step 6** — the endpoint serves the universe's default filters, and
   switching before they exist would serve all 634 symbols, delisted names
   included, to a frontend built for nine.

*Revised ordering.* An earlier draft placed the catalog switch at step 5 and
the thresholds last. That was wrong in two ways: the catalog depends on
filters the thresholds define, and the thresholds depend on data only
ingestion produces.

**Rollback**: steps 1-4 are additive and inert. Step 5 produces data that
can be deleted by listing status without touching the original 15. Step 7 is
the only behavioural change to a served endpoint and reverts by restoring
the `TRAINING_TICKERS` read.

## Open Questions

1. ~~**Minimum-history threshold.**~~ **Resolved 2026-09-07: 250 sessions**
   (`MINIMUM_HISTORY_SESSIONS`). The plan was to pick this from the observed
   distribution, and the distribution turned out to be no help: it is
   bimodal, with most symbols pinned at the ~2,000-session tier ceiling and
   a small short tail (11 of the first 197 under 250 sessions, minimum 1),
   so there is no natural gap to cut at. What is defensible is the
   pipeline's own arithmetic — 78 sessions to the indicator warm-up, a
   60-session Advice volatility window, 30 clean rows for a single-ticker
   backtest — which 250 satisfies with ~170 usable rows to spare.
   **New threshold, not covered by rules 1-6.** Symbols below it are
   flagged, never deleted, so it is re-tunable without re-ingesting.
2. ~~**Should delisted-but-never-HOSE symbols be ingested?**~~
   **Resolved 2026-08-28: ingest all 229, filter at query time.** They carry
   no historical exchange field, so there is no way to identify the HOSE
   subset before fetching. Over-ingesting costs one-time minutes and
   preserves every genuinely delisted HOSE name — which is the entire point
   of the change — at the cost of also holding former HNX/UPCOM names that
   are excluded when a HOSE-only universe is requested. Under-ingesting
   would reintroduce the survivorship bias through a one-way door.
   *Noted for later, not adopted now*: exchange could plausibly be inferred
   empirically from each symbol's price-limit signature (returns clustering
   at ±7% indicates HOSE, ±10% HNX, ±15% UPCOM), reusing the gate's own
   machinery. Worth testing once the data is in; not required for this
   change.
3. **Does `near_gap` need revisiting at this scale?** It excludes ~35% of
   rows via Senkou Span B's 78-row lookback (`MODEL_CARD.md`). Across 405
   tickers with varied listing dates the excluded fraction may differ
   substantially. Out of scope here, but the measurement becomes available.
   ~~*Still open, and now measurable.*~~ **Measured 2026-09-07: 35.6%
   across the whole ingested universe** (372,186 of 1,044,135 feature
   rows), and 35.6% again within the filtered modelling universe. That is
   indistinguishable from the ~35% `MODEL_CARD.md` records for the original
   9, so the answer to this question is *no* — the excluded fraction does
   not differ substantially at scale, despite the varied listing dates.
   Usable rows (clean, labelled, and with non-null indicators) come to
   623,882 overall, 59.8%; within the modelling universe 255,467 of
   399,369, 64.0%. Two things still make the warm-up worth revisiting some
   day, just not because the rate changed: the blackout adds its own
   78-session voids on top of `near_gap`'s (Decision 11), and the tier
   ceiling compresses every symbol's history into the same ~8 years, so a
   fixed 78-row warm-up costs a larger share of a short history than of a
   long one.
4. ~~**Should HNX follow?**~~ **Declined 2026-09-07 — not now.** The owner
   works mostly on HOSE and does not need HNX at present. The schema
   accommodates it unchanged (`ticker_universe.exchange`, and the gate
   already carries HNX's ±10% limit), so this is a matter of spending the
   ingestion time later, not of building anything further.

6. **The 8-year tier ceiling bounds every claim made over this data.**
   Recorded 2026-09-07 after the owner confirmed 8 years is the intended
   depth. The community tier caps each symbol's history at roughly 8 years,
   and the ingest takes the maximum available for every symbol, so the
   survivorship-bias-free universe effectively begins in 2018 no matter
   when a company listed. Two consequences worth stating plainly: a
   "point-in-time universe as of 2015" cannot be reconstructed at all, and
   a delisted symbol that died before ~2018 contributes nothing, so
   survivorship correction is complete only from 2018 onward. A Community
   API key raises the request rate but does **not** lift this ceiling.
5. ~~**Decision 9 — how far a hard flag's contamination reaches.**~~
   **Resolved 2026-08-28** — see Decision 9. Indicator columns are nulled
   for the longest lookback after a flagged session; detect-and-repair is
   deferred, with task 9.1's measured flag rate as the trigger to reopen.
