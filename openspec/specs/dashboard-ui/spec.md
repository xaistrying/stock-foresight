# dashboard-ui

## Purpose

TBD

## Requirements

### Requirement: Ticker panel shows the fixed set plus search for any real ticker
The dashboard's ticker panel SHALL render one selectable chip per ticker
returned by `GET /tickers` (the 9 `TRAINING_TICKERS`), always visible.
The panel SHALL also provide a search action that resolves a
user-entered ticker symbol; if that ticker is not yet loaded, the search
action SHALL trigger `POST /tickers/{ticker}/load` the same way clicking
an unloaded chip would, and the ticker SHALL join the selectable list
once loaded successfully.

#### Scenario: Panel renders the fixed set as chips
- **WHEN** the dashboard loads
- **THEN** the ticker panel shows one selectable chip per ticker
  returned by `GET /tickers`, always visible regardless of search state

#### Scenario: Searching an unloaded ticker triggers a load
- **WHEN** a user searches a ticker symbol that has no rows in `ohlcv`
  yet
- **THEN** the dashboard calls `POST /tickers/{ticker}/load` for that
  symbol, and the ticker becomes selectable once the load succeeds

#### Scenario: Searching an already-loaded ticker selects it directly
- **WHEN** a user searches a ticker symbol that already has data loaded
  (whether one of the 9 chips or a previously searched-in ticker)
- **THEN** the dashboard selects it directly without issuing a new
  `/load` request

#### Scenario: A searched-in ticker persists as a selectable entry
- **WHEN** a searched ticker outside `TRAINING_TICKERS` has loaded
  successfully at least once
- **THEN** it remains selectable in the ticker panel for the rest of the
  session, alongside the 9 fixed chips

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

### Requirement: Chart panel renders OHLCV plus the single predicted point, no indicator overlay
The chart panel SHALL render candles from `GET
/tickers/{ticker}/history`. It SHALL NOT render any indicator overlay
(Ichimoku, RSI, MACD, Bollinger, ATR, OBV). The chart MAY additionally
render exactly one predicted point at t+5 sessions, derived from
`predicted_log_return` per the percentage-conversion requirement above,
connected to the most recent historical close by a single straight
line. The chart SHALL NOT render any interpolated, smoothed, or
otherwise fabricated point between the most recent historical close and
the t+5 predicted point.

#### Scenario: Chart shows candles for the selected ticker
- **WHEN** a ticker is selected in the ticker panel
- **THEN** the chart panel renders OHLC candles from that ticker's `GET
  /tickers/{ticker}/history` response

#### Scenario: No indicator lines are drawn
- **WHEN** the chart panel renders
- **THEN** no indicator overlay is drawn on or alongside the candles

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
