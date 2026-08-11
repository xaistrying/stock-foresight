# M5 Dashboard Explore Notes (2026-08-11)

Captured from an `/opsx:explore` session discussing the dashboard structure,
prompted by a reference screenshot (chart panel + ticker chips + AI insight
panel + top control bar). This is exploratory context, not a spec — it
records what was decided, what was explicitly ruled out, and open threads
for whoever continues this. See also the `m5-frontend-reset-2026-08-07`
memory for why the previous attempt at this change was discarded.

## Context corrections vs. the reference screenshot

- Real ticker catalog is **9 fixed Vietnamese tickers**
  (`TRAINING_TICKERS` in `backend/app/ml/training.py`): `TCB, VIB, VHM,
  VND, MWG, HPG, MSN, VNM, SAB`. The screenshot's `AAPL/TSLA/NVDA/MSFT/
  AMZN` are placeholder US large-caps and must not carry into any real
  mockup or copy.
- Lesson: a borrowed reference's *content*, not just its layout, needs
  auditing before reuse — same applies to any future screenshot/mockup
  brought in as a structural reference.

## Decisions made this session

### Scope
- This change (new M5) **absorbs M6's AI insight panel** (Confidence,
  Sentiment, Advice) rather than leaving it a placeholder — a deliberate
  scope expansion vs. the old rejected proposal, which reserved M6 as a
  future placeholder only. Confirm this framing explicitly when the new
  proposal.md is written (it changes what "done" means and pulls rules
  3-6 into scope now, not later).

### Ticker selection: chips + search
- Chip row shows all 9 trained tickers, always.
- Search resolves **any real ticker** vnstock can fetch (not limited to
  the 9) — if not yet in the DB, it triggers the load flow
  (`POST /tickers/{ticker}/load`) the same way an unloaded chip would,
  and the ticker is added to the selectable list once loaded.
- Chip/list state per ticker: **Loading** (transient, load+predict in
  flight) / **Fresh** (prediction's `as_of` matches the latest available
  trading session) / **Stale** (a newer session's data is available but
  hasn't been re-predicted yet). "Not yet predicted" is not a resting
  state — see auto-predict decision below.

### Prediction scope: any ticker, but Confidence differs
- `predicted_log_return` is served for **any** loaded ticker, trained or
  searched-in. Confirmed mechanically safe: the model takes 14 OHLCV-
  derived indicator columns only, no ticker-identity feature
  (`design.md` Decision 3 of the archived `xgboost-training-pipeline`
  change) — a forward pass works on any ticker's computed features.
- **Confidence (rule 4) only has a real value for the original 9.**
  `compute_rolling_hit_rate(ticker)` (`backend/app/ml/backtest.py`)
  returns `None` for any ticker with no rows in `backtest_predictions`,
  and that table is only ever populated by the offline M3 walk-forward
  training/backtest job over the fixed 9 — there is no live/incremental
  mechanism today that would ever populate it for a searched-in ticker.
- For a non-trained ticker: Confidence shows an explicit **"N/A / not
  enough backtested history"** state (using the existing `None` return,
  not a fabricated number), plus a **"Backtest this ticker"** button.
  - This button is genuinely new scope: a scoped-down, single-ticker
    walk-forward retrain (a variant of `run_walk_forward_backtest`),
    gated on the ticker having enough historical rows to form at least
    one fold (current fold boundaries span multi-year windows). Not a
    quick wire-up — needs real design if picked up.
  - Sentiment (rule 5) is unaffected — it's computed live from
    `rolling_std(returns, 60 sessions)` on the ticker's own price
    history, no training-set dependency.

### Auto-predict on load
- Loading a ticker (chip click or search-triggered load) **immediately
  triggers its prediction too** — consistent with the old spec's
  "loading refetches prediction" requirement. Confirmed safe: the served
  model is a frozen, read-only artifact (`app.state.model`, loaded once
  at FastAPI startup in `main.py`); a prediction call is just
  `model.predict(...)`, no training, no state mutation, no drift risk.
  No champion/challenger gate needed for *this* — that pattern belongs
  to model retraining, a separate concern (see below).

### Top control bar: removed entirely, not relocated
The screenshot's top bar (`horizonDays` slider, `adviceStyle` dropdown,
`showDisclaimer` toggle) is dropped from the real dashboard, not just
moved:
- **`horizonDays` slider** — implied the prediction horizon is user-
  adjustable. Rule 1 fixes the target at exactly 5 trading sessions
  ahead; that's baked into the trained model, not a runtime parameter.
  A slider suggesting otherwise is a rule-1 conflict risk. Removed. The
  "5 trading sessions" fact can appear as static label text near the
  prediction instead.
- **`showDisclaimer` toggle** — rule 6 requires the disclaimer to appear
  unconditionally anywhere Advice/Confidence/Sentiment is shown; making
  it toggle-off-able directly contradicts that. Removed — disclaimer
  always renders alongside the AI insight panel.
- **`adviceStyle` dropdown** — dropped along with the rest of the bar
  (not picked apart individually since the whole bar is gone).
- Lesson: mockup control affordances can smuggle in a domain-rule
  violation just by existing as a plausible-looking UI convention. Each
  control needs to be checked against what it implies is variable/
  optional, not just evaluated on how it looks.

### Retrain-and-promote: explicitly out of scope, and off this UI
- Loading new tickers accumulates new rows in `features`/`ohlcv`, but
  nothing today feeds that back into the model — `pooled_xgb_model.json`
  is only ever produced by a manual/offline run of `train_final_model`.
- A future retrain-and-promote mechanism (with a champion/challenger
  comparison — rerun backtest hit-rate for candidate vs. currently-
  serving model before promoting) is real, legitimate future scope, but:
  - **Not part of this dashboard change** — touches the training
    pipeline and model storage, not the frontend.
  - **Likely candidate for M7** (SageMaker integration) or a standalone
    pre-M7 MLOps step, per `openspec/config.yaml` milestone list.
  - **Should not appear on the trader-facing dashboard at all** — it's
    an operator/maintainer concern, not something the stated audience
    (individual Vietnamese retail investors) needs to see. Decided
    explicitly: no placeholder, no reserved layout space, not even a
    footer meta line. If ever built, it gets its own admin surface (or
    just docs/MODEL_CARD.md + a CLI tool), fully separate from this
    dashboard.

## Open threads (not yet resolved)

- **Chart forecast overlay**: the reference screenshot shows a dashed
  line extending the chart past "Today" to represent the forecast. The
  old (rejected) spec explicitly forbade this: "Chart panel renders
  OHLCV only... SHALL NOT render any indicator overlay or any
  predicted-vs-actual series." Given the model produces a single
  5-session-ahead point prediction (not a day-by-day curve), what would
  a forecast overlay even honestly represent? Needs its own discussion —
  flagged but not discussed this session.
- **"Backtest this ticker" button UX**: gating condition (how much
  history is "enough"), in-progress state (spinner? estimated duration?
  does it block the rest of the panel?), and where it sits in the
  Confidence card layout — not designed, just scoped as necessary.
- Whether the new proposal.md should explicitly rename/reframe the
  change now that it absorbs M6 scope (e.g. is it still
  "vite-react-dashboard-ticker-panel," or does it need a new change
  name reflecting the combined M5+M6 scope?).

## Current settled dashboard shape (ASCII reference)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Stock Prediction                             [search: any ticker]   │
│                                                                      │
│  chips: TCB VIB VHM VND MWG HPG MSN VNM SAB (+ any searched-in)      │
│         each showing Fresh / Stale / Loading state                   │
├──────────────────────────────────────────────────────────────────────┤
│   Chart: OHLCV candles                     │  Prediction (%, rule 2) │
│   (forecast overlay = open thread)         │  Confidence:            │
│                                            │   • trained-9: real     │
│                                            │     hit-rate (rule 4)   │
│                                            │   • searched: "N/A" +   │
│                                            │     [Backtest ticker]   │
│                                            │     button (gated on    │
│                                            │     history depth)      │
│                                            │  Sentiment (rule 5,     │
│                                            │   labeled proxy)        │
│                                            │  Advice (rule 3)        │
│                                            │  Disclaimer — always on │
│                                            │   (rule 6, no toggle)   │
└──────────────────────────────────────────────────────────────────────┘
```
