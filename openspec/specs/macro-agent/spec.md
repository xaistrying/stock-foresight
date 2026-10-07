# macro-agent

## Purpose

TBD

## Requirements

### Requirement: Macro Agent computes quantitative macro signals from vnstock data
The MacroAgent SHALL compute four signals entirely from vnstock API data (the 4.x `Market` API) or the existing OHLCV table — no scraping, no LLM data fetching:
1. VN-Index 20-session price trend (slope sign: up/flat/down)
2. The ticker's own 20-session return relative to VN-Index (outperform/inline/underperform, ±1 percentage point). No sector index exists in the data, so this is not a sector comparison and MUST NOT be described as one
3. USD/VND 5-session change (strengthening/stable/weakening for VND)
4. Market-wide foreign net buy/sell value for the latest session, summed over a sample of 30 large caps from the VCI price board: net inflow / net outflow / neutral by the net's share of gross foreign turnover (beyond ±10%, a provisional threshold). It is counted in the vote only once the board has settled after the close (see the foreign-flow requirement)

Each signal maps to a partial stance contribution. The overall stance is majority vote across the signals that are available and counted.

#### Scenario: Macro environment broadly favorable
- **WHEN** VN-Index trend is up, the ticker outperforms the index, VND is stable, and market-wide foreign flow is a net inflow
- **THEN** stance is `bull` with reasoning citing the four signals

#### Scenario: Mixed macro signals
- **WHEN** VN-Index is flat but market-wide foreign flow is a net outflow and USD is strengthening
- **THEN** stance is `neutral` or `bear` depending on majority; reasoning cites which signals conflict

### Requirement: Macro Agent falls back gracefully when VN-Index is not in OHLCV
The MacroAgent SHALL check whether `VNINDEX` is present in the `ohlcv` table. If not, it SHALL fetch VN-Index data via the vnstock market API before computing the trend signal. If the fetch also fails, VN-Index trend is excluded from the stance vote and the reasoning notes its absence.

#### Scenario: VNINDEX not in local OHLCV
- **WHEN** `VNINDEX` has no rows in the `ohlcv` table
- **THEN** the agent fetches VN-Index data via vnstock market API and proceeds normally

#### Scenario: VN-Index data completely unavailable
- **WHEN** local OHLCV has no VNINDEX rows and the vnstock API call also fails
- **THEN** VN-Index trend is omitted from the stance calculation; stance is derived from the remaining 3 signals; reasoning notes "VN-Index data unavailable"

### Requirement: Macro Agent foreign flow is market-wide, latest-session, and degrades to unavailable
The free vnstock API provides no foreign-flow history and no per-ticker foreign-trade series, so the MacroAgent SHALL derive signal 4 from one price-board request for the sample of large caps and describe it as market-wide, latest session. The price board's foreign values are cumulative-so-far during the session and still move after the close, so the signal SHALL be shown to the LLM at all times but SHALL cast a vote only once the board has settled: on a weekday, not before 15:15 Vietnam time (UTC+7); on a weekend the last session's figure counts. Until then it SHALL be labelled provisional ("session in progress or just closed, not counted in the stance vote"); once settled, "latest session, final". The MacroAgent SHALL read the clock before starting the fetch, and the clock value MUST be timezone-aware. When the signal is unavailable it SHALL cast no vote and the reasoning SHALL say it is unavailable; failures SHALL log a warning once per process and thereafter at debug level.

#### Scenario: Net foreign selling after the board has settled
- **WHEN** the summed foreign net value is -90B VND of 640B gross turnover (-14%) at 16:00 on a weekday
- **THEN** signal 4 votes bearish and the reasoning cites the net value and its scale, labelled "latest session, final"

#### Scenario: Negligible flow
- **WHEN** net foreign value is within ±10% of gross foreign turnover and the board has settled
- **THEN** signal 4 votes neutral

#### Scenario: Session in progress
- **WHEN** the debate runs at 10:00 on a weekday and the figure is -15% of foreign turnover
- **THEN** the figure appears in the reasoning labelled provisional and casts no vote; the stance is decided by the other signals

#### Scenario: Just after the close
- **WHEN** the debate runs between 15:00 and 15:15 on a weekday
- **THEN** the figure is still provisional and casts no vote

#### Scenario: Weekend
- **WHEN** the debate runs on a Saturday or Sunday
- **THEN** the board holds the last session's final figure and signal 4 votes

#### Scenario: Clock read before the fetch
- **WHEN** the price-board request takes several seconds
- **THEN** whether the figure is provisional is decided from the time the request started, not the time it finished

#### Scenario: No foreign turnover or no data
- **WHEN** the price board has no foreign turnover (pre-open, a holiday), lacks the foreign value columns, or the request fails
- **THEN** signal 4 is unavailable and casts no vote; a missing-column or request failure is logged

### Requirement: Macro Agent market-data fetches are non-blocking and bounded
The MacroAgent SHALL run its market-data fetches off the event loop, in parallel, each with a deadline (20 seconds); a fetch that exceeds it or fails SHALL degrade that signal to unavailable. vnai's rate limiter ends the process with `sys.exit()`; the fetchers SHALL catch that exit (as bulk ingestion does) and SHALL re-raise any other exit request.

#### Scenario: Source hangs
- **WHEN** a market-data source does not respond within the deadline
- **THEN** that signal is unavailable and the other signals and the debate proceed

#### Scenario: Rate limit exit
- **WHEN** vnai's rate limiter calls `sys.exit()` during a fetch
- **THEN** the fetch returns unavailable and the server keeps running

### Requirement: Macro Agent uses LLM only to translate computed signals into readable reasoning
The MacroAgent SHALL pass the four computed signal values to an LLM with a prompt instructing it to produce plain-language bullet reasoning from those values. The LLM MUST NOT be used to fetch or independently assess macro conditions — it translates already-computed numbers into readable bullets only. The prompt MUST describe signal 2 as the ticker's own return and signal 4 as market-wide and latest-session. The prompt MUST tell the model that a signal marked "not counted in the stance vote" is provisional context and that it MUST NOT infer a direction from it, and the Round 2 prompt MUST tell the model that a position resting on provisional or partial data must not move a stance.

#### Scenario: LLM produces reasoning from computed signals
- **WHEN** VN-Index 20-session slope is +2.3%, the ticker's relative return is +1.1%, USD/VND -0.3%, market-wide foreign flow is net +12B VND
- **THEN** reasoning includes 3–4 bullets translating these values into plain language without inventing additional macro context

#### Scenario: Provisional signal gets no direction
- **WHEN** the foreign-flow figure is marked "not counted in the stance vote"
- **THEN** the reasoning may mention its size but does not call it bullish or bearish, and the prompt for Round 2 states that provisional data must not move a stance

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
