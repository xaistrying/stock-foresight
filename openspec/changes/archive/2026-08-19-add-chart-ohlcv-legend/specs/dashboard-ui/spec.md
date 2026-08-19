## ADDED Requirements

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
