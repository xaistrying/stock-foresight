## Context

M2 delivered a `features` table (Ichimoku, RSI, MACD, Bollinger, ATR, OBV,
`target`, `near_gap`) per `(ticker, date)`, computed leakage-safely from
`ohlcv`. Nothing trains against it yet. Two tickers were loaded during M1/M2
(TCB, VIB); nine are loaded now (see Decision 1) via M1's existing
`POST /tickers/{ticker}/load`, called manually per ticker — no batch-loading
capability exists or is built here.

This is M3's first pass: prove the pipeline (load -> split -> train ->
backtest -> persist -> document) works correctly end-to-end, not to
produce a tuned or final model. Hyperparameter tuning, additional tickers,
and a ticker-identity ablation are explicitly deferred (see Non-Goals).

## Goals / Non-Goals

**Goals:**
- Train a single pooled XGBoost regressor predicting `target` (Rule 1) from
  the existing indicator columns, across a fixed 9-ticker set.
- Validate with a leakage-safe, pooled, expanding-window walk-forward
  backtest — no shuffled k-fold, no simulated trading/P&L layer.
- Define and compute a hit-rate metric that Rule 4's confidence score can
  read directly.
- Persist the trained model artifact and backtest results in a form M4 can
  load and M6 can query.
- Create `docs/MODEL_CARD.md`, documenting data, features, split
  methodology, hyperparameters, and results.

**Non-Goals:**
- Hyperparameter tuning — conservative, untuned defaults only (see
  Decision 5). Tuning is a future iteration once this pipeline is proven.
- Building a batch/bulk ticker-loading capability — the 9 tickers were
  loaded manually via M1's existing single-ticker endpoint.
- Ticker-identity-as-feature ablation (see Decision 3) — deferred until
  enough tickers exist for a meaningful held-out-ticker test; 9 is too few.
- Simulated trading returns / P&L backtesting — walk-forward accuracy
  metrics only. A P&L layer would risk implying "this makes money" even in
  an internal doc, in tension with Rule 6's no-investment-advice framing.
- FastAPI endpoints (M4) or any UI (M5/M6) — this change stops at a
  persisted model + backtest results + Model Card.
- Regime-adaptive (rolling-window) backtesting — expanding window only
  (see Decision 4); usable history is already thin after excluding
  `near_gap` rows.

## Decisions

### 1. Training set: 9 tickers, chosen by empirical screening, pooled model
TCB, VIB (already loaded, banks), plus VHM (real estate), VND (securities/
brokerage), MWG (retail), HPG (industrials/steel), MSN (consumer
conglomerate), VNM (consumer staples), SAB (beverage) — selected by running
a realized-volatility + stale-price screen
(`backend/scripts/screen_ticker_volatility.py`) directly against loaded
`ohlcv` data, not from memory-based assumptions about which VN stocks are
"volatile" or "stable." All 9 show comparable history length (~1990-1997
rows) and no stale-price warnings (>15% same-as-previous-close sessions),
so none is a disguised illiquidity case masquerading as "stable."

A single pooled model is trained across all 9 (not per-ticker), specifically
so the walk-forward backtest can test whether technical-indicator signal
generalizes across sectors — with only banks (TCB/VIB), a backtest can't
distinguish "this indicator combo predicts returns" from "this indicator
combo fits bank-sector regime behavior."

**Alternatives considered:**
- *Per-ticker models*: rejected for v1 — ~1200-1290 clean+labeled rows per
  ticker (see Decision 2) is too thin to train and validate 9 independent
  models meaningfully; pooling is also the only way to test cross-sector
  generalization, which is the actual open question this project needs
  answered (see Decision 3).
- *Sector-label-based selection without empirical screening*: rejected —
  the screening script exists specifically because sector labels alone
  don't reveal illiquidity-masquerading-as-stability; volatility and
  stale-price fraction are checked directly against this project's own
  data.

Not tied to any of the 6 domain rules — training-data-composition choice.

