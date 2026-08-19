# dashboard-ui

## Purpose

TBD

## Requirements

### Requirement: Ticker panel shows the fixed set plus search for any real ticker
The dashboard's ticker panel SHALL render one selectable **entry** (a chip
for the fixed Watchlist, a list row for any other ticker) per ticker
returned by `GET /tickers` (the 9 `TRAINING_TICKERS`) plus every
successfully-loaded searched-in ticker. The 9 `TRAINING_TICKERS` SHALL
always be visible as the fixed **Watchlist**, regardless of any filter or
search input state. The panel SHALL also provide a search action that
resolves a user-entered ticker symbol; if that ticker is not yet loaded,
the search action SHALL trigger `POST /tickers/{ticker}/load` the same way
selecting an unloaded entry would, and the ticker SHALL join the
selectable searched-in list once loaded successfully. The same input MAY
also live-filter the searched-in list's visible entries as the user types,
provided this filtering never hides or otherwise affects the Watchlist.

#### Scenario: Panel renders the fixed set as chips
- **WHEN** the dashboard loads
- **THEN** the ticker panel shows one selectable chip per ticker in the
  Watchlist (the 9 tickers returned by `GET /tickers`), always visible
  regardless of search or filter state

#### Scenario: Searching an unloaded ticker triggers a load
- **WHEN** a user searches a ticker symbol that has no rows in `ohlcv`
  yet
- **THEN** the dashboard calls `POST /tickers/{ticker}/load` for that
  symbol, and the ticker becomes selectable once the load succeeds

#### Scenario: Searching an already-loaded ticker selects it directly
- **WHEN** a user searches a ticker symbol that already has data loaded
  (whether a Watchlist entry or a previously searched-in ticker)
- **THEN** the dashboard selects it directly without issuing a new
  `/load` request

#### Scenario: A searched-in ticker persists as a selectable entry
- **WHEN** a searched ticker outside `TRAINING_TICKERS` has loaded
  successfully at least once
- **THEN** it remains selectable in the ticker panel's searched-in list for
  the rest of the session, alongside the Watchlist

#### Scenario: Filter narrows the searched-in list only
- **WHEN** a user types a substring into the ticker panel's search input
  without submitting
- **THEN** the searched-in list's visible entries narrow to those whose
  symbol contains the typed substring, and the count of visible entries is
  announced to screen readers via an `aria-live` region

#### Scenario: Fixed Watchlist remains visible regardless of filter input
- **WHEN** a user types a substring into the ticker panel's search input
  that matches none of the 9 `TRAINING_TICKERS`
- **THEN** all 9 Watchlist entries remain visible and selectable; only the
  searched-in list's visible entries change

### Requirement: Predicted log return is converted to a percentage before display
Per domain Rule 2, the dashboard SHALL NOT render the raw
`predicted_log_return` value returned by `GET
/tickers/{ticker}/prediction` anywhere in the UI. It SHALL convert it to
a simple percentage (`(e^predicted_log_return - 1) * 100`) before
display. This applies identically whether the value is shown in the
Prediction display or in the chart panel's single predicted point.

#### Scenario: Prediction display shows a percentage, not a log return
- **WHEN** `GET /tickers/{ticker}/prediction` responds with `status:
  "ok"` and a `predicted_log_return` value
- **THEN** the dashboard displays a percentage derived from that value
  and does not render the raw `predicted_log_return` number anywhere on
  the page, including in tooltips or hidden/debug text

### Requirement: Prediction display distinguishes ok, near_gap, not-loaded, and failed states
The dashboard SHALL render visually distinct states for the four
outcomes of `GET /tickers/{ticker}/prediction`: `200` with `status:
"ok"`, `200` with `status: "near_gap"`, `404`, and `5xx`. It SHALL NOT
render the same UI treatment (e.g. a blank or generic loading state) for
more than one of these outcomes. This applies identically for any
ticker, whether one of the 9 `TRAINING_TICKERS` or a searched-in ticker.

#### Scenario: Ok state shows the converted prediction
- **WHEN** the prediction response has `status: "ok"`
- **THEN** the dashboard displays the converted percentage, the `as_of`
  date, and static label text naming the fixed 5-trading-session horizon
  (Rule 1) — never a control implying the horizon is adjustable

