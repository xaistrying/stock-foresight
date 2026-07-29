## Context

M1 persists raw OHLCV rows per `(ticker, date)` with advisory (non-blocking)
gap detection: sessions more than 5 calendar days apart are logged but never
filtered or repaired. M3 (XGBoost training) needs a feature table derived
from `ohlcv`, computed once here rather than recomputed ad hoc at training
and serving time. This change is compute-and-persist only: no training, no
API, no UI.

The six indicators are already named in `openspec/config.yaml`'s milestone
line (Ichimoku, RSI, MACD, Bollinger, ATR, OBV) — this design treats that
list as a starting hypothesis to validate in M3's backtest, not a closed
decision. Each indicator is chosen to cover a distinct signal family so the
feature set isn't redundant with itself:

```
Trend/regime   -> Ichimoku (price vs. cloud, cloud twist)
Momentum       -> RSI, MACD (speed/persistence of recent moves)
Volatility     -> Bollinger, ATR (dispersion / turbulence)
Volume confirm -> OBV (does volume agree with price direction)
```

## Goals / Non-Goals

**Goals:**
- Compute Ichimoku, RSI, MACD, Bollinger Bands, ATR, and OBV per
  `(ticker, date)` from `ohlcv`.
- Compute and persist `target_t = ln(close[t+5] / close[t])` (Rule 1) in the
  same table, since it's derived from the same per-ticker time series and
  M3 needs features and target joined for training.
- Flag rows whose indicator values are computed across a warm-up window
  that overlaps an M1-detected gap, or the start of a ticker's series,
  via a `near_gap` boolean, so M3 can choose to exclude/downweight them.
- Make re-running feature computation for a ticker idempotent (upsert),
  matching M1's upsert pattern for `ohlcv`/`tickers`.

**Non-Goals:**
- Not deciding M3's training pipeline, feature selection, or backtest
  methodology — only producing the table it will read.
- Not implementing rule 3's advice-threshold calculation
  (`0.5 x rolling_std(returns, 60)`) — that's M6 UI/advice logic. This
  change computes ATR and Bollinger width for the model, which are
  intentionally a *different* volatility measure (see Decisions).
- Not implementing rule 5's sentiment-proxy UI labeling — this change only
  produces the RSI/MACD/Ichimoku values rule 5 will later read.
- Not validating whether any given indicator actually improves prediction —
  that's an M3 backtest question (see Open Questions).

## Decisions

### 1. New `features` table, not new columns on `ohlcv`
`ohlcv` is a raw-data table per M1's spec (`ticker-data-ingestion`); adding
derived columns to it would blur that boundary and force recomputation
semantics onto a table whose spec already defines upsert behavior for raw
fetch results. A separate `features` table, keyed `(ticker, date)`, upserted
independently, keeps `ohlcv` untouched (no delta spec needed for
`ticker-data-ingestion`) and lets feature computation be re-run/versioned
later without touching ingestion.

### 2. `near_gap` is a boolean flag, not a filter
Per the M2 explore discussion: gaps in `ohlcv` are advisory, not blocking
(M1 rule), so indicator computation must not assume a contiguous daily
series. Rather than silently producing garbage at gap edges (e.g. an EMA
jumping across a 3-week hole as if it were one trading day) or dropping
those rows outright (which would silently shrink training data with no
record of why), this change computes indicators over the sequential stored
rows as-is and additionally computes, per row, whether any input date
within that row's largest lookback window (Ichimoku's 52-period Senkou
Span B is the longest) falls on the far side of a logged gap or before the
ticker's first stored session. `near_gap = 1` in that case. M3 decides
whether to exclude, downweight, or keep these rows — that decision is out
of scope here.

**Alternatives considered:**
- *Ignore gaps entirely*: rejected — silently trains on indicator artifacts
  near gaps with no way to audit or exclude them later.
- *Drop rows near gaps at computation time*: rejected — makes M2's output
  silently smaller with no record of what was excluded or why; M3 may want
  the rows for some purposes (e.g. only excluding from ATR-dependent
  features but not others) and can't recover that choice once rows are gone.

