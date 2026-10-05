## MODIFIED Requirements

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

### Requirement: Macro Agent uses LLM only to translate computed signals into readable reasoning
The MacroAgent SHALL pass the four computed signal values to an LLM with a prompt instructing it to produce plain-language bullet reasoning from those values. The LLM MUST NOT be used to fetch or independently assess macro conditions — it translates already-computed numbers into readable bullets only. The prompt MUST describe signal 2 as the ticker's own return and signal 4 as market-wide and latest-session. The prompt MUST tell the model that a signal marked "not counted in the stance vote" is provisional context and that it MUST NOT infer a direction from it, and the Round 2 prompt MUST tell the model that a position resting on provisional or partial data must not move a stance.

#### Scenario: LLM produces reasoning from computed signals
- **WHEN** VN-Index 20-session slope is +2.3%, the ticker's relative return is +1.1%, USD/VND -0.3%, market-wide foreign flow is net +12B VND
- **THEN** reasoning includes 3–4 bullets translating these values into plain language without inventing additional macro context

#### Scenario: Provisional signal gets no direction
- **WHEN** the foreign-flow figure is marked "not counted in the stance vote"
- **THEN** the reasoning may mention its size but does not call it bullish or bearish, and the prompt for Round 2 states that provisional data must not move a stance
