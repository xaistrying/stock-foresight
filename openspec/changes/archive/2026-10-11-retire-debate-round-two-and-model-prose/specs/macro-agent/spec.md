## MODIFIED Requirements

### Requirement: Macro Agent falls back gracefully when VN-Index is not in OHLCV
The MacroAgent SHALL check whether `VNINDEX` is present in the `ohlcv` table. If not, it SHALL fetch VN-Index data via the vnstock market API before computing the trend signal. If the fetch also fails, VN-Index trend is excluded from the stance vote and the reasoning lists the signal as unavailable.

#### Scenario: VNINDEX not in local OHLCV
- **WHEN** `VNINDEX` has no rows in the `ohlcv` table
- **THEN** the agent fetches VN-Index data via vnstock market API and proceeds normally

#### Scenario: VN-Index data completely unavailable
- **WHEN** local OHLCV has no VNINDEX rows and the vnstock API call also fails
- **THEN** VN-Index trend is omitted from the stance calculation; stance is derived from the remaining 3 signals; reasoning lists `VN-Index trend: unavailable`

### Requirement: Macro Agent foreign flow is market-wide, latest-session, and degrades to unavailable
The free vnstock API provides no foreign-flow history and no per-ticker foreign-trade series, so the MacroAgent SHALL derive signal 4 from one price-board request for the sample of large caps and describe it as market-wide, latest session. The price board's foreign values are cumulative-so-far during the session and still move after the close, so the signal SHALL be shown in the reasoning at all times but SHALL cast a vote only once the board has settled: on a weekday, not before 15:15 Vietnam time (UTC+7); on a weekend the last session's figure counts. Until then it SHALL be labelled provisional ("session in progress or just closed, not counted in the stance vote"); once settled, "latest session, final". The MacroAgent SHALL read the clock before starting the fetch, and the clock value MUST be timezone-aware. When the signal is unavailable it SHALL cast no vote and the reasoning SHALL say it is unavailable; failures SHALL log a warning once per process and thereafter at debug level.

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

## ADDED Requirements

### Requirement: Macro Agent reasoning lists the computed signal values (Rule 5)
The MacroAgent SHALL produce `reasoning` as one bullet per signal, in this order: `VN-Index trend: <value>`, `Relative performance: <value>`, `USD/VND: <value>`, `Market foreign flow (latest session): <value>`, where `<value>` is the signal text the agent computed or `unavailable`. The relative-performance value SHALL describe the ticker's own return against VN-Index over the two stated dates and SHALL NOT call it a sector comparison; the foreign-flow value SHALL describe a market-wide, latest-session figure and, when it is provisional, SHALL carry the provisional label and no direction word. The MacroAgent SHALL NOT call a language model, and its bullets are computed values, not model-written text (Rule 5).

#### Scenario: Every signal has a line
- **WHEN** the four signals are computed
- **THEN** reasoning has four bullets in the stated order, each with its value

#### Scenario: Provisional signal gets no direction
- **WHEN** the foreign-flow figure is marked "not counted in the stance vote"
- **THEN** its bullet states its size and the provisional label and does not call it bullish or bearish

#### Scenario: A window the index does not cover
- **WHEN** the VN-Index data has no close on the ticker's `d_first`
- **THEN** the relative-performance bullet reads `unavailable` and names the ticker window `<d_first>..<d_last>` as not covered by the VN-Index data, and signal 2 casts no vote

#### Scenario: No model is needed
- **WHEN** the agent runs while every language-model call would raise
- **THEN** it returns its position with the four bullets and is not degraded

## REMOVED Requirements

### Requirement: Macro Agent uses LLM only to translate computed signals into readable reasoning
**Reason**: Owner answer for step 1 of `docs/DISCUSSION_describe_not_vote_redesign.md`: Macro reasoning becomes the values list it already used as a fallback. A model paraphrase of four computed numbers added wording risk and a model call, not evidence.
**Migration**: The new requirement "Macro Agent reasoning lists the computed signal values (Rule 5)" defines the bullets. The provisional-signal rule moves into it; the Round 2 prompt clause goes with Round 2 (see `debate-engine`).
