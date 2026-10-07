## MODIFIED Requirements

### Requirement: Row filtering excludes unknown-quality rows
The system SHALL exclude any `features` row where `near_gap = 1`, `target IS NULL`, or any indicator column is null from the clean row set used to build walk-forward folds (`filter_clean_labeled`). Indicator nulls are checked directly against the indicator columns, not through `near_gap`, so a hard-flag blackout row whose `near_gap` is clear is still excluded.

#### Scenario: near_gap rows are excluded
- **WHEN** the clean row set is built for fold construction
- **THEN** rows with `near_gap = 1` are not included

#### Scenario: Rows with a null target are excluded
- **WHEN** the clean row set is built for fold construction
- **THEN** rows with `target IS NULL` (insufficient future data per the target computation) are not included

#### Scenario: Blacked-out rows are excluded without relying on near_gap
- **WHEN** a row has `near_gap = 0`, a non-null target and one or more null indicator columns
- **THEN** it is not included in the clean row set

## REMOVED Requirements

### Requirement: Fixed multi-ticker training set
**Reason**: There is no model trained on a fixed ticker set. `TRAINING_TICKERS` remains only as a legacy catalog marker (see `ticker-catalog`).
**Migration**: None. The HAR-RV model's training universe is defined by `calibrate-volatility-range`.

### Requirement: Pure OHLCV-derived features only, no ticker identity
**Reason**: The feature matrix assembly (`assemble_feature_matrix`) existed only for the XGBoost regressor and is deleted.
**Migration**: None.

### Requirement: Pooled single global model
**Reason**: The pooled XGBoost regressor is retired and no longer trained or served.
**Migration**: None.

### Requirement: Conservative, untuned hyperparameters
**Reason**: `XGB_PARAMS` and the training procedure are deleted.
**Migration**: The recorded values stay in `docs/MODEL_CARD.md` as history.

### Requirement: Persisted model artifact
**Reason**: The training procedure that wrote `pooled_xgb_model.json` is deleted. The existing file stays on disk, gitignored and unread; it is not deleted by this change.
**Migration**: None.
