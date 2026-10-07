## ADDED Requirements

### Requirement: Range display shows the typical 5-session move and its measured coverage
For the selected ticker the dashboard SHALL render a range display from `GET /tickers/{ticker}/range` showing `range_5s_pct` as an unsigned half-width (`±X.X%`) labelled "Typical 5-session move" (Rule 1: five trading sessions), the response's `as_of` date, the nominal coverage stated in words and derived from the response's `range_coverage` (not a constant in the UI), and the ticker's `range_hit_rate` as a count of non-overlapping five-session moves (about the last year; the window and method are defined by `calibrate-volatility-range`) that stayed inside the band, worded "N of the last M five-session moves", where M is the `n` returned by `/range` and N is the response's hit count or, when the response carries only `rate` and `n`, `rate x n` rounded. The disclaimer in force SHALL be visible in the same card as the coverage and hit-rate figures.

This display, the range card, is the only surface that renders `range_hit_rate`. The chart band draws the range only, and the debate panel shows only the range line added by `calibrate-volatility-range`; neither renders the hit-rate. This change owns this rendering requirement.

#### Scenario: Available range is shown with its coverage
- **WHEN** `/range` responds with a numeric `range_5s_pct` of 3.2, `range_coverage` of 0.68 and `range_hit_rate` of `{rate: 0.75, n: 48}`
- **THEN** the card shows "±3.2%" labelled "Typical 5-session move", the `as_of` date, a sentence stating the nominal coverage as about 2 in 3, and a line reading "36 of the last 48 five-session moves"

#### Scenario: The hit-rate is rendered only in the range card
- **WHEN** the dashboard renders the range card, the chart band and the debate panel for a ticker whose `/range` response carries a `range_hit_rate`
- **THEN** the hit-rate wording appears in the range card and nowhere in the chart or the debate panel

#### Scenario: Coverage wording follows the response
- **WHEN** `/range` responds with `range_coverage` null (an uncalibrated ticker)
- **THEN** the card shows the range but makes no coverage claim

#### Scenario: Hit-rate that cannot be measured
- **WHEN** `range_hit_rate` is missing, has `n` of 0 or has neither a hit count nor a `rate`
- **THEN** the card shows "Not enough history to measure" in place of a percentage and no number is fabricated

#### Scenario: Disclaimer accompanies the coverage figures
- **WHEN** the card shows a coverage or hit-rate figure
- **THEN** the disclaimer in force is visible in the same card with no interaction

### Requirement: Range display distinguishes available, unavailable, not-loaded, and failed states
The range display SHALL render visually distinct states for: `GET /tickers/{ticker}/range` responding `200` with a numeric `range_5s_pct`; `200` with a null `range_5s_pct` (any refusing `status`); `404`; and `5xx`. It SHALL decide between the first two by whether `range_5s_pct` is a number and SHALL use `status` and `reasons` only as display text, so a status added later cannot cause a stale figure to be shown. It SHALL NOT render the same treatment for more than one of these outcomes, and SHALL show no number in any state but the first.

#### Scenario: Unavailable range names its reason
- **WHEN** `/range` responds `200` with a null `range_5s_pct` and a non-empty `reasons`
- **THEN** the card shows a message naming the reason from the response and no percentage

#### Scenario: Unavailable range without a reason
- **WHEN** `/range` responds `200` with a null `range_5s_pct` and no `reasons`
- **THEN** the card shows a generic "range unavailable for this ticker" message and no percentage

#### Scenario: Not-loaded state is distinguishable
- **WHEN** the range request responds `404`
- **THEN** the card shows that the ticker has not been loaded yet, in wording distinct from the unavailable and failed messages

#### Scenario: Server failure is distinguishable
- **WHEN** the range request responds with a `5xx` status
- **THEN** the card shows a failure message distinct from the not-loaded and unavailable messages

### Requirement: Range display shows no daily sigma, direction, or point forecast
The dashboard SHALL NOT render `sigma_daily_pct`, any signed or direction-coloured figure, or any single predicted price or return derived from the range, anywhere in the UI, including tooltips and hidden text. The range SHALL be drawn and written symmetrically about the last close and SHALL use no positive or negative (up or down) colour. This replaces the Rule 2 log-return conversion requirement: no endpoint the dashboard calls returns a log return.

