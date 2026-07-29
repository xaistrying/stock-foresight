# feature-engineering

## Purpose

TBD

## Requirements

### Requirement: Features table schema
The system SHALL persist engineered features in a SQLite `features` table
keyed by `(ticker, date)`, containing columns for Ichimoku components
(including `chikou_signal`, not a literal Chikou Span), RSI, MACD,
Bollinger Bands, ATR, OBV, the prediction target, a gap-quality flag, and a
`computed_at` timestamp, distinct from the raw `ohlcv` table.

#### Scenario: Row shape includes all six indicator families, target, and metadata
- **WHEN** a row is written to `features` for a given `(ticker, date)`
- **THEN** the row includes non-null Ichimoku, RSI, MACD, Bollinger Band,
  ATR, and OBV columns (when computable — see warm-up scenarios below), a
  `target` column, a `near_gap` boolean column, and a `computed_at`
  timestamp set to the time of computation

### Requirement: Target variable computation
The system SHALL compute `target = ln(close[t+5] / close[t])` for each row,
per Rule 1 (5 trading sessions ahead, not calendar days, log return).

#### Scenario: Target computed from close prices 5 sessions apart
- **WHEN** computing the target for date `t` for a ticker with a valid
  close price at the 5th subsequent stored session `t+5`
- **THEN** `target = ln(close[t+5] / close[t])`

#### Scenario: Target is null when insufficient future data exists
- **WHEN** a date `t` has fewer than 5 subsequent stored sessions for its
  ticker (e.g. the most recent rows in the series)
- **THEN** `target` is null for that row, and the row is still written
  (feature columns are still computed and persisted)

### Requirement: Technical indicator computation
The system SHALL compute Ichimoku, RSI, MACD, Bollinger Bands, ATR, and OBV
for each `(ticker, date)` row using standard, explicitly-documented
parameters (periods/smoothing), reading only from the `ohlcv` table.

#### Scenario: Indicators computed per ticker independently
- **WHEN** computing features for a ticker
- **THEN** only that ticker's `ohlcv` rows are used as input; no
  cross-ticker leakage occurs

#### Scenario: Indicator parameters are documented
- **WHEN** this change is implemented
- **THEN** `docs/DATA_DICTIONARY.md` documents the exact period/smoothing
  parameters used for each indicator

### Requirement: No look-ahead leakage in indicator computation
The system SHALL NOT compute any `features` value for row `(ticker, t)`
using any `ohlcv` row dated after `t`. In particular, Ichimoku's Chikou
Span SHALL be represented as `chikou_signal`, a leakage-safe comparison of
`close(t)` to `close(t-26)`, not the textbook backward-shifted Chikou
value (which would require `close(t+26)`).

#### Scenario: Ichimoku Chikou is leakage-safe, not literally as-charted
- **WHEN** computing Ichimoku-family values for date `t`
- **THEN** no output column depends on any `ohlcv` row dated after `t`;
  `chikou_signal(t) = close(t) - close(t-26)` (or the equivalent boolean),
  never `close(t+26)`

#### Scenario: No indicator reads future rows
- **WHEN** computing any feature column for row `(ticker, t)`
- **THEN** the computation's inputs are restricted to `ohlcv` rows with
  `date <= t` for that ticker

### Requirement: Gap-aware quality flagging
The system SHALL set `near_gap = 1` for any `(ticker, date)` row whose
indicator computation window overlaps an M1-logged gap (session-to-session
distance greater than 5 calendar days) or extends before the ticker's first
stored session, and SHALL NOT filter, drop, or block writing such rows.

#### Scenario: Row within an indicator's lookback of a logged gap
- **WHEN** a row's date `t` has, within the longest indicator lookback
  window used for that row (e.g. Ichimoku's longest component), a stored
  gap greater than 5 calendar days between two sessions
- **THEN** `near_gap = 1` for that row, and the row's indicator values are
  still computed and written using the available sequential rows

#### Scenario: Row near the start of a ticker's series
- **WHEN** a row's date `t` is close enough to the ticker's first stored
  session that the longest indicator lookback window extends before
  available history
- **THEN** `near_gap = 1` for that row

#### Scenario: Rows unaffected by gaps are not flagged
- **WHEN** a row's full indicator lookback window contains no gap greater
  than 5 calendar days and does not extend before the ticker's first stored
  session
- **THEN** `near_gap = 0` for that row

### Requirement: Idempotent upsert on recomputation
The system SHALL upsert into `features` on `(ticker, date)` conflict when
feature computation is re-run for a ticker, without creating duplicate rows.

#### Scenario: Re-running feature computation updates existing rows
- **WHEN** feature computation is re-run for a ticker that already has rows
  in `features`
- **THEN** existing `(ticker, date)` rows are updated in place
  (`ON CONFLICT ... DO UPDATE`), not duplicated, and `computed_at` is set to
  the new computation time

### Requirement: Data dictionary documentation for features table
The system SHALL document the `features` table schema, indicator
parameters, warm-up window lengths, and `near_gap` semantics in
`docs/DATA_DICTIONARY.md`.

#### Scenario: Data dictionary reflects the features table after this change
- **WHEN** this change is implemented
- **THEN** `docs/DATA_DICTIONARY.md` describes the `features` table schema,
  each indicator's parameters and warm-up window, the target formula (Rule
  1), and what `near_gap = 1` means and does not mean (advisory, not a
  filter)
