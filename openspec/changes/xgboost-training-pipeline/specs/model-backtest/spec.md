## ADDED Requirements

### Requirement: Leakage-safe pooled walk-forward split
The system SHALL validate the model using a walk-forward split with
pooled fold boundaries shared across all training tickers, an expanding
training window, and an explicit purge gap on the training side of each
fold boundary. The system SHALL NOT use a shuffled or k-fold
cross-validation split for this purpose.

#### Scenario: Fold boundaries are shared calendar dates across tickers
- **WHEN** the walk-forward split is constructed
- **THEN** every ticker's rows are partitioned into folds using the same
  set of calendar-date boundaries, not independently per ticker

#### Scenario: Training window expands across folds
- **WHEN** moving from one fold to the next later fold
- **THEN** the later fold's training set includes all of the earlier
  fold's training data plus additional data, never less

#### Scenario: Training rows whose label overlaps the test period are purged
- **WHEN** a fold boundary separates training data from a test period
  starting at date T
- **THEN** any row whose target label (per Rule 1, `t+5` sessions ahead)
  falls at or after T is excluded from that fold's training set, even
  though its own date is before T

#### Scenario: No shuffled cross-validation is used
- **WHEN** the model is validated
- **THEN** the validation methodology is the walk-forward split described
  above; no random shuffling of rows across train/test assignment occurs

### Requirement: Directional hit-rate metric
The system SHALL compute a hit-rate metric for each out-of-fold
(backtested) prediction, where a prediction is a "hit" if
`sign(predicted_target) == sign(actual_target)`, and a "miss" otherwise,
including when `actual_target == 0`.

#### Scenario: Matching-sign prediction is a hit
- **WHEN** a backtested prediction's sign matches its actual target's sign
  (both positive or both negative)
- **THEN** that prediction is recorded as a hit

#### Scenario: Opposite-sign prediction is a miss
- **WHEN** a backtested prediction's sign does not match its actual
  target's sign
- **THEN** that prediction is recorded as a miss

#### Scenario: Zero actual target is a miss regardless of prediction
- **WHEN** a backtested row's actual target equals exactly 0
- **THEN** that prediction is recorded as a miss, regardless of the
  predicted value's sign

### Requirement: Persisted per-ticker rolling hit-rate
The system SHALL persist backtested (out-of-fold) predictions and their
hit/miss outcome in a form that supports computing, for any of the 9
training tickers, the hit-rate over that ticker's most recent ~60
backtested predictions.

#### Scenario: Backtest results are queryable per ticker
- **WHEN** backtesting completes
- **THEN** each ticker's out-of-fold predictions, actual targets, and
  hit/miss outcomes are persisted and retrievable filtered to that ticker,
  ordered by date

#### Scenario: Rolling hit-rate is computable from persisted results
- **WHEN** a ticker has at least 60 persisted backtested predictions
- **THEN** the hit-rate over its most recent 60 predictions can be
  computed directly from the persisted results, without re-running
  training or backtesting

### Requirement: No simulated trading return or P&L reporting
The system SHALL NOT compute or report simulated trading returns, P&L, or
any framing implying realized investment performance from backtest
results.

#### Scenario: Backtest output contains no P&L figures
- **WHEN** backtest results are produced or documented
- **THEN** no simulated return, profit/loss, or win-rate-in-currency-terms
  figure is present; only directional accuracy (hit-rate) and standard
  regression error metrics (e.g. MAE/RMSE on the log-return target) are
  reported

### Requirement: Model Card documents backtest methodology and results
The system SHALL document, in `docs/MODEL_CARD.md`, the training data
(tickers, row counts, date ranges), the walk-forward split methodology
(fold count, purge gap, expanding-window rationale), the hit-rate
definition, and per-ticker backtest results, framed as technical
observation rather than investment performance (Rule 6).

#### Scenario: Model Card is created by this change
- **WHEN** this change is implemented
- **THEN** `docs/MODEL_CARD.md` exists and documents training data,
  features used, split methodology, hyperparameters, hit-rate definition,
  and backtest results

#### Scenario: Model Card avoids investment-advice framing
- **WHEN** `docs/MODEL_CARD.md` describes backtest results
- **THEN** results are described as technical/statistical observations
  (e.g. "directional hit-rate of X% over walk-forward validation"), not as
  investment advice, predicted returns, or performance claims
