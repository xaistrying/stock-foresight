## ADDED Requirements

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
