## MODIFIED Requirements

### Requirement: Leakage-safe pooled walk-forward split
The system SHALL provide a walk-forward split with pooled fold boundaries shared across all tickers in the evaluated set, an expanding training window, and an explicit purge gap on the training side of each fold boundary, for any evaluation that fits a model per fold. The system SHALL NOT use a shuffled or k-fold cross-validation split for this purpose.

#### Scenario: Fold boundaries are shared calendar dates across tickers
- **WHEN** the walk-forward split is constructed
- **THEN** every ticker's rows are partitioned into folds using the same set of calendar-date boundaries, not independently per ticker

#### Scenario: Training window expands across folds
- **WHEN** moving from one fold to the next later fold
- **THEN** the later fold's training set includes all of the earlier fold's training data plus additional data, never less

#### Scenario: Training rows whose label overlaps the test period are purged
- **WHEN** a fold boundary separates training data from a test period starting at date T
- **THEN** any row whose target label (per Rule 1, `t+5` sessions ahead) falls at or after T is excluded from that fold's training set, even though its own date is before T

#### Scenario: No shuffled cross-validation is used
- **WHEN** a model is validated
- **THEN** the validation methodology is the walk-forward split described above; no random shuffling of rows across train/test assignment occurs

## REMOVED Requirements

### Requirement: Directional hit-rate metric
**Reason**: There is no directional prediction to score. Rule 4's directional hit-rate is replaced by the range hit-rate, a different quantity (share of five-session moves inside the displayed band) defined in `calibrate-volatility-range`.
**Migration**: Use `range_hit_rate` from `GET /tickers/{ticker}/range`. The ruling on Rule 4 belongs to `align-rules-and-disclaimer`.

### Requirement: Persisted per-ticker rolling hit-rate
**Reason**: `backtest_predictions` is no longer written or read (`persist_backtest_predictions` and `compute_rolling_hit_rate` are deleted). The table and its 10,191 rows stay in existing databases, untouched; no migration drops them.
**Migration**: None. `range_hit_rate` is computed from OHLCV history on request, not persisted.

### Requirement: No simulated trading return or P&L reporting
**Reason**: The backtest that could have produced such figures is deleted. The prohibition on P&L framing continues to follow from Rule 6 and the disclaimer.
**Migration**: None.

### Requirement: Model Card documents backtest methodology and results
**Reason**: There is no live model to document. `docs/MODEL_CARD.md` stays as the record of the retired model; its retirement note belongs to `align-rules-and-disclaimer`.
**Migration**: None.
