## ADDED Requirements

### Requirement: Ticker panel lists only the fixed validated set
The dashboard's ticker panel SHALL render exactly the tickers returned by
`GET /tickers` and SHALL NOT provide free-text ticker entry or any other
means of selecting a ticker outside that set for prediction display.

#### Scenario: Panel renders the fixed set
- **WHEN** the dashboard loads
- **THEN** the ticker panel shows one selectable entry per ticker
  returned by `GET /tickers`, and no input field for typing an arbitrary
  ticker symbol

#### Scenario: Selecting a ticker never targets an unvalidated symbol
- **WHEN** a user interacts with the ticker panel to choose a ticker for
  the chart and prediction display
- **THEN** the selected ticker is always one of the entries returned by
  `GET /tickers` — never a client-constructed or free-typed value

### Requirement: Predicted log return is converted to a percentage before display
Per domain Rule 2, the dashboard SHALL NOT render the raw
`predicted_log_return` value returned by `GET
/tickers/{ticker}/prediction` anywhere in the UI. It SHALL convert it to
a simple percentage (`(e^predicted_log_return - 1) * 100`) before
display.

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
more than one of these outcomes.

#### Scenario: Ok state shows the converted prediction
- **WHEN** the prediction response has `status: "ok"`
- **THEN** the dashboard displays the converted percentage and the
  `as_of` date

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

### Requirement: Chart panel renders OHLCV only, no indicator overlay
The chart panel SHALL render candles from `GET
/tickers/{ticker}/history` only. It SHALL NOT render any indicator
overlay (Ichimoku, RSI, MACD, Bollinger, ATR, OBV) or any predicted-vs-
actual series in this version.

#### Scenario: Chart shows candles for the selected ticker
- **WHEN** a ticker is selected in the ticker panel
- **THEN** the chart panel renders OHLC candles from that ticker's `GET
  /tickers/{ticker}/history` response

#### Scenario: No indicator lines are drawn
- **WHEN** the chart panel renders
- **THEN** no indicator overlay or predicted-vs-actual series is drawn on
  or alongside the candles

### Requirement: AI insight panel area is reserved as a placeholder
The dashboard SHALL reserve a visibly distinct panel area for the future
M6 AI insight panel (Confidence, Sentiment, Advice — Rules 3, 4, 5). This
version SHALL NOT compute or display a confidence score, sentiment
proxy, or advice text — the panel SHALL show only a placeholder
indicating this feature is not yet available.

#### Scenario: Placeholder panel is visible but inert
- **WHEN** the dashboard renders
- **THEN** a panel area is visible in the AI-insight-panel position
  showing a "coming soon" / not-yet-available state, with no confidence
  score, sentiment proxy, or advice text rendered anywhere on the page

### Requirement: Loading a ticker refetches its prediction and history
When `POST /tickers/{ticker}/load` succeeds from the dashboard, the
system SHALL invalidate and refetch that ticker's `/prediction` and
`/history` data so the chart and prediction display reflect the
newly-loaded data without a manual page refresh.

#### Scenario: Successful load refreshes chart and prediction
- **WHEN** a load action for a ticker completes successfully from the
  dashboard
- **THEN** the chart panel and prediction display for that ticker
  re-fetch and reflect the newly loaded data without the user reloading
  the page
