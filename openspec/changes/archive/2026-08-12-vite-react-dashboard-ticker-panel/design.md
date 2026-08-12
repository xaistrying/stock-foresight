## Context

`frontend/` is currently empty — this is a from-scratch build, not a
migration. The backend (M1-M4) exposes exactly two endpoints today:
`POST /tickers/{ticker}/load` and `GET /tickers/{ticker}/prediction`
(latest-row only, no history). Neither serves what a dashboard needs to
populate a ticker picker or draw a chart, so this change adds two small
read endpoints alongside the frontend build.

The model (`docs/MODEL_CARD.md`) was trained and backtested on exactly 9
tickers (`TRAINING_TICKERS` in `backend/app/ml/training.py`): TCB, VIB,
VHM, VND, MWG, HPG, MSN, VNM, SAB. Nothing at the API layer currently
stops a client from requesting a prediction for a ticker outside that
set — `GET /tickers/{ticker}/prediction` will happily serve a
`predicted_log_return` for any loaded ticker, validated or not.

**Scope note (2026-08-11):** an `/opsx:explore` session, prompted by a UI
reference screenshot, revised this change to absorb the original M6
scope (Confidence, Sentiment, Advice, disclaimer) rather than deferring
it behind a placeholder — see `docs/M5_DASHBOARD_EXPLORE_NOTES.md` for
the full discussion. The decisions below reflect that session; several
superseded decisions are marked as such rather than deleted, so the
reasoning trail stays legible.

## Goals / Non-Goals

**Goals:**
- Ship a working dashboard: ticker panel (9 fixed chips + search), chart
  panel, prediction display, and the real AI insight panel (Confidence,
  Sentiment, Advice, disclaimer) — not a placeholder.
- Add the minimum backend surface the dashboard needs (`GET /tickers`,
  `GET /tickers/{ticker}/history`, plus the AI-insight and
  single-ticker-backtest endpoints) without touching the existing
  ingestion or prediction endpoints.
- Let search resolve and load any real ticker, not only the 9, while
  keeping Confidence honest about which tickers it's actually validated
  for (see Decision 3, revised).

**Non-Goals:**
- No indicator overlay (Ichimoku/RSI/MACD/etc.) on the chart in v1 —
  `near_gap` rows would render misleading indicator lines with no visual
  distinction from clean rows, and building that distinction is deferred.
  (The chart's single predicted point, Decision 8, is not an indicator
  overlay and is in scope.)
- No historical predicted-vs-actual track-record view — live predictions
  aren't logged in a form that supports a track record yet; that's new
  infrastructure, not this change's job. (Distinct from the chart's
  single-point forecast marker, which is in scope.)
- No automatic or scheduled backtesting for searched-in tickers — only
  the explicit, user-triggered single-ticker backtest (Decision 6). No
  retrain-and-promote / champion-challenger mechanism for the served
  model itself — that's a separate future change (likely M7-adjacent),
  and deliberately kept off this dashboard entirely, including as a
  placeholder (see `docs/M5_DASHBOARD_EXPLORE_NOTES.md`).
- No chart zoom/range controls or configurable window size — the
  750-session window is fixed (widened from the original 300 post-ship,
  see Decision 2).
- No user-adjustable prediction horizon, advice-style control, or
  disclaimer-visibility toggle — the reference screenshot's top control
  bar (`horizonDays`, `adviceStyle`, `showDisclaimer`) is dropped
  entirely, not relocated (Decision 9).

## Decisions

### Decision 1: `GET /tickers` sources from `TRAINING_TICKERS`, not a new list
The endpoint imports `TRAINING_TICKERS` from `backend/app/ml/training.py`
as its ticker set and left-joins the `tickers` table for status
(`loaded`, `features_computed`, `last_loaded_at`) per ticker. No second
copy of the 9-ticker list is created anywhere in the codebase — training
code remains the single source of truth.

