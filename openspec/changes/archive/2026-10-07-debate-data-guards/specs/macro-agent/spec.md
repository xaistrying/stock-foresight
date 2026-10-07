## ADDED Requirements

### Requirement: Macro Agent compares the ticker and VN-Index over the same dates
Signal 2 (the ticker's own return relative to VN-Index) SHALL be computed over the two dates `d_first` and `d_last`, the dates of the ticker's 20th-latest and latest stored closes. The VN-Index return SHALL use the VN-Index closes dated exactly `d_first` and `d_last`. Both series SHALL keep their dates; alignment by list position is not permitted. If the VN-Index data has no close on either date (a window the fetched range does not cover, or a calendar mismatch), the window is mismatched: signal 2 SHALL cast no vote and the reasoning SHALL state that the ticker window `<d_first>..<d_last>` is not covered by the VN-Index data. When it is computed, the signal text SHALL include both dates.

#### Scenario: Stale ticker compared over its own window
- **WHEN** the ticker's last stored close is 2026-10-02 and the VN-Index data runs to 2026-10-06
- **THEN** the relative return uses the VN-Index closes of the ticker's `d_first` and 2026-10-02, not the index's last 20 positions

#### Scenario: Matching windows
- **WHEN** both series cover the ticker's `d_first` and `d_last`
- **THEN** signal 2 votes by the existing ±1 percentage point rule and states the two dates

#### Scenario: Index lacks an endpoint
- **WHEN** the VN-Index series has no close on `d_first`
- **THEN** signal 2 casts no vote and the reasoning says the window is not covered

#### Scenario: Unit test with position-shifted index
- **WHEN** the VN-Index series is shifted by 3 sessions relative to the ticker's
- **THEN** the computed relative return differs from the positional one and equals the by-date one

### Requirement: Macro Agent with no counted signal is degraded, not neutral
When none of the four signals casts a vote, the MacroAgent SHALL return a position with `degraded_reason: "no_input"` instead of a default `neutral` stance, and its reasoning SHALL say that no macro signal was available.

#### Scenario: Every market-data fetch fails
- **WHEN** VN-Index, USD/VND and foreign flow are all unavailable
- **THEN** the Macro position is degraded with `no_input`

#### Scenario: Foreign flow provisional and others unavailable
- **WHEN** only the provisional foreign-flow signal is available and the other three are not
- **THEN** no signal is counted and the Macro position is degraded with `no_input`

#### Scenario: One counted signal
- **WHEN** exactly one signal votes
- **THEN** the Macro position is live with the stance from that vote
