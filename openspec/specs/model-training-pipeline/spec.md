# model-training-pipeline

## Purpose

TBD

## Requirements

### Requirement: Fixed multi-ticker training set
The system SHALL train against `features` rows from a fixed set of 9
tickers (TCB, VIB, VHM, VND, MWG, HPG, MSN, VNM, SAB), selected by
empirical realized-volatility and stale-price screening rather than
sector-label assumption, and already loaded via M1's existing per-ticker
load endpoint.

#### Scenario: Training reads only the named ticker set
- **WHEN** the training pipeline loads its input data
- **THEN** only rows for TCB, VIB, VHM, VND, MWG, HPG, MSN, VNM, and SAB
  are included; no other tickers are read even if present in `features`

### Requirement: Row filtering excludes unknown-quality rows
The system SHALL exclude any `features` row where `near_gap = 1` or
`target IS NULL` from both training and backtest evaluation.

#### Scenario: near_gap rows are excluded
- **WHEN** the training pipeline loads input data for a ticker
- **THEN** rows with `near_gap = 1` are not included in the training or
  backtest evaluation set

#### Scenario: Rows with a null target are excluded
- **WHEN** the training pipeline loads input data for a ticker
- **THEN** rows with `target IS NULL` (insufficient future data per M2's
  target computation) are not included in the training or backtest
  evaluation set

### Requirement: Pure OHLCV-derived features only, no ticker identity
The system SHALL train only on the existing indicator columns (Ichimoku
components, RSI, MACD components, Bollinger Band components, ATR, OBV) as
model input features. The system SHALL NOT include ticker identity (as a
categorical column, one-hot encoding, or per-ticker target encoding) as a
model input feature.

#### Scenario: Model input excludes ticker identity
- **WHEN** constructing the feature matrix for training
- **THEN** the ticker column is not present among the model's input
  features, in any encoded form

### Requirement: Pooled single global model
The system SHALL train one XGBoost regressor across all 9 tickers' pooled
rows, not a separate model per ticker.

#### Scenario: One model artifact covers all tickers
- **WHEN** training completes
- **THEN** exactly one trained model artifact is produced, usable for
  predictions on any of the 9 training tickers

### Requirement: Conservative, untuned hyperparameters
The system SHALL use a fixed, documented, conservative XGBoost
hyperparameter configuration (shallow trees, early stopping against a
validation fold, regularization via subsample/colsample_bytree,
`min_child_weight` above the library default) for this training pass, with
no automated or manual hyperparameter search performed.

#### Scenario: Hyperparameters are fixed and documented
- **WHEN** the model is trained
- **THEN** the exact hyperparameter values used are recorded in
  `docs/MODEL_CARD.md`, and no tuning/search procedure was run to select
  them

### Requirement: Persisted model artifact
The system SHALL persist the trained model artifact to disk in a location
and format that a future prediction-serving component (M4) can load.

#### Scenario: Model artifact is saved after training
- **WHEN** training completes successfully
- **THEN** a model artifact file exists on disk, containing the trained
  XGBoost model, in a location under `backend/data/models/`
