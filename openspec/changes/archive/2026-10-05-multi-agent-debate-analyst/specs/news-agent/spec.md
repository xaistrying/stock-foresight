## ADDED Requirements

### Requirement: News Agent reads recent VN financial headlines from public RSS feeds, tagged by relevance
The NewsAgent SHALL fetch the public RSS feeds of VnExpress (kinh doanh), CafeF (thị trường chứng khoán) and Vietstock (cổ phiếu) via async HTTP (httpx) and use items published in the past 7 calendar days. Each headline SHALL be tagged `[ticker]` (names the ticker symbol as a whole word in its title or snippet), `[sector]` (its title matches keywords for the ticker's sector, derived from `icb_code2` in the universe table) or `[market]` (market-wide or macro news: VN-Index, rates, FX, GDP, foreign flow); headlines matching none of these SHALL be dropped. At most 5 `[ticker]`, 4 `[sector]` and 10 `[market]` headlines SHALL be passed on, ticker first, then sector, then market. The agent MUST NOT use any form of authenticated API — public feeds only.

#### Scenario: Headlines found for ticker
- **WHEN** at least one headline names the ticker symbol in the last 7 days
- **THEN** those headlines, tagged `[ticker]`, are passed to the LLM first, followed by sector and market headlines

#### Scenario: No headlines name the ticker
- **WHEN** no headline names the ticker in the last 7 days
- **THEN** `[sector]` and `[market]` headlines are used if available; if none exist, the agent returns `stance: neutral` with `reasoning: ["No recent news found for this ticker, its sector or the market."]`

#### Scenario: Only market-wide headlines
- **WHEN** the headlines are all `[market]` (for example a VN-Index decline or a GDP release)
- **THEN** the LLM is told they are context rather than evidence about the company, its bullets say so, and the stance stays `neutral` unless the headlines themselves make a case for `bull` or `bear`

#### Scenario: Index and foreign-flow news is prioritised
- **WHEN** more `[market]` headlines exist than slots
- **THEN** headlines about the VN-Index fill up to 4 slots first, then headlines about foreign investor flow ("khối ngoại") fill 2 reserved slots with market-wide recaps (a week, a session or HOSE in the title) ahead of one-stock stories, and the remaining slots go to other market news (rates, FX, GDP), newest first within each group

#### Scenario: One feed fails
- **WHEN** one feed raises an exception, returns a non-2xx status, is malformed, or exceeds its time or size bound
- **THEN** it is logged and skipped, and the headlines from the other feeds are used

#### Scenario: Every feed fails
- **WHEN** all feeds fail
- **THEN** the agent returns `stance: neutral` with `reasoning: ["News data unavailable — could not fetch the news feeds."]`; the debate engine proceeds without blocking

### Requirement: News Agent uses LLM to extract bullish/bearish signals from headlines
The NewsAgent SHALL pass collected headlines to the LLM with a structured prompt that instructs the model to extract signals relevant to the ticker. The prompt MUST instruct the model to derive signals only from the provided headlines, not from its training knowledge about the ticker, and MUST tell the model that `[market]` headlines are context, not evidence about the company. Output is `{ stance, reasoning }`.

#### Scenario: LLM identifies negative news signals
- **WHEN** headlines mention profit warning, regulatory action, or sector downturn for the ticker
- **THEN** stance is `bear` with reasoning bullets citing specific headline content

#### Scenario: LLM finds no clear signal in headlines
- **WHEN** headlines are unrelated to the ticker's prospects or are purely factual/neutral
- **THEN** stance is `neutral` with reasoning `["Headlines present no clear directional signal for this ticker"]`

### Requirement: News Agent treats feed content as untrusted
Feed content reaches an LLM prompt, so the NewsAgent SHALL parse feed XML with a parser that rejects entity declarations (defusedxml); bound each feed fetch to 15 seconds in total, 2 MB of decoded content and 3 redirects; strip markup, control characters and invisible Unicode characters from titles and snippets and cap their length (200 and 160 characters); drop headlines dated more than a day in the future; and instruct the LLM to ignore any instructions that appear inside headlines.

#### Scenario: Entity-expansion feed
- **WHEN** a feed declares XML entities (for example an entity-expansion payload)
- **THEN** it is rejected as a failed feed, not parsed

#### Scenario: Hostile characters in a headline
- **WHEN** a headline contains HTML, double-escaped tags, zero-width or invisible tag characters, or line breaks
- **THEN** the text passed to the LLM contains none of them and is a single line

### Requirement: News Agent output is labeled "News Context" — not "Market Sentiment" (Rule 5)
The NewsAgent's output MUST be labeled "News Context" in all UI surfaces and in the exported `.md` report. The label "Market Sentiment" MUST NOT be used for NewsAgent output. The TechnicalAgent's signal continues to use "Technical Signal" (Rule 5 preserved for technical proxy). This labeling MUST be enforced at the component level in `DebatePanel`.

#### Scenario: News context label in UI
- **WHEN** the debate result is rendered in the DebatePanel at Level 2
- **THEN** the NewsAgent's card header reads "News Context" and the TechnicalAgent's card header reads "Technical Signal"

#### Scenario: News context label in markdown export
- **WHEN** the `.md` report is generated
- **THEN** the NewsAgent section is headed "News Context", never "Market Sentiment"