#### Scenario: Daily sigma is never rendered
- **WHEN** `/range` responds with both `sigma_daily_pct` and `range_5s_pct`
- **THEN** only `range_5s_pct` appears in the DOM, and the value of `sigma_daily_pct` appears nowhere on the page

#### Scenario: No signed or directional figure
- **WHEN** the range card is rendered for any available range
- **THEN** its figure carries no `+` or `-` sign and no up/down data attribute or colour class

### Requirement: Dashboard issues no per-ticker requests for tickers that are not selected
On load the dashboard SHALL issue `GET /tickers` and no other request that depends on a ticker. Selecting a ticker SHALL issue `GET /tickers/{ticker}/history` and `GET /tickers/{ticker}/range` for that ticker and nothing else per ticker (the debate runs only on the user's Analyse click). A ticker chip SHALL NOT issue any query. Re-selecting a ticker within the session MAY be served from cache.

#### Scenario: Initial load with no selection
- **WHEN** the dashboard loads and the catalog holds 208 loaded tickers
- **THEN** exactly one API request is made, `GET /tickers`

#### Scenario: Selecting a ticker
- **WHEN** a user selects a ticker
- **THEN** one `/history` request and one `/range` request are made for that ticker, and no request is made for any other ticker

#### Scenario: No prediction, insight or backtest request exists
- **WHEN** any user flow runs (load, select, search-and-load, refresh, analyse)
- **THEN** no request is made to `/prediction`, `/insight` or `/backtest`

### Requirement: Range display shows explicit placeholders when no ticker is selected

When no ticker is selected, the range display SHALL render its full
populated layout (all labels and value slots) with an explicit
non-fabricated placeholder value (`N/A`) in place of every value that
depends on a selected ticker, rather than showing a "select a ticker"
message or omitting the card. This placeholder SHALL render at the same
font-size, font-family, and weight as a real populated value,
distinguished from one only by a muted color — not by a smaller or less
visually substantial presentation — so it reads as a legible, deliberate
"no value" state rather than a barely-visible mark. The debate panel's
disclaimer and the range card's disclaimer SHALL render unconditionally in
this state. The debate panel in this state shows its own prompt to select a
ticker; this requirement does not change that. This requirement applies only
to the no-ticker-selected case; each component's other states (loading,
not-loaded, unavailable, failure, populated) are unaffected and continue to
render independently per their own existing behavior.

#### Scenario: No ticker selected shows N/A placeholders in the range card

- **WHEN** the dashboard loads or a ticker is deselected, and no ticker is
  currently selected
- **THEN** the range display renders its title and an `N/A` placeholder,
  styled at the same font-size/family/weight as a real range value, in
  place of the percentage, plus its disclaimer

#### Scenario: Range display keeps the same shape whether or not a ticker is selected

- **WHEN** no ticker is selected
- **THEN** the range display renders all of its populated-state lines — the
  `N/A` range placeholder, an "As of —" placeholder in place of the real
  date, the unconditional "5 trading sessions" horizon line and the
  coverage line slot — so selecting a ticker for the first time does not
  grow the card by adding lines that were previously absent

#### Scenario: N/A placeholders are visually distinct from a real N/A value by color, not by wording

- **WHEN** the no-ticker `N/A` placeholder is shown
- **THEN** it is styled in a distinctly muted color from a real computed
  value or a real "not enough history" result, so it cannot be mistaken for
  actual range or coverage data

#### Scenario: Selecting a ticker replaces N/A placeholders with the card's states

- **WHEN** a ticker is selected after the N/A-placeholder state was
  showing
- **THEN** the N/A placeholders are removed, and the range display renders
  its own state (loading, not-loaded, unavailable, failure, or populated)
  for the selected ticker

### Requirement: Chart panel renders OHLCV plus a 5-session range band, no derived-indicator overlay