Alternative considered: duplicate the list as a config constant in the
API layer. Rejected — the two lists would drift silently if
`TRAINING_TICKERS` ever changes (e.g. a future retrain adds a 10th
ticker), and nothing would catch the mismatch since they serve different
layers of the same app.

### Decision 2: `GET /tickers/{ticker}/history` is OHLCV-only, fixed 750-session window
Returns `{ticker, rows: [{date, open, high, low, close, volume}, ...]}`
for the most recent 750 sessions (~3 years) in `ohlcv`, no `near_gap`
field, no indicator columns. Window size is a fixed backend constant, not
a query parameter.

Alternative considered: a `?sessions=` query param with a default and
max clamp. Rejected for v1 — nothing in the current UI plan (no zoom/pan
control) would use a variable window, so the param would be unused
surface area. Can be added later without a breaking change (adding an
optional param is additive).

Alternative considered: include `near_gap` per row so the chart could
visually mark gaps. Rejected for v1 — deferred along with the indicator
overlay decision above; scope stays OHLCV-only end to end for this
endpoint's first version.

**Revised (post-ship, 2026-08-12)**: shipped at 300, then widened to 750
per the Risks section's own anticipated follow-up ("revisit after the
dashboard ships and real usage is visible"). 750 sessions (~3 years) was
chosen over the full ~2000-row history: `lightweight-charts` and the
`/history` query handle either size without a measurable performance
difference (payload is a few hundred KB at most; the query is a single
indexed `ORDER BY date DESC LIMIT n`) — the real constraint is
*readability* without pan/zoom controls, which this change still doesn't
add. 750 was picked as enough added context to be useful without candles
becoming illegibly thin at the dashboard's current fixed chart width.