#### Scenario: near_gap state is distinguishable from ok
- **WHEN** the prediction response has `status: "near_gap"`
- **THEN** the dashboard shows a message indicating a data gap prevents a
  current prediction, and does not display a percentage figure

#### Scenario: Not-loaded state is distinguishable from near_gap and failure
- **WHEN** the prediction request responds `404`
- **THEN** the dashboard shows a message indicating the ticker has not
  been loaded yet, distinct from the near_gap and failure messages

#### Scenario: Feature-computation-failure state is distinguishable from the others
- **WHEN** the prediction request responds with a `5xx` status
- **THEN** the dashboard shows a message indicating feature computation
  failed for this ticker, distinct from the near_gap and not-loaded
  messages

### Requirement: Unselected-ticker state shows explicit placeholders, not an empty message

When no ticker is selected, the Prediction display and AI insight panel
SHALL each render their full populated layout (all labels and value
slots) with an explicit non-fabricated placeholder value (`N/A`) in
place of every value that depends on a selected ticker, rather than
showing a "select a ticker" message or omitting either panel. This
placeholder SHALL render at the same font-size, font-family, and weight
as a real populated value, distinguished from one only by a muted color
— not by a smaller or less visually substantial presentation — so it
reads as a legible, deliberate "no value" state rather than a barely-
visible mark. The AI insight panel's disclaimer SHALL render
unconditionally in this state, consistent with its unconditional
visibility whenever a ticker is selected. This requirement applies only
to the no-ticker-selected case; each component's other states (loading,
not-loaded, feature-computation failure, populated) are unaffected and
continue to render independently per their own existing behavior.

#### Scenario: No ticker selected shows N/A placeholders in both panels

- **WHEN** the dashboard loads or a ticker is deselected, and no ticker is
  currently selected
- **THEN** the Prediction display renders its title and an `N/A`
  placeholder, styled at the same font-size/family/weight as a real
  percentage, in place of the percentage value, and the AI insight
  panel renders Confidence, Technical Signal, and Advice labels each with
  an `N/A` placeholder value styled at the same font-size/family/weight
  as a real value, plus its disclaimer

#### Scenario: Prediction display keeps the same three-line shape whether or not a ticker is selected

- **WHEN** no ticker is selected
- **THEN** the Prediction display renders all three of its populated-state
  lines — the `N/A` percentage placeholder, an "As of —" placeholder in
  place of the real date, and the unconditional "Fixed horizon: 5 trading
  sessions" line (unchanged, since the horizon is fixed regardless of
  ticker selection) — so selecting a ticker for the first time does not
  grow the card by adding lines that were previously absent

#### Scenario: N/A placeholders are visually distinct from a real N/A value by color, not by wording

- **WHEN** the no-ticker `N/A` placeholder is shown
- **THEN** it is styled in a distinctly muted color from a real computed
  value or a real N/A result (e.g. Confidence's own no-backtest-history
  N/A state), so it cannot be mistaken for actual Confidence/Sentiment/
  Advice/Prediction data — consistent with rules 4/5/6's requirement that
  these disclosures reflect real computed data or an explicit N/A, never
  a value that could pass as real

#### Scenario: Selecting a ticker replaces N/A placeholders with per-component states

- **WHEN** a ticker is selected after the N/A-placeholder state was
  showing
- **THEN** the N/A placeholders are removed, and the Prediction display
  and AI insight panel each independently render their own state
  (loading, not-loaded, failure, or populated) for the selected ticker,
  as already specified elsewhere in this capability

### Requirement: Chart panel renders OHLCV plus the single predicted point, no derived-indicator overlay

The chart panel SHALL render candles from `GET /tickers/{ticker}/history`,
and MAY additionally render that same response's volume field as a
histogram — both are raw OHLCV data already present in the response, not a
derived indicator. The chart SHALL NOT render any derived technical
indicator overlay (Ichimoku, RSI, MACD, Bollinger, ATR, OBV). The chart MAY
additionally render exactly one predicted point at t+5 sessions, derived
from `predicted_log_return` per the percentage-conversion requirement
above, connected to the most recent historical close by a single straight
line. The chart SHALL NOT render any interpolated, smoothed, or otherwise
fabricated point between the most recent historical close and the t+5
predicted point.

