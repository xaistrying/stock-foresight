## MODIFIED Requirements

### Requirement: Prediction endpoint returns volatility range in addition to model output
`GET /tickers/{ticker}/prediction` SHALL include a `volatility_range_pct` field in its response — the HAR-RV predicted ±% range for the next 5 trading sessions (Rule 1, Rule 2: shown as percentage, not log return). The existing `predicted_log_return` field is retained for backwards compatibility but marked `deprecated: true` in the response. The endpoint MUST NOT remove `predicted_log_return` in this change.

#### Scenario: Prediction response includes volatility range
- **WHEN** `GET /tickers/{ticker}/prediction` is called for a loaded ticker with sufficient history
- **THEN** response includes `volatility_range_pct: <float>` alongside the existing fields

#### Scenario: Insufficient history for volatility range
- **WHEN** the ticker has fewer than 60 OHLCV sessions
- **THEN** `volatility_range_pct: null` is returned; `predicted_log_return` is still returned as before

## REMOVED Requirements

### Requirement: Insight endpoint drives Advice and Confidence from XGBoost
**Reason**: XGBoost directional prediction is retired from the live serving path (pooled hit-rate 47.8%, statistically indistinguishable from random — see `docs/DISCUSSION_model_direction.md`). The `GET /tickers/{ticker}/insight` endpoint is deprecated; Advice and Confidence derived from XGBoost direction are superseded by the debate verdict and agreement level.

**Migration**: Use `POST /tickers/{ticker}/debate` for analysis. The `GET /tickers/{ticker}/insight` endpoint remains alive and returns its existing response shape with an added `deprecated: true` field and a `Deprecation: true` response header. It will be removed in a future change after the debate panel is validated in production.
