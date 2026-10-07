# model-training-pipeline

## Purpose

TBD

## Requirements

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