### 2. Row filtering: exclude `near_gap = 1`, keep only `target IS NOT NULL`
M2's design explicitly deferred this decision ("M3 decides whether to
exclude, downweight, or keep" near_gap rows). This change excludes them:
`near_gap = 1` means a row's indicator lookback window crossed a real
session gap (>5 calendar days) or extended before the ticker's first stored
row — the indicator values for that row are of *unknown* quality, not
verified wrong, just unverifiable. Training and backtesting on
unknown-quality rows would make a bad result ambiguous ("model doesn't
work" vs. "some rows were quietly corrupted"). Downweighting/keeping is a
reasonable ablation once a clean baseline exists to compare against — not
attempted here.

Empirically (checked against the loaded data, not assumed): `near_gap = 1`
is **not** a small warm-up-only fraction. It's ~35% of rows for 7 of the 9
tickers and ~38-39% for VIB/VND — confirmed to be driven by shared
HOSE-exchange holiday/closure calendar dates (identical `near_gap=1` date
sets across tickers on the same exchange), recurring across the full
~8-year history, not concentrated at series start. After filtering, 11,480
clean+labeled rows remain pooled across all 9 tickers (~1200-1290 each).

**Known blind spot** (documented here, not fixed): because flagged dates
cluster in bands following each recurring HOSE holiday closure (consistent
with post-Tet reopening periods), excluding them means the model is never
trained or backtested on the ~2-3 months following Lunar New Year each
year — a period Vietnamese equities may show a distinct volume/volatility
regime. This is a seasonal exclusion, not random missingness. Flagged as a
known limitation for `docs/MODEL_CARD.md`, not addressed by this change.

**Alternatives considered:**
- *Downweight near_gap rows instead of excluding*: rejected for v1 — adds
  a tuning parameter (the downweight factor) with no baseline to justify
  any particular value yet.
- *Keep all rows*: rejected — reintroduces the exact ambiguity (bad
  indicator values vs. bad model) this decision exists to avoid.

Not tied to any of the 6 domain rules — new correctness/data-quality
decision, resolving what M2's design left open.

### 3. No ticker-identity feature — pure OHLCV-derived indicators only
The model receives only the existing indicator columns (Ichimoku, RSI,
MACD, Bollinger, ATR, OBV) — no categorical or one-hot ticker column, and
no per-ticker target encoding. With only 9 tickers, a ticker-identity
feature has just enough cardinality for the model to partially memorize
per-ticker base rates ("VHM rows tend to look like X") instead of learning
transferable technical-analysis signal, which is the actual thing this
pipeline is testing for. If ticker-specific volatility genuinely carries
predictive information, ATR and Bollinger Band width already encode that
as continuous, transferable signal (per M2 design.md Decision 3, which
keeps these deliberately distinct from Rule 3's advice-threshold
calculation) — so omitting ticker identity doesn't discard that
information, it forces the model to read it through features that
generalize to tickers not seen during training.

**Deferred ablation** (not this change): once significantly more tickers
are loaded, test whether adding ticker identity helps or hurts performance
specifically on tickers *unseen* during training. With 9 tickers, a
held-out-ticker test is barely a test; not meaningful yet.

**Alternatives considered:**
- *One-hot ticker column*: rejected for the memorization risk above.
- *Per-ticker target encoding (e.g. mean historical return)*: rejected —
  same memorization risk, and additionally leaks each ticker's own
  historical target distribution into its own feature at training time
  unless computed with the same walk-forward discipline as the split
  itself, adding leakage-surface for no established benefit yet.

Not tied to any of the 6 domain rules — feature-set design decision.

### 4. Walk-forward split: pooled folds, expanding window, explicit purge gap
- **Pooled folds, not per-ticker folds**: every ticker's rows within a
  given date range belong to the same fold together — fold boundaries are
  shared calendar dates across all 9 tickers. Since near_gap-driving gaps
  are exchange-calendar events shared across tickers (Decision 2), and
  broader market-wide effects don't respect ticker boundaries, per-ticker
  fold boundaries would risk a market-wide event landing in training for
  one ticker and test for another at the "same" real-world time — pooled
  folds avoid that.
- **Expanding window, not rolling**: each successive fold's training set
  grows to include all prior folds' data, rather than sliding a
  fixed-width window forward. Given how thin usable history already is
  (M1's ~8-year tier cap, further reduced by excluding ~35-39% of rows to
  `near_gap`), this maximizes data used for training rather than discarding
  old data on a fixed window. Regime-adaptivity (VN market conditions
  plausibly shift over 8 years) is a legitimate future concern, but not
  solved in this first pass — revisit once a rolling-window comparison is
  actually needed.
- **Explicit purge gap, not a plain time-ordered split**: `target(t) =
  ln(close[t+5]/close[t])` (Rule 1) means row `t`'s label reads `close[t+5]`.
  Any training row whose 5-session-ahead label window extends into or past
  a fold's test-period start must be excluded from that fold's training
  set — not just "close in time," but specifically because its label
  literally depends on data inside the test window. Purge width =
  `TARGET_HORIZON = 5` rows (per ticker, by that ticker's own row
  position) immediately before each fold boundary, training side only — rows
  at positions T-5 through T-1 inclusive; even T-5's label reads close[T],
  the test set's first value, so it must be purged too. A test fold's own
  trailing edge needs no equivalent purge: a test row's label is real
  (computed from data at or before the point the row's horizon reaches), not
  leaked from a future fold — and rows at the true end of the whole series
  already have target IS NULL (confirmed against the last 5 rows of a full
  ticker series, per M2's own target-nullability design — target(t) requires
  close[t+5] to exist) and are dropped by Decision 2's filter regardless.
- **Fold count: 4-6.** Each fold boundary costs data to the purge gap;
  over-fragmenting an already-thin ~11,480-row pooled dataset across too
  many folds would defeat the point of using an expanding window to
  preserve data.

**Alternatives considered:**
- *Shuffled k-fold cross-validation*: rejected outright — target is a
  forward-looking label; shuffling would put future data in training for
  rows whose "test" neighbors are adjacent in time, a severe leakage bug,
  not a stylistic choice.
- *Per-ticker independent folds*: rejected — breaks the pooled-model
  generalization goal (Decision 1) and risks the cross-ticker leakage
  described above.
- *No purge gap (plain chronological split)*: rejected — this is the
  specific overlapping-label leakage risk this design exists to close;
  identified as a real risk during design discussion, not hypothetical.

Not tied to any of the 6 domain rules directly, but purge-gap sizing is
derived from Rule 1's 5-session horizon.

### 5. XGBoost hyperparameters: conservative, untuned defaults
No tuning pass in this change — the goal is proving the pipeline works,
not optimizing it. "Conservative" means a posture, not a locked numeric
config: shallow trees (e.g. `max_depth` 3-4), a moderate learning rate with
early stopping against a validation fold rather than a large fixed
`n_estimators`, subsample/colsample_bytree below 1.0 for regularization,
and a sane `min_child_weight` floor. This posture is chosen deliberately
given the sample-size ceiling: ~11,480 clean+labeled rows pooled, but
labels overlap 4-of-5 days with their neighbors (Rule 1's 5-session
horizon), so the *effective independent* sample size is far smaller than
row count suggests (M2's design.md flagged this same concern at ~400
non-overlapping windows per ticker before pooling) — aggressive
hyperparameters (deep trees, low min_child_weight, high n_estimators
without early stopping) overfit fastest in exactly this regime. Exact
numeric values are an implementation-time choice within this posture, not
fixed here.

Not tied to any of the 6 domain rules — model-configuration decision.

### 6. Hit-rate definition (feeds Rule 4's confidence score)
Rule 4 defines confidence as "backtested hit-rate over the ticker's most
recent ~60 predictions" but doesn't define what a "hit" is — that's decided
here, since it's new and not yet specified anywhere else.

**Decision**: a prediction is a **hit** if its sign matches the actual
`target`'s sign — i.e. `sign(predicted_target) == sign(actual_target)`,
a directional-accuracy criterion. This is the simplest criterion
consistent with Rule 4's own clarification that this is "not a statistical
prediction interval" — no magnitude/interval matching is attempted, only
direction. Hit-rate for a given ticker = fraction of hits over that
ticker's most recent ~60 backtested (out-of-fold) predictions, computed
from walk-forward results, not in-sample predictions.

**Zero-crossing edge case**: when `actual_target` is exactly `0`
(close[t+5] == close[t] exactly), sign is undefined. Treat as a **miss**
regardless of predicted sign — this is a data-defined edge case (extremely
rare for continuous prices) needing a fixed rule to keep hit-rate
well-defined; documented in `docs/MODEL_CARD.md` since it's a specific,
citable choice.

**Alternatives considered:**
- *Magnitude-threshold hit (e.g. within X% of actual)*: rejected —
  requires picking an arbitrary threshold with no principled anchor yet;
  sign-match is simpler and Rule 4 already disclaims interval-style
  precision.
- *Treat zero-actual as a hit regardless of prediction*: rejected — makes
  hit-rate artificially easier to inflate near a degenerate case, however
  rare.

This is a **new definition, not yet covered by openspec/config.yaml or
CLAUDE.md** — implements Rule 4, first precise specification of "hit."

### 7. Persistence: model artifact + backtest results storage
- **Model artifact**: persisted to `backend/data/models/` (new directory,
  gitignored — matches `backend/data/app.db`'s existing pattern of
  data-not-checked-in). Exact serialization format (e.g. XGBoost's native
  booster format) is an implementation-time choice.
- **Backtest results**: persisted in a form M4/M6 can query per ticker —
  either a new SQLite table (e.g. `backtest_predictions` storing each
  out-of-fold prediction, actual target, and hit/miss) or a results file;
  the exact storage mechanism (new table vs. file) is left to tasks.md/
  implementation, since it doesn't change this design's requirements-level
  behavior. Whatever the mechanism, it must support computing a ticker's
  rolling hit-rate over its most recent ~60 predictions (Decision 6) —
  this is the actual constraint driving the choice, not the storage
  medium itself.

Not tied to any of the 6 domain rules directly, but the ~60-prediction
rolling-window query requirement is derived from Rule 4.

## Risks / Trade-offs

- **[Risk]** Effective independent sample size (~11,480 rows, but
  4-of-5-day label overlap means far fewer truly independent windows) is
  small relative to 15 raw feature columns → real overfitting risk even
  with conservative hyperparameters (Decision 5). **Mitigation**: walk-
  forward backtest (Decision 4) with an explicit purge gap is the direct
  check for this — if backtest hit-rate is materially worse than in-fold
  training performance, that's the overfitting signal to watch for, not
  something this design can rule out in advance.

- **[Risk]** Excluding `near_gap` rows (Decision 2) systematically removes
  the same ~2-3-month post-Tet-holiday period every year, across every
  ticker, since gap dates are shared exchange-calendar events. The model
  is neither trained nor backtested on this recurring period.
  **Mechanism**: `near_gap` triggers on the single longest indicator
  lookback (Senkou Span B's 78-row window), so one ~1-week annual gap gets
  amplified into a ~78-session contamination tail — applied uniformly even
  to indicators with much shorter windows (RSI/ATR: 14-15 rows, MACD: 34,
  Bollinger: 20). **Mitigation**: documented explicitly in
  `docs/MODEL_CARD.md` as a known blind spot; not fixed in this change.
  **Future lever**, if this blind spot matters later: a per-column
  reliability flag instead of one blanket `near_gap` per row could recover
  much of this data for the five shorter-window indicators — real added
  complexity, not attempted here.

- **[Risk]** All 9 tickers are large-cap, liquid VN30 constituents
  (deliberately, per Decision 1's stale-price screening) — the pipeline
  and any resulting model are unvalidated on small/mid-cap or
  recently-listed tickers, which may have thinner history, more real gaps,
  and different liquidity dynamics. **Mitigation**: none in this change;
  flagged for whoever loads additional tickers later via M1's existing
  endpoint to re-run this same backtest methodology before trusting
  results on a different ticker population.

- **[Trade-off]** No ticker-identity feature (Decision 3) may cost some
  predictive accuracy if ticker-specific effects exist beyond what
  ATR/Bollinger width capture — accepted deliberately in exchange for a
  backtest that can actually speak to cross-sector generalization, which
  is this project's more important open question at this stage.

- **[Risk]** No simulated P&L/trading-return layer means this backtest
  cannot report anything like "expected return" or "win rate in $ terms" —
  by design (Non-Goals), to avoid Rule 6 framing risk, but means
  `docs/MODEL_CARD.md` and any future consumer of these results must be
  careful not to characterize hit-rate as investment performance.
  **Mitigation**: Model Card task explicitly requires "technical
  observation" framing per Rule 6, even though Rule 6's UI-facing
  disclaimer requirement (docs/DISCLAIMER.md) isn't created until M6 —
  this document isn't user-facing UI, but should still not overstate what
  a directional hit-rate implies.
