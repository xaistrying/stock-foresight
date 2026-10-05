## ADDED Requirements

### Requirement: Macro Agent computes quantitative macro signals from vnstock data
The MacroAgent SHALL compute four signals entirely from vnstock API data (the 4.x `Market` API) or the existing OHLCV table — no scraping, no LLM data fetching:
1. VN-Index 20-session price trend (slope sign: up/flat/down)
2. The ticker's own 20-session return relative to VN-Index (outperform/inline/underperform, ±1 percentage point). No sector index exists in the data, so this is not a sector comparison and MUST NOT be described as one
3. USD/VND 5-session change (strengthening/stable/weakening for VND)
4. Market-wide foreign net buy/sell value for the latest session, summed over a sample of 30 large caps from the VCI price board: net inflow / net outflow / neutral by the net's share of gross foreign turnover (beyond ±10%, a provisional threshold)

Each signal maps to a partial stance contribution. The overall stance is majority vote across the signals that are available.

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
The free vnstock API provides no foreign-flow history and no per-ticker foreign-trade series, so the MacroAgent SHALL derive signal 4 from one price-board request for the sample of large caps and describe it as market-wide, latest session (partial while the market is open). When it is unavailable the signal SHALL cast no vote and the reasoning SHALL say it is unavailable; failures SHALL log a warning once per process and thereafter at debug level.

#### Scenario: Net foreign selling
- **WHEN** the summed foreign net value is -90B VND of 640B gross turnover (-14%)
- **THEN** signal 4 votes bearish and the reasoning cites the net value and its scale

#### Scenario: Negligible flow
- **WHEN** net foreign value is within ±10% of gross foreign turnover
- **THEN** signal 4 votes neutral

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
The MacroAgent SHALL pass the four computed signal values to an LLM with a prompt instructing it to produce plain-language bullet reasoning from those values. The LLM MUST NOT be used to fetch or independently assess macro conditions — it translates already-computed numbers into readable bullets only. The prompt MUST describe signal 2 as the ticker's own return and signal 4 as market-wide and latest-session.

#### Scenario: LLM produces reasoning from computed signals
- **WHEN** VN-Index 20-session slope is +2.3%, the ticker's relative return is +1.1%, USD/VND -0.3%, market-wide foreign flow is net +12B VND
- **THEN** reasoning includes 3–4 bullets translating these values into plain language without inventing additional macro context
