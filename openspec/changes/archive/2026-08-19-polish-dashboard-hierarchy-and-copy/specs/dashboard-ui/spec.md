## ADDED Requirements

### Requirement: Unselected-ticker state shows dash placeholders, not an empty message

When no ticker is selected, the Prediction display and AI insight panel
SHALL each render their full populated layout (all labels and value
slots) with a dash (`—`) placeholder in place of every value that
depends on a selected ticker, rather than showing a "select a ticker"
message or omitting either panel. The AI insight panel's disclaimer
SHALL render unconditionally in this state, consistent with its
unconditional visibility whenever a ticker is selected. This requirement
applies only to the no-ticker-selected case; each component's other
states (loading, not-loaded, feature-computation failure, populated) are
unaffected and continue to render independently per their own existing
behavior.

#### Scenario: No ticker selected shows dash placeholders in both panels

- **WHEN** the dashboard loads or a ticker is deselected, and no ticker is
  currently selected
- **THEN** the Prediction display renders its title and a dash
  placeholder in place of the percentage/as-of value, and the AI insight
  panel renders Confidence, Technical Signal, and Advice labels each with
  a dash placeholder value, plus its disclaimer

#### Scenario: Dash placeholders are visually distinct from a real N/A value

- **WHEN** the no-ticker dash placeholder is shown
- **THEN** it is styled distinctly from a real computed value (e.g. a
  muted color), so it cannot be mistaken for actual Confidence/Sentiment/
  Advice/Prediction data — consistent with rules 4/5/6's requirement that
  these disclosures reflect real computed data or an explicit N/A, never
  a value that could pass as real

#### Scenario: Selecting a ticker replaces dash placeholders with per-component states

- **WHEN** a ticker is selected after the dash-placeholder state was
  showing
- **THEN** the dash placeholders are removed, and the Prediction display
  and AI insight panel each independently render their own state
  (loading, not-loaded, failure, or populated) for the selected ticker,
  as already specified elsewhere in this capability

## MODIFIED Requirements

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
