## ADDED Requirements

### Requirement: Signal computation reuses the existing walk-forward protocol
The system SHALL compute cross-sectional momentum signals and evaluate them
using the same pooled, expanding-window, purge-gapped walk-forward protocol
`backend/app/ml/training.py` already defines (`compute_fold_boundaries` and
its purge logic), rather than a new or differently-parameterized protocol,
so results are comparable to `docs/MODEL_CARD.md`'s existing figures.

#### Scenario: Fold boundaries match the established protocol
- **WHEN** the evaluation computes its walk-forward folds over the
  modelling universe's pooled date range
- **THEN** the fold count and boundary-computation method are the same as
  `compute_fold_boundaries` uses for the production model, not an
  independently chosen scheme

#### Scenario: Purge gap is applied per horizon evaluated
- **WHEN** a fold boundary is used to split training from test data for a
  given horizon
- **THEN** rows within that horizon's lookahead window of the boundary are
  excluded from training, mirroring the existing purge-gap rationale for
  Rule 1's 5-session horizon, generalized to whichever horizon is being
  evaluated

### Requirement: Evaluation runs over the current modelling universe
The system SHALL evaluate cross-sectional momentum over exactly the
modelling universe as currently defined — `ticker_universe` rows with
`ingestion_state = 'ok'`, `fails_liquidity_filter = 0`, and
`below_minimum_history = 0` — not a hand-picked or hard-coded ticker list.

#### Scenario: Universe membership is read at run time
- **WHEN** the evaluation runs
- **THEN** it queries `ticker_universe` for the current set of symbols
  passing the modelling-universe filters, rather than reading a
  previously-saved or hard-coded list

#### Scenario: A change in universe membership changes what is evaluated
- **WHEN** the modelling universe's membership changes (a symbol newly
  passes or newly fails the liquidity or minimum-history filter)
- **THEN** a subsequent run of the evaluation reflects that change without
  requiring the evaluation code itself to be edited

### Requirement: Signals are computed at multiple horizons and cross-sectionally demeaned
The system SHALL compute a momentum signal at each of the 5, 10, 21, and
63-session horizons, and SHALL demean each signal and its corresponding
forward return across all universe symbols sharing the same date, so the
evaluation measures relative (cross-sectional) predictability rather than
each symbol's own absolute momentum.

#### Scenario: Demeaning is cross-sectional, not per-ticker
- **WHEN** a signal value is computed for a symbol on a given date
- **THEN** it is demeaned against the mean of that same signal across all
  other universe symbols with a value on that date, not against that
  symbol's own historical mean

#### Scenario: All four horizons are reported, not just the best one
- **WHEN** the evaluation completes
- **THEN** results for all four horizons (5, 10, 21, 63 sessions) are
  reported together, so a horizon is not selected after the fact based on
  which one happened to score best

### Requirement: Decile-ranking evaluation, not correlation alone
The system SHALL evaluate a top-decile-minus-bottom-decile ranking
construction at each horizon, in addition to the raw cross-sectional
correlation, and SHALL report the correlation's sign stability across
walk-forward folds.

#### Scenario: Decile spread is reported per fold
- **WHEN** the evaluation runs
- **THEN** each fold's top-decile-minus-bottom-decile average forward
  return is reported individually, not only pooled across all folds

#### Scenario: Sign instability is surfaced, not averaged away
- **WHEN** a horizon's correlation or decile spread changes sign across
  folds
- **THEN** that instability is reported explicitly (e.g. per-fold sign
  alongside the pooled mean), consistent with how
  `docs/DISCUSSION_model_direction.md`'s single-ticker findings reported
  sign instability rather than only a pooled average

### Requirement: Effective breadth is reported alongside raw correlation
The system SHALL compute and report the modelling universe's mean pairwise
cross-sectional correlation (ρ̄) of returns, and an effective-breadth
estimate derived from it, alongside each horizon's raw correlation figure.

#### Scenario: Effective breadth is computed on the current universe
- **WHEN** the evaluation runs
- **THEN** ρ̄ is computed from the 208-symbol modelling universe's own
  return data, not carried over from the smaller 15-symbol figure measured
  earlier in `docs/DISCUSSION_model_direction.md`

#### Scenario: A high ρ̄ is reported as a caveat, not hidden
- **WHEN** ρ̄ implies an effective breadth materially smaller than the
  universe's nominal symbol count
- **THEN** the report states both the nominal count and the
  effective-breadth estimate together, so a headline correlation number is
  never presented without the caveat that narrows it

### Requirement: The evaluation is durable and re-runnable
The system SHALL implement this evaluation as a script under
`backend/scripts/` that can be re-run to reproduce its own results, rather
than as an ephemeral, one-off analysis whose code is discarded after use.

#### Scenario: Re-running the script reproduces the reported numbers
- **WHEN** the script is re-run against an unchanged database
- **THEN** it produces the same figures as the run whose numbers were
  recorded in the verdict, modulo any randomness that is itself seeded and
  documented

#### Scenario: The script requires no manual setup beyond what other backend/scripts entries require
- **WHEN** the script is invoked the way existing scripts under
  `backend/scripts/` (e.g. `report_ingest_outcomes.py`) are invoked
- **THEN** it runs to completion without additional undocumented setup
  steps

### Requirement: A plain verdict is produced regardless of outcome
The system SHALL produce a written verdict stating whether the measured
effect holds at scale, at what confidence, and what using it would require
— and SHALL state a negative or inconclusive result as plainly as a
positive one.

#### Scenario: A negative result is reported, not omitted
- **WHEN** the measured effect does not hold at scale (e.g. the decile
  spread is not sign-stable across folds, or effective breadth erases the
  correlation's apparent headroom)
- **THEN** the verdict states this plainly as the finding, rather than the
  evaluation being reframed, re-parameterized, or left unreported until a
  positive result is found

#### Scenario: The verdict names concrete prerequisites for using a positive result
- **WHEN** the measured effect does hold at scale
- **THEN** the verdict names what would be required to act on it (e.g. a
  ranking/screening surface that does not exist today, portfolio
  construction guidance, holdings data not yet collected) rather than
  implying the finding alone is ready to serve to a user

### Requirement: This evaluation makes no change to any served surface
The system SHALL NOT modify `backend/data/models/pooled_xgb_model.json`,
any API response, any UI component, or any of the six non-negotiable
domain rules as part of this evaluation.

#### Scenario: The production model artifact is untouched
- **WHEN** the evaluation runs, including any walk-forward training it
  performs internally for its own signals
- **THEN** `backend/data/models/pooled_xgb_model.json` is not read for
  writing and not modified

#### Scenario: No endpoint or component changes behavior
- **WHEN** the evaluation is added to the codebase
- **THEN** no existing API endpoint's response shape or behavior changes,
  and no frontend component changes, as a result
