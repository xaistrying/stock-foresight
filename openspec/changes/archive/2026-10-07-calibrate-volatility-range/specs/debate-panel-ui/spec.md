## ADDED Requirements

### Requirement: Panel range line states the typical 5-session move and its coverage
At Level 1 of a populated panel, when `result.range_5s_pct` is not null, the DebatePanel SHALL render a line "Typical 5-session move: ±X.X% (about 2 in 3 recent 5-session moves stayed within this range)" with one decimal. The coverage phrase SHALL be derived from `result.range_coverage`: 0.68 renders "about 2 in 3", any other value renders "about N%" with N rounded to the nearest 5. When `range_coverage` is null the line SHALL read "Typical 5-session move: ±X.X% (coverage not established for this stock)". When `range_5s_pct` is null the line SHALL be omitted with no placeholder. The line MUST NOT use the words "expected", "confidence" or "forecast", MUST NOT display `sigma_daily_pct`, and MUST appear inside the panel that carries the Rule 6 disclaimer. The wording is a proposal for the copy review owned by `align-rules-and-disclaimer`.

#### Scenario: Calibrated band shown with its coverage
- **WHEN** the result has `range_5s_pct` 5.3 and `range_coverage` 0.68
- **THEN** Level 1 shows "Typical 5-session move: ±5.3%" and "about 2 in 3"

#### Scenario: Other nominal coverage
- **WHEN** `range_coverage` is 0.8
- **THEN** the line says "about 80%"

#### Scenario: Uncalibrated ticker
- **WHEN** `range_5s_pct` is 5.3 and `range_coverage` is null
- **THEN** the line says "coverage not established for this stock" and does not say "about 2 in 3"

#### Scenario: No band
- **WHEN** `range_5s_pct` is null
- **THEN** no range line is rendered
