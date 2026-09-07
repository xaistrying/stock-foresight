## MODIFIED Requirements

### Requirement: Prediction display distinguishes ok, near_gap, not-loaded, and failed states
The dashboard SHALL render visually distinct states for the five
outcomes of `GET /tickers/{ticker}/prediction`: `200` with `status:
"ok"`, `200` with `status: "near_gap"`, `200` with `status:
"indicators_unavailable"`, `404`, and `5xx`. It SHALL NOT render the same
UI treatment (e.g. a blank or generic loading state) for more than one of
these outcomes. This applies identically for any ticker, whether one of
the 9 `TRAINING_TICKERS` or a searched-in ticker.

#### Scenario: Ok state shows the converted prediction
- **WHEN** the prediction response has `status: "ok"`
- **THEN** the dashboard displays the converted percentage, the `as_of`
  date, and static label text naming the fixed 5-trading-session horizon
  (Rule 1) — never a control implying the horizon is adjustable

#### Scenario: near_gap state is distinguishable from ok
- **WHEN** the prediction response has `status: "near_gap"`
- **THEN** the dashboard shows a message indicating a data gap prevents a
  current prediction, and does not display a percentage figure

#### Scenario: indicators_unavailable state is distinguishable from near_gap
- **WHEN** the prediction response has `status: "indicators_unavailable"`
- **THEN** the dashboard shows a message naming a data-quality flag on the
  ticker's recent sessions, distinct in wording from the near_gap message
  and displaying no percentage figure — never an empty card body

#### Scenario: Not-loaded state is distinguishable from near_gap and failure
- **WHEN** the prediction request responds `404`
- **THEN** the dashboard shows a message indicating the ticker has not
  been loaded yet, distinct from the near_gap and failure messages

#### Scenario: Feature-computation-failure state is distinguishable from the others
- **WHEN** the prediction request responds with a `5xx` status
- **THEN** the dashboard shows a message indicating feature computation
  failed for this ticker, distinct from the near_gap and not-loaded
  messages

The chart panel's "No predicted point when prediction is unavailable"
requirement is deliberately left unmodified: it already gates the predicted
point on `status: "ok"` rather than enumerating the unavailable statuses, so
a fifth outcome needs no change there.