### 3. ATR/Bollinger (features) vs. `rolling_std(returns, 60)` (Rule 3) are
   deliberately two different volatility numbers
Rule 3's advice threshold is defined as `0.5 x rolling_std(returns, 60
sessions)` — a close-to-close return-based volatility measure, computed at
advice time (M6), not here. ATR (true-range-based, typically 14-period) and
Bollinger Band width (close-based, typically 20-period) are model *input
features* for M3's regressor, computed here. These serve different
purposes (model input vs. advice-threshold denominator) and use different
window lengths and source quantities, so this design keeps them as
separate, independently-named columns rather than trying to unify them into
one "the" volatility number. If M3/M6 later find they want one canonical
volatility calc shared by both, that's a future change, not assumed here.

### 4. Indicator computation library: hand-rolled vs. `pandas-ta`
Deferred to tasks.md as an implementation-time choice, not a design
commitment, since it doesn't affect the schema or requirements — pick
whichever library produces standard-definition Ichimoku/RSI/MACD/Bollinger/
ATR/OBV with parameters explicit (no silent library defaults), and document
chosen parameters (periods, smoothing) in `docs/DATA_DICTIONARY.md`.

### 5. Feature computation always recomputes the full per-ticker series,
   not incrementally
OBV is a cumulative running total from a ticker's earliest stored row —
unlike RSI/MACD/Bollinger/ATR/Ichimoku, which only need a bounded lookback
window, OBV's correctness depends on being computed over the complete
ordered history every time. If feature computation ever processed only
rows appended since the last run, existing rows' OBV values could silently
drift depending on how many times and in what order computation ran. To
avoid a special case for one indicator, this applies uniformly: computing
features for a ticker means recomputing every row in `features` for that
ticker from its earliest stored `ohlcv` row, then upserting the full
result — not an incremental/append-only update. Cost is small at current
scale (~2000 rows per ticker given M1's tier cap); revisit only if a
ticker's history grows large enough that full recompute becomes expensive.
Not tied to any of the 6 domain rules — new correctness constraint.

**Alternatives considered:**
- *Incremental computation*: rejected — correct for the five bounded-window
  indicators but silently wrong for OBV; maintaining two recompute
  strategies inside one function is more error-prone than always
  recomputing everything.

### 6. Ichimoku: Senkou Span A/B use the standard forward-shifted
   (as-charted) convention; Chikou Span is replaced with a leakage-safe
   proxy, not the standard backward-shifted convention
Senkou Span A/B "as charted" at row D are computed from data as of
`D-26` — built entirely from data on or before D, safe to store this way.
Chikou Span "as charted" at row D would require `close(D+26)` — 26
sessions of future data relative to D. Storing that literally would leak
future price information into a feature, and leak *more* future
information than `target` itself is defined on (target: 5 sessions ahead;
literal Chikou: 26). This is a correctness bug, not a style choice, if
implemented by the book.

**Decision**: Senkou Span A/B use the standard forward-shifted convention.
Chikou Span is replaced by `chikou_signal(D) = close(D) - close(D - 26)`
(or a boolean `close(D) > close(D-26)`) — the comparison Chikou is meant
to signal (current price vs. N sessions ago), computed using only data on
or before D. Column named `chikou_signal`, not `chikou_span`, so the
schema itself signals it's a derived comparison, not the raw charted line.
Not tied to any of the 6 domain rules — new correctness constraint.

**Alternatives considered:**
- *Literal as-charted Chikou*: rejected — the leakage bug described above,
  not viable regardless of documentation.
- *All three unshifted*: rejected — makes Senkou A/B not match what
  Rule 5's "Market Sentiment" is supposed to represent, for no safety
  benefit, since Senkou's shift is leakage-safe anyway.

### 7. Default indicator periods (starting values, tunable in M3)
Explicit periods, since Decision 2's near_gap logic already depends on
knowing which window is longest, and code needs concrete values regardless:
- RSI: 14
- MACD: 12/26/9 (fast/slow/signal)
- Bollinger Bands: 20-period, 2 standard deviations
- ATR: 14
- Ichimoku: Tenkan 9 / Kijun 26 / Senkou B 52 (standard; also the window
  Decision 2's near_gap check treats as longest)
- chikou_signal: 26 (fixed by Decision 6's leakage-safe definition — not a
  tunable choice in the same sense as the others)

Starting defaults, not permanently fixed — M3's backtest may motivate
tuning any of these. If periods change, `computed_at` (Decision 8) is the
only breadcrumb distinguishing which rows were computed under which
parameter set; there is no formal parameter-version column in this change.

### 8. `computed_at` timestamp added; full parameter-versioning deferred
A `computed_at TIMESTAMP` column is added to `features`, set on every
upsert. This is NOT a parameter/schema version — it records when a row was
computed, not what periods or Chikou definition produced it. It's a cheap
breadcrumb: if indicator parameters change later, tickers whose
`computed_at` predates that change are the ones whose features are stale
relative to the new definition (assuming reload → Decision 5's full
recompute is what brings a ticker current). A real parameter-version
column is deferred; the trigger for building it is "computed_at
comparison stops being precise enough," which hasn't happened yet.

## Risks / Trade-offs

- **[Risk]** Vietnamese tickers may have thin trading history (M1's ~8-year
  tier cap, `possibly_truncated_by_tier`) → longer-window indicators
  (Ichimoku's 52-period component) may have very few valid, non-`near_gap`
  rows for recently-listed or tier-truncated tickers. **Mitigation**: this
  is visible via `near_gap` plus M1's existing `possibly_truncated_by_tier`
  flag; M3 can decide per-ticker whether enough clean history exists to
  train on, rather than this change silently producing thin or misleading
  feature rows.

- **[Risk]** Six indicators across four families is a design hypothesis,
  not a validated feature set — some may add no predictive value over a
  volatility-only baseline, or may add overfitting risk given a limited
  number of independent 5-session windows per ticker. Concretely: ~2000
  stored sessions per tier-capped ticker is closer to ~400 *non-overlapping*
  5-session windows, since a 5-session-forward label shares 4 of 5 days
  with its neighbor's label — the effective sample size for validating
  15+ raw feature columns against is much smaller than row count suggests.
  **Mitigation**: not fixed here; flagged as an M3 backtest question
  (ablation: OHLCV+volatility baseline vs. full six) — this change computes
  all six so that ablation is possible later, but does not claim they're
  all justified yet.

- **[Trade-off]** Every feature computation run for a ticker recomputes and
  upserts its *entire* stored history from the earliest `ohlcv` row, not
  just new/changed rows (Decision 5) — required for OBV's correctness, not
  only for the narrower case of a schema/parameter change. Cost is small at
  current scale (~2000 rows/ticker under M1's tier cap); revisit if a
  ticker's history grows large enough that full recompute becomes
  expensive, or if per-ticker compute time becomes noticeable at M5's VN30
  batch scale.

- **[Risk]** Chikou Span's near-miss (Decision 6: the literal as-charted
  definition would have leaked 26 sessions of future data) shows look-ahead
  leakage is an easy mistake in this specific feature family, not a
  one-time fluke. Any indicator added later carries the same risk.
  **Mitigation**: task 7.6 establishes a guard-test pattern (assert no
  indicator's inputs at row D include any `ohlcv` row dated after D) —
  apply this same guard to any future indicator addition, not only to
  Chikou.

- **[Risk]** `computed_at` (Decision 8) records *when* a row was computed,
  not *what parameters* produced it — it's a proxy for staleness, not a
  real parameter version. If two different parameter sets were ever
  computed with overlapping timestamps (e.g. a partial rollout across
  tickers), `computed_at` alone can't disambiguate which parameters
  produced a given row. **Mitigation**: accepted for now, given no
  versioning requirement yet; if this scenario becomes real (e.g. mid-M3
  parameter tuning applied ticker-by-ticker rather than all-at-once), that
  is the trigger for building real parameter versioning, not before.
