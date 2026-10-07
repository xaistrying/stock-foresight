## ADDED Requirements

### Requirement: Catalog entries carry an eligibility summary computed in one pass
Each entry in `GET /tickers`'s response SHALL include `eligibility`, an object `{eligible, reasons, as_of, age_sessions}` equal, field for field and in the same fixed reason order, to what `assess_eligibility(ticker)` (`data-eligibility`) returns for that ticker at the time of the request, so a client can say why a ticker cannot be analysed without one request per ticker. `eligibility` SHALL be null for an entry that is not loaded (no `tickers` row), and SHALL be present, never omitted. The entries of one response SHALL be computed in a single batched pass: the distinct stored session dates SHALL be read once for the whole response, not once per ticker. `assess_eligibility` SHALL be a single-ticker call of the same batched code, so the two cannot differ. The field is additive: no existing field of an entry changes.

#### Scenario: Summary equals the single-ticker assessment
- **WHEN** `GET /tickers` is requested and, for every loaded entry, `assess_eligibility(entry.ticker, now)` is evaluated with the same clock
- **THEN** each entry's `eligibility` equals that result, including the order of `reasons`

#### Scenario: Several reasons keep their fixed order
- **WHEN** a catalog ticker is delisted and its data is 21 sessions old
- **THEN** its `eligibility.reasons` is `["delisted", "stale"]`, `eligible` is false and `age_sessions` is 21

#### Scenario: Not-loaded ticker has a null summary
- **WHEN** a catalog entry has `loaded: false`
- **THEN** its `eligibility` is null and the response is still `200`

#### Scenario: Ticker with no features row
- **WHEN** a loaded ticker has no `features` row
- **THEN** its `eligibility` is `{eligible: false, reasons: ["insufficient_history"], as_of: null, age_sessions: null}`

#### Scenario: One scan of session dates for the whole catalog
- **WHEN** `GET /tickers` is requested for a catalog of 208 loaded tickers and the database statements issued are counted
- **THEN** the distinct-session-dates read is issued exactly once, and no statement is issued once per ticker for it

#### Scenario: Still read-only
- **WHEN** `GET /tickers` is requested
- **THEN** no `vnstock` call is made and no table is written, as before
