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

### Chart forecast overlay: single point, no fabricated path
- The model produces exactly **one scalar per prediction**
  (`predicted_log_return`, a single point 5 sessions ahead) — never a
  day-by-day trajectory. The reference screenshot's smooth dashed curve
  from "Today" out to "+7" implies interpolated points the model never
  produced.
- The old spec's blanket ban ("SHALL NOT render any indicator overlay
  or predicted-vs-actual series") was written when M5 had no prediction
  in scope at all — that premise no longer holds now that this change
  absorbs M6. The requirement is being **narrowed, not violated**: chart
  MAY show the single predicted point at t+5 (from `predicted_log_return`,
  converted per rule 2), connected to today's close by one straight
  dashed line — no fabricated intermediate points, no smooth curve. This
  needs to be written into the new `dashboard-ui` spec explicitly citing
  rule 6 (a curved/interpolated path would visually overclaim confidence
  in a trajectory that isn't real).

### "Backtest this ticker" button — settled shape
- **Gate**: enabled once the ticker has at least N clean+labeled feature
  rows (same `near_gap = 0 AND target IS NOT NULL` filter M3's training
  pipeline already uses). Exact N left for design.md to pick empirically
  (check what produces non-empty walk-forward folds in practice) —
  deliberately not a multi-year-span requirement, just "enough rows for
  a real fold," since requiring years of history would make the button
  practically unusable for any freshly-searched ticker.
- Below the row threshold: button is hidden/disabled, replaced by
  explanatory text ("Needs more price history to backtest").
- **In-progress state**: inline spinner on the button itself, button
  disabled while running; the rest of the AI insight panel (Prediction,
  Sentiment, Advice) stays fully interactive — a single-ticker backtest
  is real compute (seconds to tens of seconds) but shouldn't block
  anything else on the dashboard.
- On completion, Confidence transitions to the normal real-hit-rate
  display — no distinct "just backtested" visual state.

## Copy contract (for the design/build pass)

Drafted this session so a visual build (Hallmark / Claude design pass)
has fixed content to work from rather than inventing wording. Follows
the project's `copy.md` discipline (specific labels, no vague claims,
active/direct phrasing) applied against rules 2–6.

### Prediction
| State | Headline | Subtext |
|---|---|---|
| `ok` | `+2.3%` / `−1.1%` (converted from `predicted_log_return`, rule 2 — raw log return never shown) | `Projected close · 5 trading sessions` |
| `near_gap` | `Prediction unavailable` | `A recent data gap means the model can't produce a reliable estimate right now` |
| not loaded (404) | `Not loaded yet` | `Load this ticker to see a prediction` |
| feature failure (5xx) | `Prediction failed` | `Feature computation failed for this ticker — try reloading` |

### Confidence (rule 4)
| State | Headline | Subtext |
|---|---|---|
| has backtest history | `82%` + bar | `Hit-rate, last 60 predictions` |
| searched ticker, insufficient rows | `N/A` | `Needs more price history to backtest — check back after more sessions load` |
| searched ticker, enough rows, not run | `N/A` | `Enough history to backtest.` + button `Backtest this ticker` |
| backtest running | `N/A` | button label becomes `Backtesting…` (disabled, spinner) |
| backtest complete | `82%` + bar | same as "has backtest history" — no distinct transitional state |

### Sentiment (rule 5)
Label itself renamed to pre-empt misreading, not just annotated after
the fact:
| State | Headline | Subtext (always shown, not a tooltip) |
|---|---|---|
| any | `Technical Signal` (not "Market Sentiment") — value `Neutral` / `Bullish` / `Bearish` | `Based on RSI, MACD, Ichimoku position — not news or market sentiment` |

### Advice (rule 3, rule 6)
Framed as a conclusion from a stated criterion, not a bare directive.
**Decided: directional wording, not BUY/SELL** — those are literal
transaction verbs and read as instructions to act; "signal: up/down"
stays in observation-mode.
| State | Line 1 (reasoning, precedes verdict) | Line 2 (verdict) |
|---|---|---|
| within threshold | `Move is within normal volatility range` | `HOLD` |
| above threshold, positive | `Move exceeds typical volatility to the upside` | `Signal: up` |
| above threshold, negative | `Move exceeds typical volatility to the downside` | `Signal: down` |

### Disclaimer (rule 6 — always visible, no toggle)
- **Inline** (shown under the AI insight panel at all times):
  > Technical observation from a backtested model — not a forecast, not investment advice.
- **Full version** (linked/expandable; candidate first draft for
  `docs/DISCLAIMER.md`, created when this change ships since it's now
  M6-scope too):
  > This panel shows technical observations generated by a statistical model trained on historical price patterns (see `docs/MODEL_CARD.md`). Confidence reflects the model's own backtested hit-rate, not a guarantee. Sentiment reflects technical indicators (RSI, MACD, Ichimoku), not real news or market sentiment. Nothing here is investment advice or a recommendation to buy, sell, or hold any security.

## Open threads (not yet resolved)

- Whether the new proposal.md should explicitly rename/reframe the
  change now that it absorbs M6 scope (e.g. is it still
  "vite-react-dashboard-ticker-panel," or does it need a new change
  name reflecting the combined M5+M6 scope?).
- Visual container question: do Prediction/Confidence/Sentiment/Advice
  sit as separate stat-tile cards, or one continuous panel with
  dividers? Not settled — left for the design/build pass.

## Current settled dashboard shape (ASCII reference)

```
┌───────────────────────────────────────────────────────────────────────┐
│  Stock Foresight                             [search: any ticker]    │
│                                                                       │
│  chips: TCB VIB VHM VND MWG HPG MSN VNM SAB (+ any searched-in)       │
│         each showing Fresh / Stale / Loading state                    │
├───────────────────────────────────────────────────────────────────────┤
│   Chart: OHLCV candles                     │  Prediction              │
│   ─history──●╌╌╌╌╌○ (single t+5 point,     │  +2.3%                   │
│   dashed line, no interpolated path)       │  Projected close ·       │
│                                            │  5 trading sessions      │
│                                            │                          │
│                                            │  Confidence       82%    │
│                                            │  ████████░░              │
│                                            │  Hit-rate, last 60       │
│                                            │  (or N/A + Backtest btn) │
│                                            │                          │
│                                            │  Technical Signal Neutral│
│                                            │  RSI/MACD/Ichimoku —     │
│                                            │  not news sentiment      │
│                                            │                          │
│                                            │  Move within normal      │
│                                            │  volatility range        │
│                                            │  HOLD                    │
│                                            │                          │
│                                            │  Technical observation   │
│                                            │  from a backtested model │
│                                            │  — not investment advice │
└──────────────────────────────────────────────────────────────────────┘
```
