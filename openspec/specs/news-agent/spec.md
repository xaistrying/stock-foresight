# news-agent

## Purpose

TBD

## Requirements

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

### Requirement: News Agent sector tags exclude look-alike stories
The `[sector]` tag takes at most four of the agent's headline slots, so a story that merely contains a sector word SHALL NOT be tagged as sector news. Matching is on the headline title, using Vietnamese keywords per sector, and the NewsAgent SHALL apply these precision rules:

1. For the banking sector, the bare words "ngân hàng" and "huy động" SHALL NOT match on their own. A banking headline SHALL match on a sector phrase (for example "tín dụng", "nợ xấu", "lãi suất huy động", "tiền gửi", "ngành/nhóm/cổ phiếu/các ngân hàng", "hệ thống ngân hàng", "ngân hàng thương mại", "lợi nhuận ngân hàng", "LDR", "NIM"), on the full name of a peer Vietnamese bank (for example Vietcombank, Techcombank, VPBank), or on a generic bank as the subject of results or capital news ("ngân hàng …" followed within 40 characters by "báo lãi", "lợi nhuận", "lãi quý", "tăng vốn", "chia cổ tức" or "phát hành trái phiếu"). Bare bank ticker symbols (for example ACB, VIB, MSB) SHALL NOT count as peer-bank names, because they also appear as symbols in stock-list stories.
2. For the banking sector, a headline about a foreign bank SHALL NOT match (the country name — Mỹ, Hàn Quốc, Trung Quốc, Nhật Bản, châu Âu, Đức, Thụy Sĩ, Ấn Độ, Thái Lan, Singapore, Indonesia — within 25 characters of "ngân hàng", matched case-sensitively; Britain is not in the list because "Anh" is also the Vietnamese pronoun).
3. For a sector outside banking, insurance, financial services and real estate, a headline whose subject is a bank (its title contains "ngân hàng") SHALL NOT be tagged `[sector]`, except when "ngân hàng" is followed by "thế giới", "phát triển châu Á", "nhà nước" or "trung ương" (the World Bank, the ADB, the State Bank, central banks). Banking, insurance, financial services and real estate keep headlines that mention banks. Headlines that match the market keywords (for example "Ngân hàng Nhà nước", rates) are still tagged `[market]`.

#### Scenario: A bare mention of a bank is not banking sector news
- **WHEN** a headline reads "Loạt ngân hàng Hàn Quốc liên tiếp bị tấn công mạng" or "Ngân hàng hạ giá rao bán 50% nhà máy nông sản …" and the ticker is a bank
- **THEN** it is not tagged `[sector]`

#### Scenario: Banking phrases, peer brands and bank earnings are sector news
- **WHEN** a headline reads "Tín dụng tăng gần 11,6% sau 9 tháng", "Ngân hàng VPBank phát hành trái phiếu" or "Ngân hàng X báo lãi quý 3 tăng 30%" and the ticker is a bank
- **THEN** it is tagged `[sector]`

#### Scenario: A list of stock symbols is not banking news
- **WHEN** a headline reads "BSC: PNJ, FPT và MSB có nguy cơ bị loại khỏi rổ Diamond"
- **THEN** it is not tagged as banking sector news for a bank ticker

#### Scenario: Foreign banks are not banking sector news
- **WHEN** a headline reads "Các ngân hàng Hàn Quốc bị tấn công mạng" and the ticker is a bank
- **THEN** it is not tagged `[sector]`

#### Scenario: The pronoun "anh" does not make a Vietnamese bank story foreign
- **WHEN** a headline reads "Các ngân hàng tăng lãi suất huy động, anh em nhà đầu tư chú ý"
- **THEN** it is tagged `[sector]` for a bank ticker

#### Scenario: A story about a bank is not news about a non-financial sector
- **WHEN** a headline reads "Ngân hàng hạ giá rao bán 50% nhà máy nông sản và thép" and the ticker's sector is food and beverage or basic resources
- **THEN** it is not tagged `[sector]`

#### Scenario: Financial sectors keep stories that mention banks
- **WHEN** a headline reads "Ngân hàng siết cho vay bất động sản" and the ticker's sector is real estate
- **THEN** it is tagged `[sector]`

#### Scenario: World Bank and ADB outlooks still reach other sectors
- **WHEN** a headline reads "Ngân hàng Thế giới dự báo giá dầu giảm trong năm tới" and the ticker's sector is oil and gas
- **THEN** it is tagged `[sector]`