The chart panel SHALL render candles from `GET /tickers/{ticker}/history`,
and MAY additionally render that same response's volume field as a
histogram — both are raw OHLCV data already present in the response, not a
derived indicator. The chart SHALL NOT render any derived technical
indicator overlay (Ichimoku, RSI, MACD, Bollinger, ATR, OBV). The chart MAY
additionally render exactly one range band at the t+5 session position,
built from `range_5s_pct` in `GET /tickers/{ticker}/range`: an upper bound
at `close x (1 + range_5s_pct/100)` and a lower bound at
`close x (1 - range_5s_pct/100)`, where `close` is the most recent
historical close, drawn as dashed lines with a light fill between them in a
neutral colour, symmetric about the last close. The band SHALL NOT imply
direction: it uses no positive or negative colour, no arrow, and no marker
at either bound. The chart SHALL NOT render any line, point, envelope or
fill between the most recent historical close and the t+5 position, and
SHALL NOT render a single predicted price.

This requirement's substantive constraint is unchanged — no derived
technical indicator may be drawn; volume is raw fetched data, not a
prohibited indicator.

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

#### Scenario: Band bounds are computed from the last close
- **WHEN** the last historical close is 11 and `/range` responds with a numeric `range_5s_pct` of 5
- **THEN** the band's upper bound is 11.55 and its lower bound is 10.45 at the t+5 position

#### Scenario: Band is one position, not a path
- **WHEN** the chart panel renders a band
- **THEN** nothing is drawn between the most recent historical close and the t+5 position except empty axis space, and no valued data point is added to any series for the intermediate sessions

#### Scenario: Band is neutral and symmetric
- **WHEN** the chart panel renders a band
- **THEN** both bounds and the fill use the chart's neutral ink colour, never the positive or negative candle colours, and the upper and lower distances from the last close are equal

#### Scenario: No band when the range is unavailable
- **WHEN** `/range` responds with a null `range_5s_pct`, or responds `404` or `5xx`
- **THEN** the chart panel renders candles and volume only, with no band

#### Scenario: Price scale includes the band
- **WHEN** a band's upper or lower bound lies outside the price range of the visible candles
- **THEN** the price scale expands so both bounds are visible

### Requirement: Disclaimer stays visible with the debate panel and range card, with no visibility control
Per domain Rule 6, the dashboard SHALL display the disclaimer in force
(the text of `docs/DISCLAIMER.md`; its wording is owned by
`align-rules-and-disclaimer`) whenever a debate verdict, an Agreement count
or a measured range coverage is displayed. The dashboard SHALL NOT provide
any control that hides, collapses, or otherwise makes this disclaimer's
visibility optional.

#### Scenario: Disclaimer renders alongside the debate panel and the range card
- **WHEN** the debate panel or the range card is displayed for any ticker, or with no ticker selected
- **THEN** the disclaimer text is visible on the same view, with no user
  action required to reveal it

#### Scenario: No control can hide the disclaimer
- **WHEN** the dashboard renders
- **THEN** no toggle, setting, or other control exists anywhere in the
  UI that would hide or collapse the disclaimer

### Requirement: Loading a ticker refreshes its chart and range
When `POST /tickers/{ticker}/load` succeeds from the dashboard — whether
triggered by a Refresh action or by search — the system SHALL invalidate
that ticker's catalog entry, `/history` and `/range` data so the chart, the
range band and the range display reflect the newly-loaded data without a
manual page refresh or a separate user action. A ticker that is not
selected SHALL NOT have `/range` or `/history` fetched as a result; they are
fetched when it is next selected.

#### Scenario: Successful load refreshes chart and range automatically
- **WHEN** a load action for the selected ticker completes successfully
  from the dashboard, whether via search or Refresh
- **THEN** the chart panel and the range display for that ticker fetch and
  reflect the newly loaded data without the user reloading the page or
  taking a separate action

#### Scenario: A load for an unselected ticker fetches nothing per-ticker
- **WHEN** a load completes for a ticker that is not selected
- **THEN** only the catalog is refetched

### Requirement: Dashboard renders the debate panel for the selected ticker
The dashboard SHALL render the `DebatePanel` in the side panel region
unconditionally, with no environment variable or flag controlling it. The
region's layout dimensions and grid position are unchanged. The panel's
analysis runs only when the user clicks Analyse.

#### Scenario: Debate panel is shown with no configuration
- **WHEN** the dashboard loads with `VITE_DEBATE_PANEL_ENABLED` unset, `false` or `true`
- **THEN** the `DebatePanel` is rendered and no other insight panel exists in the tree

#### Scenario: No retired panel is reachable
- **WHEN** any user flow runs
- **THEN** no Confidence, Advice or "Backtest this ticker" element is rendered

