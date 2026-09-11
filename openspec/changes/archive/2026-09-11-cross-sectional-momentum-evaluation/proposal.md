## Why

`docs/DISCUSSION_model_direction.md` found that single-ticker directional
prediction of Rule 1's target is flat at every horizon tested (5 to 252
sessions): correlation ~0.01, sign unstable across folds, never beating
"always predict up" as a base rate. The one exception was cross-sectional
(relative, demeaned) momentum — small but growing and sign-stable with
horizon (+0.025 at 5 sessions to +0.056 at 63) — which the same document
could not evaluate as a strategy: at 15 tickers, a top decile is 1.5
stocks, too small to mean anything.

The `hose-universe-ingestion` change (archived 2026-09-07) exists
specifically to remove that constraint: 208 symbols now pass the
modelling-universe filters, giving a top decile of roughly 21 stocks. That
work is done and the question it was building toward — does the one
surviving effect actually hold at a workable scale — has not yet been
asked. This change asks it, formally and reproducibly, rather than as
another ephemeral scratchpad session whose numbers evaporate once cited.

Why now, specifically: the served model (`pooled_xgb_model.json`) is still
the July M3 artifact, untouched by six weeks of new data and 13x more
tickers, and 198 of 208 modelling-universe symbols currently show
Confidence as N/A. Any decision about what replaces or extends that model
should be made with this question answered, not before it.

## What Changes

- **New**: a reproducible cross-sectional momentum evaluation pipeline —
  computes date-demeaned momentum signals at 5/10/21/63-session horizons
  across the full 208-symbol modelling universe, using the same pooled
  walk-forward protocol (`compute_fold_boundaries`, expanding window, purge
  gap) `backend/app/ml/training.py` already establishes, so results are
  comparable to `docs/MODEL_CARD.md`'s existing figures rather than a new,
  incomparable methodology.
- **New**: decile-ranking evaluation — not just a raw correlation, but
  whether a top-decile / bottom-decile construction produces a real,
  sign-stable effect at 208 symbols, and the universe's effective breadth
  given its cross-sectional correlation structure (ρ̄ ≈ 0.41 measured
  earlier on 15 symbols; recomputed here on 208).
- **New**: the analysis is a durable, re-runnable script under
  `backend/scripts/`, matching the standard the project's own hardening
  work already applies to itself — `DISCUSSION_model_direction.md`'s
  "Reproducing these numbers" section records that its own scripts were
  never preserved, which this change deliberately does not repeat.
- **New**: a written verdict appended to `docs/DISCUSSION_model_direction.md`
  stating plainly whether the effect holds at scale, at what confidence,
  and what using it would actually require (a ranking/screening surface
  that does not exist today; portfolio construction guidance; holdings
  data not yet collected) — without pre-supposing which answer is correct.
- **Not changed**: `backend/data/models/pooled_xgb_model.json`, any API
  endpoint, any UI component, `docs/MODEL_CARD.md`'s existing content (only
  appended to, if this change's own protocol reuse surfaces something worth
  recording there), and none of the six non-negotiable domain rules.

## Capabilities

### New Capabilities
- `cross-sectional-momentum-evaluation`: an offline, reproducible analysis
  capability — computing and evaluating date-demeaned momentum signals
  across the modelling universe on the existing walk-forward protocol, and
  producing a durable, re-runnable verdict. This capability is analysis
  tooling, not a served feature; it has no API surface and no UI surface.

### Modified Capabilities
None. This change adds an analysis capability only. It reads
`ticker_universe`, `ohlcv`, and `features` (all already populated by
`ticker-universe`, `ticker-data-ingestion`, and `feature-engineering`) and
writes no rows to any table and no response to any endpoint. No existing
requirement's behavior changes.

## Impact

**Code**
- New: `backend/scripts/evaluate_cross_sectional_momentum.py` (or a small
  module it imports from, if the signal computation is worth reusing
  later) — read-only against the existing database.
- No change to `backend/app/ml/training.py`, `backend/app/api/*`, or any
  frontend code. The walk-forward primitives there are read and reused,
  not modified.

**Data**
- Read-only. No new table, no new column, no write to any existing table.
- Reads the 208-symbol modelling universe (`ticker_universe` filtered by
  `ingestion_state = 'ok' AND fails_liquidity_filter = 0 AND
  below_minimum_history = 0`) and each symbol's `ohlcv`/`features` history.

**Documentation**
- Appends a dated, evidence-bearing verdict section to
  `docs/DISCUSSION_model_direction.md` — the same document this change's
  motivation comes from — rather than opening a new file, so the whole
  arc from "direction is flat" to "is the one surviving effect usable at
  scale" stays in one place.
- If the measured ρ̄/effective-breadth figures materially update
  `docs/MODEL_CARD.md`'s existing per-ticker correlation table, note that
  as a candidate follow-up edit; this change does not itself commit to
  rewriting that document.

**Domain rules**
This change touches **none of the non-negotiable domain rules 1-6**. It is
read-only offline analysis: no change to the prediction target (Rule 1), no
UI display of any kind (Rule 2), no advice thresholds (Rule 3), no
Confidence definition or computation (Rule 4), no Sentiment labelling
(Rule 5), and no output served to a user (Rule 6). All six are honored
unchanged; none require sign-off. This is a deliberate, load-bearing
property of this change's scope, not an incidental fact — see Non-Goals in
design.md.

**Explicitly out of scope**
Production model retraining; any UI change; a decision on whether/how to
expose a ranking or screening feature if the effect holds; portfolio-risk
or holdings work. Each is named because a future change may reasonably
follow from this one's result, and this proposal's scope stops here on
purpose so that decision is made with evidence in hand, not assumed by
momentum.