This requirement's substantive constraint is unchanged — no derived
technical indicator may be drawn. Only its wording is clarified to state
explicitly that volume (already named as part of OHLCV) is not itself a
prohibited indicator, since it is raw fetched data rather than something
computed from the price series.

#### Scenario: Chart shows candles for the selected ticker
- **WHEN** a ticker is selected in the ticker panel
- **THEN** the chart panel renders OHLC candles from that ticker's `GET
  /tickers/{ticker}/history` response

#### Scenario: No derived indicator lines are drawn

- **WHEN** the chart panel renders
- **THEN** no derived technical indicator overlay (Ichimoku, RSI, MACD,
  Bollinger, ATR, OBV) is drawn on or alongside the candles

#### Scenario: Volume histogram is not a prohibited indicator overlay

- **WHEN** the chart panel renders a volume histogram below the
  candlesticks
- **THEN** this does not violate the no-derived-indicator-overlay
  constraint, since volume is raw OHLCV data already named in this
  requirement, not a derived technical indicator

#### Scenario: Predicted point is a single point, not a path
- **WHEN** the chart panel renders a predicted point for a ticker with
  `status: "ok"` from `GET /tickers/{ticker}/prediction`
- **THEN** exactly one additional point appears at the t+5 position,
  joined to the most recent historical close by one straight line, with
  no intermediate point rendered between them

#### Scenario: No predicted point when prediction is unavailable
- **WHEN** the prediction response has `status: "near_gap"`, or the
  request responds `404` or `5xx`
- **THEN** the chart panel renders candles only, with no predicted point

### Requirement: Chart panel shows an OHLCV legend for the hovered or most recent session
The chart panel SHALL display a fixed-position legend showing that
session's Open, High, Low, Close, and Volume values. The legend SHALL
reflect the session currently under the crosshair; when the crosshair is
not positioned over the chart, the legend SHALL show the most recent
(rightmost) session's values instead of appearing blank. The legend's
five values SHALL render in the same positive or negative color the
chart already uses for that session's candle and volume bar (Close ≥
Open → positive, else negative); the legend SHALL NOT introduce a
different up/down comparison or a new color.

#### Scenario: Legend defaults to the most recent session
- **WHEN** the chart panel renders for a selected ticker and the
  crosshair is not positioned over the chart
- **THEN** the legend shows the most recent session's Open, High, Low,
  Close, and Volume values

#### Scenario: Legend updates to the hovered session
- **WHEN** a user positions the crosshair over a specific candle
- **THEN** the legend shows that candle's Open, High, Low, Close, and
  Volume values, replacing whatever it showed before

#### Scenario: Legend values are colored to match the session's direction
- **WHEN** the legend displays a session whose Close is greater than or
  equal to its Open
- **THEN** the legend's O/H/L/C/Volume values render in the same
  positive color used for that session's candle and volume bar

#### Scenario: Legend reflects only real historical data
- **WHEN** the chart panel renders a predicted point (per the existing
  "Chart panel renders OHLCV plus the single predicted point" requirement)
- **THEN** the legend never displays the predicted point's value as if it
  were a real session's OHLCV

### Requirement: AI insight panel computes and displays Confidence, Sentiment, and Advice
The dashboard SHALL display an AI insight panel with three elements —
Confidence, Sentiment ("Technical Signal"), and Advice — for the
selected ticker, alongside an unconditional disclaimer (see the
Disclaimer requirement below). This panel SHALL NOT be a placeholder;
it SHALL compute and render real values per the requirements below for
any loaded ticker.

#### Scenario: AI insight panel renders for any loaded ticker
- **WHEN** a ticker (one of the 9 `TRAINING_TICKERS`, or a searched-in
  ticker) has a prediction with `status: "ok"`
- **THEN** the dashboard displays Confidence, Sentiment, and Advice for
  that ticker — not a "coming soon" or not-yet-available placeholder

### Requirement: Confidence reflects backtested hit-rate, or explicit N/A for unvalidated tickers
Per domain Rule 4, Confidence SHALL display the ticker's backtested
hit-rate (`compute_rolling_hit_rate`) when that value exists. When it
does not exist (the function returns `None` — no persisted
`backtest_predictions` rows for that ticker), the dashboard SHALL
display an explicit `N/A` state with text naming the reason, and SHALL
NOT display a fabricated, estimated, or substituted percentage in its
place.

#### Scenario: Trained ticker shows a real hit-rate
- **WHEN** the selected ticker is one of the 9 `TRAINING_TICKERS`
- **THEN** Confidence displays `compute_rolling_hit_rate`'s value as a
  percentage, with subtext naming it as a hit-rate over the ticker's
  most recent backtested predictions

#### Scenario: Searched-in ticker with no backtest history shows N/A
- **WHEN** the selected ticker has no rows in `backtest_predictions`
- **THEN** Confidence displays `N/A` with text explaining that more
  price history or a backtest run is needed, and no numeric percentage
  is shown

#### Scenario: N/A never substitutes a pooled or global value
- **WHEN** Confidence is in the `N/A` state for a ticker
- **THEN** the dashboard does not display the model's pooled/overall
  backtested accuracy, or any other ticker's hit-rate, as a stand-in
  value

### Requirement: "Backtest this ticker" action populates Confidence for unvalidated tickers
When Confidence is in the `N/A` state and the selected ticker has at
least the minimum number of clean, labeled feature rows needed to form
a walk-forward fold, the dashboard SHALL offer a "Backtest this ticker"
action. Selecting it SHALL trigger a single-ticker walk-forward backtest
whose results persist so a subsequent Confidence read reflects a real
hit-rate. While the backtest runs, the action SHALL show a disabled,
loading state without blocking the rest of the AI insight panel.

#### Scenario: Action is offered once there is enough history
- **WHEN** the selected ticker's `N/A` Confidence state has at least the
  minimum clean+labeled row count needed to form a walk-forward fold
- **THEN** the dashboard shows an enabled "Backtest this ticker" action

#### Scenario: Action is hidden or disabled below the history threshold
- **WHEN** the selected ticker has fewer clean+labeled rows than the
  minimum needed to form a walk-forward fold
- **THEN** the "Backtest this ticker" action is hidden or disabled, with
  text explaining more price history is needed

#### Scenario: Running the backtest does not block the rest of the panel
- **WHEN** a user triggers the "Backtest this ticker" action
- **THEN** the action shows a disabled, loading state until the backtest
  completes, while Prediction, Sentiment, and Advice remain interactive
  and unaffected

#### Scenario: Completed backtest transitions Confidence to a real value
- **WHEN** a single-ticker backtest completes successfully
- **THEN** Confidence subsequently displays that ticker's real
  `compute_rolling_hit_rate` value, identically to a `TRAINING_TICKERS`
  ticker, with no distinct "just backtested" visual treatment

### Requirement: Sentiment is labeled as a technical proxy, not real sentiment
Per domain Rule 5, the dashboard SHALL label this element "Technical
Signal" (not "Market Sentiment" or any wording implying real news/NLP
sentiment) and SHALL always display, inline and without requiring a
hover or additional interaction, the technical indicators it is
computed from (RSI, MACD, Ichimoku position). This applies identically
for any loaded ticker.

#### Scenario: Label and basis are both visible without interaction
- **WHEN** the AI insight panel renders Sentiment for any loaded ticker
- **THEN** the element is labeled "Technical Signal", and text naming
  RSI, MACD, and Ichimoku position as the basis is visible without a
  hover, click, or other interaction

#### Scenario: Sentiment computes identically regardless of ticker origin
- **WHEN** the selected ticker is a searched-in ticker outside
  `TRAINING_TICKERS`
- **THEN** Sentiment is computed and displayed the same way as for one
  of the 9 fixed tickers — Sentiment has no training-set dependency

#### Scenario: Basis text renders unconditionally, even with no ticker selected or a ticker's insight still loading
- **WHEN** no ticker is selected, or a selected ticker's insight is in
  flight
- **THEN** the RSI/MACD/Ichimoku-position basis text is still visible —
  it does not wait for a ticker to be selected or its data to load, since
  this basis is a fixed list that never varies per ticker (unlike
  Confidence's basis or Advice's reasoning, which do depend on
  per-ticker data and correctly remain placeholders until known)

### Requirement: Advice uses directional wording, never a transaction verb
Per domain Rules 3 and 6, Advice SHALL be computed from `0.5 x
rolling_std(returns, 60 sessions)` (volatility-relative, not a fixed
threshold) and SHALL be worded directionally (e.g. "HOLD" / "Signal:
up" / "Signal: down"). The dashboard SHALL NOT use "BUY" or "SELL" or
any other literal transaction-instruction wording. Each verdict SHALL be
preceded by text naming the technical criterion that produced it.

#### Scenario: Move within threshold shows HOLD with reasoning
- **WHEN** the ticker's predicted move is within `0.5 x
  rolling_std(returns, 60 sessions)`
- **THEN** the dashboard shows text stating the move is within normal
  volatility range, followed by "HOLD"

#### Scenario: Move above threshold shows directional wording, not BUY/SELL
- **WHEN** the ticker's predicted move exceeds `0.5 x
  rolling_std(returns, 60 sessions)` in either direction
- **THEN** the dashboard shows text naming which direction the move
  exceeds typical volatility, followed by "Signal: up" or "Signal: down"
  as appropriate — never "BUY" or "SELL"

### Requirement: Disclaimer is always visible, with no visibility control
Per domain Rule 6, the dashboard SHALL display a disclaimer stating that
the AI insight panel's output is a technical observation from a
backtested model, not investment advice, whenever Confidence, Sentiment,
or Advice is displayed. The dashboard SHALL NOT provide any control that
hides, collapses, or otherwise makes this disclaimer's visibility
optional.

#### Scenario: Disclaimer renders alongside the AI insight panel
- **WHEN** the AI insight panel displays Confidence, Sentiment, or
  Advice for any ticker
- **THEN** the disclaimer text is visible on the same view, with no user
  action required to reveal it

#### Scenario: No control can hide the disclaimer
- **WHEN** the dashboard renders the AI insight panel
- **THEN** no toggle, setting, or other control exists anywhere in the
  UI that would hide or collapse the disclaimer

### Requirement: Ticker chips and searched-in entries show a freshness state
Each selectable ticker (a fixed chip or a searched-in entry) SHALL show
one of three states: **Loading** (a load-and-predict cycle is in
flight), **Fresh** (the stored prediction's `as_of` matches the latest
trading session available in the ticker's data), or **Stale** (a newer
trading session's data is available than the one the stored
prediction's `as_of` reflects).

#### Scenario: In-flight load shows Loading
- **WHEN** a ticker's load-and-predict cycle has been triggered and has
  not yet completed
- **THEN** that ticker's entry shows a Loading state

#### Scenario: Up-to-date prediction shows Fresh
- **WHEN** a ticker's stored prediction's `as_of` matches the latest
  trading session available for that ticker
- **THEN** that ticker's entry shows a Fresh state

#### Scenario: Newer data available than the stored prediction shows Stale
- **WHEN** a ticker has a newer trading session's data available than
  the one its stored prediction's `as_of` reflects
- **THEN** that ticker's entry shows a Stale state, rather than a fixed
  calendar-age threshold determining staleness

### Requirement: Loading a ticker immediately triggers its prediction
When `POST /tickers/{ticker}/load` succeeds from the dashboard — whether
triggered by a chip click or by search — the system SHALL immediately
trigger `GET /tickers/{ticker}/prediction` for that ticker as well, and
SHALL invalidate and refetch that ticker's `/prediction` and `/history`
data so the chart and prediction display reflect the newly-loaded data
without a manual page refresh or a separate user action to request a
prediction.

#### Scenario: Successful load refreshes chart and prediction automatically
- **WHEN** a load action for a ticker completes successfully from the
  dashboard, whether via a chip click or a search-triggered load
- **THEN** the chart panel, prediction display, and AI insight panel for
  that ticker fetch and reflect the newly loaded data without the user
  reloading the page or taking a separate action to request a
  prediction
</content>