### Decision 3 (REVISED 2026-08-11): Prediction serves any loaded ticker; Confidence alone stays scoped to `TRAINING_TICKERS`
**Supersedes the original Decision 3** ("prediction display restricted
to `TRAINING_TICKERS`; no free-text entry"), which is kept below for the
reasoning trail, not because it's still in effect.

The ticker panel shows the 9 `TRAINING_TICKERS` chips always, **plus** a
search box that resolves and loads any real ticker via the existing
`POST /tickers/{ticker}/load` (Decision 4's `status` field distinguishes
the real failure modes, so the UI doesn't need to special-case search's
error handling separately). A searched ticker that loads successfully
joins the selectable list and gets a real prediction, chart, and
Sentiment/Advice — all computed the same way regardless of ticker
origin, since none of those three depend on training-set membership
(the model has no ticker-identity feature at all — see
`xgboost-training-pipeline`'s design.md Decision 3 — and Sentiment/Advice
read live from the ticker's own price history).

**Confidence is the one exception**, and stays scoped: `Rule 4`'s
definition is a backtested hit-rate, and `compute_rolling_hit_rate`
(`backend/app/ml/backtest.py`) can only return a real value for a ticker
with rows in `backtest_predictions` — a table only the offline M3
training/backtest job populates, only for the 9. For any other ticker,
Confidence shows an explicit `N/A` (the function's actual `None` return,
not a fabricated number) with a **"Backtest this ticker"** action
(Decision 6) that can make a real value exist.

This still implements **Rule 6** (never frame output as investment
advice), just via a different mechanism than the original decision: the
risk wasn't "a prediction exists for an unvalidated ticker" (the model
is a plain forward pass over OHLCV-derived features regardless of
ticker identity — nothing about computing `predicted_log_return` for a
new ticker is technically unsound), it was "a confidence-looking number
is shown with no real basis." Fixing that directly (honest `N/A`) is a
more accurate mitigation than withholding the whole prediction, and it
stops blocking a real, asked-for product capability (loading and
checking any ticker) to solve a narrower problem (Confidence's basis)
that has its own fix.

**Original Decision 3 (superseded), kept for the record:** "The ticker
panel only ever renders the 9 tickers from `GET /tickers` — there is no
free-text ticker entry in the UI. This is a *display-layer* restriction:
`POST /tickers/{ticker}/load` and `GET /tickers/{ticker}/prediction` are
unchanged and remain technically callable for any ticker string. The
frontend simply never constructs a request for a ticker outside the
fixed set. [...] Alternative considered: free-text ticker input, calling
`/load` on submit. Rejected for two independent reasons: (a) `/load` is
a synchronous, potentially rate-limited live `vnstock` call — the UI
would stall for an unbounded time on every new ticker; (b) even if that
were solved, it reopens the Rule 6 gap by letting a user drive the
prediction display to an unvalidated ticker." Reason (a) is addressed by
Decision 5 below (loading state, not a blocking stall); reason (b) is
addressed by the Confidence-scoping mechanism above rather than by
blocking the request.

### Decision 4: `/load` response gains an explicit `status` field
Today `load_ticker` returns `rows_loaded: 0` for two distinct causes — a
caught `RateLimitError`, or a fetch that succeeds but returns an empty
result (invalid ticker symbol, delisted ticker, or a ticker vnstock
genuinely has no data for) — and the only way to tell them apart is
inferring from which other fields (`available_since`,
`possibly_truncated_by_tier`) are `None`. The ticker panel's
load-failure UI (tasks.md 4.4) needs to show a different message for
"rate-limited, retry later" versus "no data for this symbol" — a
distinction that already exists in `load_ticker`'s control flow but
isn't named in its return value.

This change adds `status: "ok" | "rate_limited" | "no_data"` to the
response, set explicitly at each return point in `load_ticker`. This is
a modification to the existing `ticker-data-ingestion` capability, not a
new one — see the `ticker-data-ingestion` delta spec in this change.

Alternative considered: leave the response as-is and have the frontend
show one generic "load failed, try again" message for any non-success
outcome. Rejected — it throws away signal `load_ticker` already computes
internally (the two failure branches are already separate code paths)
for no implementation savings; adding the field is a small, mechanical
change (one field, three values, one function, one call site) versus a
UI that gives users a less actionable message than the backend could
easily support.

**Note**: this decision originally assumed a fetch that succeeds but
returns zero rows would be the source of `no_data`. Testing (Decision 7)
found that's not what actually happens — a malformed symbol raises
`ValueError` directly (mapped to `"invalid_symbol"`), while a
well-formed ticker with genuinely no data raises `tenacity.RetryError`
wrapping a different `ValueError`, unwrapped via
`e.last_attempt.exception()` and mapped to `"no_data"`. The final enum
is `"ok" | "rate_limited" | "invalid_symbol" | "no_data"` — four values,
not the originally-assumed three; `no_data` survived as a name but its
actual trigger (a wrapped `RetryError`, not a bare empty result) wasn't
the one first assumed.

### Decision 5: React Query for data fetching
Chosen over SWR and over hand-rolled `useEffect` fetching. The dashboard
needs: (a) multiple distinct response shapes per endpoint (prediction's
ok/near_gap variants, load's success/rate-limited variants), and (b) a
write-then-invalidate flow — `POST /load` succeeding must invalidate and
refetch both `/prediction` and `/history` for that ticker. React Query's
mutation + query-invalidation primitives cover this directly; SWR has
weaker mutation support, and hand-rolling both cache invalidation and
loading/error states with `useEffect` is strictly more code for the same
behavior, not less.

### Decision 6: Charting library — deferred to task-time, not decided here
The proposal names "a charting library" as a new dependency but does not
pin one. Candidates: lightweight-charts (TradingView's, candlestick-native,
no React wrapper), Recharts (React-idiomatic, no candlestick primitive
out of the box), visx (low-level, more build effort). This design defers
the final choice to implementation, constrained to: must render OHLC
candles from the `/history` shape above, must not require a paid license,
must have current (non-abandoned) maintenance.

### Decision 7: `/load`'s response gains a `status` field; malformed
symbols and well-formed-but-empty tickers are now both caught, not left
to crash

Discovered while writing task 4.4 (surfacing `/load`'s failure states in
the ticker panel) — `rows_loaded: 0` alone couldn't distinguish a
rate-limited retry from a genuinely bad ticker string, and testing
found a malformed symbol wasn't even caught at all; it crashed
`load_ticker` with an unhandled `ValueError`.

Two confirmed message strings from `vnstock`'s symbol validation
("Invalid symbol. Your symbol format is not recognized!" and "Symbol
must be between 3 and 12 characters long.") are matched via a shared
`_classify_load_error` helper, returning `"invalid_symbol"` for either.
`RateLimitError`'s existing branch is unchanged apart from adding the
same `status` field for shape consistency.

**Also fixed, once confirmed**: a well-formed ticker with no real data
raises `tenacity.RetryError`, not a plain `ValueError` — confirmed live
that `e.last_attempt.exception()` returns the real underlying
`ValueError("Không tìm thấy dữ liệu...")`, and that this case is never
wrapped for the malformed-symbol case (that one stays a bare
`ValueError`), so the two remain distinguishable after unwrapping.
`load_ticker` now catches `(ValueError, RetryError)` together, unwraps
`RetryError` via `.last_attempt.exception()` before classifying, and
`_classify_load_error` gained a third match returning `"no_data"`. This
was deliberately *not* done speculatively in the same pass as the
`invalid_symbol` fix — the message string and the unwrap API were each
verified live first (matching this project's standard of testing before
writing message-based matching logic), then implemented once confirmed.

**Alternative considered**: unwrap and match on `RetryError`
speculatively without a confirmed message string, in the same pass as
the `invalid_symbol` fix. Rejected initially for that reason — implemented
in a follow-up pass once the message and the `.last_attempt.exception()`
API were both confirmed live, not guessed at.

### Decision 8: Chart shows the single predicted point, connected by one straight line — never an interpolated path
The model produces exactly one scalar per prediction
(`predicted_log_return`, a single point 5 sessions ahead), never a
day-by-day trajectory. The chart renders that point (converted to price
via the percentage, Rule 2) and connects it to today's close with one
straight dashed line — no smoothing, no fabricated intermediate points
between today and t+5.

This narrows, rather than reintroduces a violation of, the instinct
behind the earlier "no predicted-vs-actual series" framing: that
framing was written when M5 had no prediction in scope at all, so a
blanket ban was the only safe rule. Now that a prediction is genuinely
on-screen (Decision 3, revised), the requirement is precise about what
would be dishonest — an interpolated curve implying confidence in a
path the model never computed — rather than banning every rendering of
the one real number the model does produce. This is a **Rule 6**
mitigation: a smooth forecast curve (as in the reference screenshot)
visually overclaims a day-by-day trajectory that doesn't exist.

**Alternative considered**: no chart overlay at all, prediction stays
text-only in the AI insight panel. Rejected — discussed directly with
the user; a single honest point communicates "here's the one number we
predicted" without the framing risk of a fabricated path, and is
strictly more informative than omitting it.

**Alternative considered**: single point with no connecting line at all
(visually separated from the historical line). Rejected in favor of one
straight connecting line — the line still communicates direction/magnitude
at a glance without implying an interpolated path, which was judged
worth the small addition over a fully disconnected marker.

### Decision 9: Top control bar (horizonDays / adviceStyle / showDisclaimer) dropped entirely, not relocated
The reference screenshot's top bar exposed three controls, each
individually reconsidered and rejected rather than carried over
unreviewed:

- **`horizonDays` slider** (shown at 7): implies the prediction horizon
  is user-adjustable. Rejected — **Rule 1** fixes the target at exactly
  5 trading sessions ahead; this is baked into the trained model, not a
  runtime parameter, and a slider suggesting otherwise is a Rule 1
  conflict risk, not just a UX choice. The "5 trading sessions" fact is
  static label text near the Prediction display instead (see
  `dashboard-ui` spec).
- **`showDisclaimer` toggle**: makes the disclaimer optional. Rejected —
  **Rule 6** requires the disclaimer to appear unconditionally anywhere
  Advice/Confidence/Sentiment is shown; a toggle to hide it directly
  contradicts that. The disclaimer always renders with the AI insight
  panel.
- **`adviceStyle` dropdown**: dropped along with the rest of the bar,
  not evaluated as a standalone case.

The general lesson, worth stating for future reference-screenshot reuse:
a mockup's control affordances can smuggle in a domain-rule violation
just by existing as a plausible-looking UI convention — each control
needs to be checked against what it implies is variable/optional, not
evaluated only on how it looks.

### Decision 10: Ticker chip/list freshness states — Loading / Fresh / Stale
Each selectable ticker (chip or searched-in) shows one of three states:
**Loading** (transient — load + auto-predict, Decision 11, in flight),
**Fresh** (the stored prediction's `as_of` matches the latest available
trading session), or **Stale** (a newer session's OHLCV/features exist
than the one the stored prediction's `as_of` used). Staleness is defined
against actual data availability, not a fixed calendar age (e.g. "3+
days old") — a ticker isn't stale just because time passed if there's
genuinely no newer session to refresh against (e.g. over a holiday gap).
This reuses the existing `as_of`/`near_gap` fields already in the
`/prediction` contract rather than inventing a new timer.

### Decision 11: Auto-predict on load
Loading a ticker (chip click or search-triggered load) immediately
triggers `GET /tickers/{ticker}/prediction` too, with no separate user
action — extending the original "loading refetches prediction"
requirement (still true, see the `dashboard-ui` spec) to also cover
search-triggered loads, not only re-loads of an already-known ticker.

This was checked against a real concern raised during design: does
predicting on a freshly-searched ticker retrain or otherwise change the
served model? Confirmed no — `app.state.model` is a frozen `xgb.Booster`
loaded once at FastAPI startup (`main.py`); `GET /prediction` only ever
calls `model.predict(...)`, a forward pass with no weight update, no
retraining, and no persistence back to `pooled_xgb_model.json`. A
retrain-and-promote mechanism (with a champion/challenger comparison) is
real future scope, but belongs to a separate change that touches the
training pipeline — not something auto-predict-on-load needs to gate on
or wait for (see Non-Goals and `docs/M5_DASHBOARD_EXPLORE_NOTES.md`).

### Decision 12: Single-ticker backtest — gated on a minimum row count, not a multi-year span
The "Backtest this ticker" button (Decision 3, revised) runs a
scoped-down variant of `run_walk_forward_backtest`
(`backend/app/ml/backtest.py`) for one ticker outside `TRAINING_TICKERS`,
persisting results into the same `backtest_predictions` table the M3
training job writes, so `compute_rolling_hit_rate` has real data to read
afterward.

**Gate**: enabled once the ticker has at least N rows passing the same
`near_gap = 0 AND target IS NOT NULL` filter `training.py`'s
`filter_clean_labeled` already uses — not a requirement to span a
multi-year window comparable to the 9's ~8 years of history. Exact N is
an implementation-time decision (task-level, not fixed here) — pick the
smallest value that reliably produces non-empty walk-forward folds
(`compute_fold_boundaries` needs `len(dates) >= n_folds`, and
`run_walk_forward_backtest` already skips folds where
`len(train_df) == 0 or len(test_df) == 0`), verified empirically rather
than guessed. Below the threshold, the button is hidden/disabled with
explanatory text instead of a clickable dead end.

**In-progress state**: the button shows an inline spinner and disables
itself while the backtest runs (real compute — seconds to tens of
seconds, unlike the rest of this dashboard's near-instant reads); the
rest of the AI insight panel (Prediction, Sentiment, Advice) stays fully
interactive throughout. On completion, Confidence transitions to the
same display used for the 9 — no distinct "just backtested" visual
state.

**Alternative considered**: gate on spanning a comparable multi-year
window to the 9, for closer parity with their backtest rigor. Rejected —
discussed directly with the user; this would make the button
unreachable for most newly-searched tickers for a long time, defeating
its purpose. A lower, empirically-chosen row-count bar was preferred.

### Decision 13: Sentiment relabeled "Technical Signal"; Advice uses directional wording, not BUY/SELL
Two copy-level decisions enforcing Rules 5 and 6 respectively, drafted
in full in `docs/M5_DASHBOARD_EXPLORE_NOTES.md`'s copy contract:

- **Sentiment** is labeled "Technical Signal" (not "Market Sentiment"),
  always paired inline with the computing indicators ("Based on RSI,
  MACD, Ichimoku position — not news or market sentiment") rather than
  behind a hover-only tooltip. Directly implements **Rule 5**'s
  labeling requirement — the label alone should not invite the reading
  the rule prohibits.
- **Advice** uses `HOLD` / `Signal: up` / `Signal: down` rather than the
  traditional `HOLD`/`BUY`/`SELL` trio. `BUY`/`SELL` are literal
  transaction verbs and read as an instruction to act; directional
  wording stays in observation-mode, reinforcing **Rule 6**. Each
  verdict is preceded by the reasoning that produced it (e.g. "Move
  exceeds typical volatility to the upside") so the label reads as a
  conclusion from a stated technical criterion, not a standalone
  command.

**Alternative considered**: keep the familiar BUY/SELL/HOLD trio,
relying on the disclaimer and surrounding framing to prevent
misreading. Rejected — discussed directly with the user; avoiding
transaction verbs outright was preferred over relying on adjacent copy
to do that work.

### Decision 14 (added 2026-08-12): Dashboard uses the full viewport width, not a centered fixed-width column
`App.css`'s `.app-shell` originally capped the dashboard at `max-width:
72rem` and centered it (`margin: 0 auto`) — an unreviewed carryover from
typical content-page layout, not a deliberate choice for a data-dense
financial dashboard. Revised: the dashboard now fills the available
viewport width, so the chart panel and AI insight panel get more room on
wide screens rather than sitting in a fixed ~1152px column with unused
space on either side.

**Alternative considered**: keep a max-width but raise it (e.g. 96rem)
instead of removing it entirely. Rejected — discussed directly with the
user; the request was explicitly for the dashboard to use "the whole
screen," not a wider-but-still-capped column.

### Decision 15 (added 2026-08-12): T+5 predicted point uses weekday-stepping + whitespace points, not a flat +7-day offset
The chart's single predicted point (Decision 8) was originally placed at
`as_of + 7 calendar days` — a rough weekend-absorbing approximation. Real
usage found this rendered the point immediately adjacent to the last
candle, reading as "tomorrow" rather than "5 sessions out": lightweight-
charts' time scale only reserves x-axis width for timestamps it has
actually been given data for, so with only 2 data points (last close,
target date) it collapsed the 4 intervening trading sessions regardless
of what date string was used.

Fixed two ways: (a) `approximateTargetDate` now steps forward 5 WEEKDAYS
(skipping Sat/Sun) from `as_of` instead of a flat 7 calendar days — still
an approximation (it doesn't know Vietnamese market holidays) but closer
to 5 real trading sessions; (b) the chart also passes the 4 intermediate
weekday dates as lightweight-charts "whitespace" points (`{time}`, no
`value`) — these reserve axis space without adding a plotted value or a
connecting line segment, so the model still gets credit for exactly one
predicted point (Decision 8's constraint is unchanged), only its
x-position on the axis is now honest.

**Alternative considered**: ask the backend for a real t+5 target date
instead of approximating client-side. Rejected for this pass — bigger
scope (API change), and the weekday-stepping approximation was judged
close enough for a visual placement heuristic that doesn't affect the
predicted value itself (Rule 2's conversion is exact regardless).

### Decision 16 (added 2026-08-12): Ticker freshness shown as a color dot + legend, not inline text
Each chip originally showed the literal word "Fresh"/"Stale"/"Loading"
next to the ticker symbol (Decision 10). Revised to a small color dot
(green/amber/spinning-gray) instead, with a legend row below the chip
list spelling out the color mapping — the words took up horizontal space
disproportionate to the information conveyed, once every one of the 9
chips carried one.

A bare color dot alone would fail WCAG's color-not-only requirement
(colorblind users, screen readers can't perceive color) — the dot
carries an `aria-label`/`title` with the same wording the text used
("Fresh — up to date with the latest trading session", etc.), so the
information is still reachable by hover or screen reader, not lost.
Load-failure messages ("Not loaded", rate-limited, etc.) are unaffected
— those carry information a dot can't express and remain visible text.

**Alternative considered**: a dot with a 1-letter glyph inside it
(F/S/L) instead of a separate legend, for accessibility without hovering.
Rejected — discussed directly with the user; the dot+legend combination
was preferred.

### Decision 17 (added 2026-08-12): Chart reset-zoom control, resetting both axes independently
Once a user manually pans/zooms the chart (drag, scroll-wheel, pinch —
lightweight-charts' native gestures, not something this dashboard adds),
the time scale and price scale each permanently leave auto-fit mode and
won't self-correct on new data. There was no way back to a fitted view
without reselecting the ticker. Added a small icon button (top-right of
the chart canvas) that restores both axes: `timeScale().fitContent()`
(or the default-window equivalent, Decision 18) for the x-axis, and
`priceScale().setAutoScale(true)` for the y-axis — `fitContent()` alone
only affects the time scale, so a manually-dragged price axis needed its
own explicit reset.

**Implementation note, not a design decision but worth recording**:
lightweight-charts sets `z-index: 2` on its own internal canvases (e.g.
the price-scale overlay); the reset button initially rendered correctly
but was unclickable, intercepted by that canvas despite being painted
underneath it. Fixed by giving the button `z-index: 3`. Caught by testing
the real interaction in a browser, not just inspecting the DOM/a
screenshot.

### Decision 18 (added 2026-08-12): Chart opens on the most recent ~60 sessions, not the full history
Decision 2's widened 750-session window (~3 years), combined with
`fitContent()` fitting the entire window on every ticker selection,
squeezed the recent candles — and the predicted point — into a thin
sliver at the right edge of an otherwise mostly-flat 3-year view. Revised
so opening a ticker (or clicking "Reset zoom", Decision 17) shows the
most recent 60 sessions (~3 months) via
`timeScale().setVisibleLogicalRange()`, with a small right margin so the
dashed prediction line/point isn't flush against the canvas edge. Falls
back to the old `fitContent()` behavior when a ticker has fewer than 60
sessions of history — nothing to crop. The full 750-session (or full
~8-year model) history remains reachable by scrolling/zooming out or is
unaffected respectively; only the *default* view changed.

**Alternative considered**: 20 sessions (~1 month) or 125 sessions (~6
months) as the default window. Chose 60 (~3 months) — discussed directly
with the user — as enough to read short-term trend clearly while keeping
today's close and the predicted point comfortably visible.

### Decision 19 (added 2026-08-12): Freshness dot has a fixed footprint across all states
The Loading spinner (a ring, added for Decision 16) and the resting
Fresh/Stale dot were sized differently (0.75rem vs 0.5rem) — since every
chip passes through Loading first while its freshness query is in
flight, each chip visibly grew then shrank the moment it settled. Fixed
by giving the dot a fixed 0.75rem box (`box-sizing: border-box`) across
every state; the resting dot renders as a smaller circle centered inside
that same box via `background-clip: content-box`, rather than the
element itself changing size.

## Risks / Trade-offs

- **[Risk]** *(Acted on 2026-08-12)* Fixed 300-session window was too
  short once real usage showed it — users expected more visible history
  than ~14 months. → **Resolution**: widened to 750 sessions (~3 years,
  Decision 2 revised); still a fixed backend constant, no zoom/pan added.
  Full ~8-year history remains available to the model (unrelated to this
  window — it only affects the chart, never training/backtesting), and
  the constant can be widened again the same way with no migration cost.
- **[Risk]** `TRAINING_TICKERS` import creates a dependency from
  `app.api` on `app.ml.training` — a module that also does model
  training I/O. → **Mitigation**: only the list constant is imported, not
  any training function; if this coupling becomes a problem, the constant
  can be hoisted to a shared config module without changing this
  endpoint's contract.
- **[Risk]** *(Superseded)* The original risk here — "restricting the
  prediction display to 9 tickers may read as an arbitrary limitation" —
  no longer applies; prediction is no longer restricted to the 9
  (Decision 3, revised). Superseding risks below.
- **[Risk]** Confidence's explicit `N/A` for a searched-in ticker could
  itself read as a weakness or bug to a user unfamiliar with why, rather
  than an honest scope boundary. → **Mitigation**: the subtext next to
  `N/A` names the reason ("Needs more price history to backtest") and
  offers a concrete next action (the backtest button) rather than
  leaving the state unexplained.
- **[Risk]** The single-ticker backtest (Decision 12) is real compute
  triggered by a user click — a ticker with borderline-enough history to
  clear the row-count gate might still produce a low-confidence or
  noisy backtest result (few folds, small test windows) compared to the
  9's ~8-year, multi-fold validation. → **Mitigation**: accepted for v1;
  the button's existence doesn't claim parity with the 9's validation
  rigor, only that a real (if smaller-scale) backtest ran. Revisit if
  usage shows this reads as misleadingly authoritative.
- **[Risk]** Rule 6's disclaimer/framing protections (directional
  wording, unconditional disclaimer, single-point chart) exist only at
  the frontend display layer — the underlying prediction/Sentiment/
  Advice computation is callable directly at the API level without
  those framing choices attached. A direct API client bypasses them
  entirely. → **Mitigation**: accepted for v1 (no public deployment
  yet); if this API is ever exposed beyond the dashboard's own frontend,
  backend-level framing (or at least equivalent response metadata)
  becomes necessary, not optional.
- **[Risk]** *(Resolved)* The `RetryError` gap (Decision 7) meant even a
  request against one of the 9 fixed, previously-successful tickers
  could theoretically crash `/load` ungracefully, if that ticker's data
  became temporarily unavailable from vnstock. Fixed: `load_ticker` now
  catches and unwraps `RetryError` alongside `ValueError`, returning
  `status: "no_data"` instead of crashing. `docs/KNOWN_ISSUES.md`'s
  entry is closed.
- **[Trade-off]** Deferring predicted-vs-actual tracking means the
  dashboard cannot show historical prediction accuracy inline on the
  chart in M5. Accepted — building a prediction log is real new
  infrastructure and belongs in its own change, not folded into a UI
  milestone.

## Open Questions

- Charting library choice (Decision 6) — resolve during `tasks.md` /
  implementation, not blocking design sign-off.
- Exact visual treatment for near_gap / 404 / 503 prediction states, and
  for the AI insight panel overall (separate stat-tile cards vs. one
  continuous panel with dividers), is a UI design detail for
  implementation (Hallmark skill), not a spec-level decision — see
  `docs/M5_DASHBOARD_EXPLORE_NOTES.md`'s copy contract for the fixed
  wording each state should use, so the visual pass has real content to
  work from rather than inventing it.
- The single-ticker backtest's exact row-count threshold (Decision 12)
  is left for implementation to determine empirically, not fixed here.