## MODIFIED Requirements

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
- **WHEN** the chart panel renders a range band (per the "Chart panel
  renders OHLCV plus a 5-session range band" requirement)
- **THEN** the legend never displays a band bound as if it were a real
  session's OHLCV

## REMOVED Requirements

### Requirement: Unselected-ticker state shows explicit placeholders, not an empty message
**Reason**: The Prediction card and the AI insight panel it named are deleted; their N/A-placeholder rule is re-stated for the range card.
**Migration**: "Range display shows explicit placeholders when no ticker is selected".

### Requirement: Chart panel renders OHLCV plus the single predicted point, no derived-indicator overlay
**Reason**: The predicted point came from the retired direction model and implied a direction.
**Migration**: "Chart panel renders OHLCV plus a 5-session range band, no derived-indicator overlay".

### Requirement: Disclaimer is always visible, with no visibility control
**Reason**: It described the AI insight panel and a "backtested model", both deleted.
**Migration**: "Disclaimer stays visible with the debate panel and range card, with no visibility control".

### Requirement: Loading a ticker immediately triggers its prediction
**Reason**: `/prediction` is deleted; a load no longer triggers a prediction fetch.
**Migration**: "Loading a ticker refreshes its chart and range".

### Requirement: Dashboard renders AI insight panel for selected ticker
**Reason**: The AI insight panel and the `VITE_DEBATE_PANEL_ENABLED` flag are deleted.
**Migration**: "Dashboard renders the debate panel for the selected ticker".

### Requirement: Predicted log return is converted to a percentage before display
**Reason**: No endpoint the dashboard calls returns `predicted_log_return` any more, so there is nothing to convert. Rule 2 stays in force and is carried by "Range display shows no daily sigma, direction, or point forecast".
**Migration**: `range_5s_pct` is already a percentage half-width and is shown as received.

### Requirement: Prediction display distinguishes ok, near_gap, not-loaded, and failed states
**Reason**: The Prediction card and `/prediction` are deleted.
**Migration**: "Range display distinguishes available, unavailable, not-loaded, and failed states".

### Requirement: AI insight panel computes and displays Confidence, Sentiment, and Advice
**Reason**: `AIInsightPanel` and `/insight` are deleted; Advice and Confidence were derived from the retired XGBoost model.
**Migration**: The debate verdict and Agreement count (`debate-panel-ui`) and the range display's measured coverage replace them. Rules 3 and 4 need rulings from `align-rules-and-disclaimer`.

### Requirement: Confidence reflects backtested hit-rate, or explicit N/A for unvalidated tickers
**Reason**: Confidence read `backtest_predictions` (10 tickers; 589 of 599 loaded tickers would read N/A) and the model behind it is retired.
**Migration**: `range_hit_rate` in the range display is the owner's proposed replacement; the Rule 4 ruling belongs to `align-rules-and-disclaimer`.

### Requirement: "Backtest this ticker" action populates Confidence for unvalidated tickers
**Reason**: `POST /tickers/{ticker}/backtest` and `useBacktestTicker` are deleted; there is no Confidence to populate.
**Migration**: None.

### Requirement: Sentiment is labeled as a technical proxy, not real sentiment
**Reason**: The AI insight panel's Technical Signal element is deleted. The label obligation (Rule 5) continues in `debate-panel-ui` "Agent cards use correct labels (Rule 5)". The always-visible inline RSI / MACD / Ichimoku basis line is not carried over; the debate card shows its reasoning bullets at Level 2, and whether Level 1 needs a basis line is part of the Rule 5 ruling.
**Migration**: See `debate-panel-ui`.

### Requirement: Advice uses directional wording, never a transaction verb
**Reason**: Advice is deleted with `/insight`. The ban on transaction wording continues in `align-rules-and-disclaimer`'s label requirements for the debate verdict.
**Migration**: None.

### Requirement: Ticker chips and searched-in entries show a freshness state
**Reason**: The dot compared a prediction's `as_of` with the latest stored session; the prediction is gone and the comparison was constant by construction (`docs/DISCUSSION_calendar_staleness.md`).
**Migration**: "Loaded Nd ago" and the Refresh action (`ticker-manual-refresh`) stay on each chip; the range display shows `as_of`; the debate result carries data age (`debate-data-guards`).
