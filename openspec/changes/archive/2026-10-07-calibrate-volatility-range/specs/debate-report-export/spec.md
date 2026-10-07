## ADDED Requirements

### Requirement: Export Summary states the typical 5-session move and its coverage
The Summary section of an exported report SHALL contain, in place of the `**Volatility range**: ±X.X% (5 trading sessions)` line of the earlier template, the line `**Typical 5-session move**: ±X.X% (about 2 in 3 recent 5-session moves stayed within this range)` when `range_5s_pct` is not null and `range_coverage` is 0.68; the coverage phrase follows the same derivation as the panel ("about N%" for other values). When `range_coverage` is null the parenthetical SHALL read `(coverage not established for this stock)`. When `range_5s_pct` is null the line SHALL be omitted entirely with no placeholder. The line MUST NOT print `sigma_daily_pct` as a 5-session figure. This requirement supersedes the `**Volatility range**` template line and the scenario "Volatility range is omitted when unavailable" in the requirement "Markdown export structure is NotebookLM-optimised".

#### Scenario: Calibrated band in the report
- **WHEN** a report is written for a result with `range_5s_pct` 5.3 and `range_coverage` 0.68
- **THEN** the Summary contains `**Typical 5-session move**: ±5.3% (about 2 in 3 recent 5-session moves stayed within this range)` and no `**Volatility range**` line

#### Scenario: Uncalibrated band in the report
- **WHEN** `range_5s_pct` is 5.3 and `range_coverage` is null
- **THEN** the Summary line ends with `(coverage not established for this stock)`

#### Scenario: Band omitted when not served
- **WHEN** the debate result has `range_5s_pct` null
- **THEN** the Summary has no typical-move line and no placeholder
