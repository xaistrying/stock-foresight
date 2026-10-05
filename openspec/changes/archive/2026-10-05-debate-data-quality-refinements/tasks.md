## 1. Export: split label

- [x] 1.1 In `export.py`, print `**Agreement**: Split (3 different positions)` for a `split` agreement level; keep `(N of 3 agents)` for `majority` and `unanimous`
- [x] 1.2 Tests in `test_debate_export_api.py`: the split label, and guards that majority and unanimous still count the agreeing agents

## 2. Macro agent: foreign flow votes only once settled

- [x] 2.1 Add `_foreign_flow_is_settling(now)` to `macro.py`: true on weekdays from 09:00 until 15:15 Vietnam time (UTC+7); a naive datetime raises `ValueError`
- [x] 2.2 Keep the foreign-flow signal in the reasoning at all times, but append its vote only when the board is not settling; label it "provisional: session in progress or just closed, not counted in the stance vote" or "latest session, final"
- [x] 2.3 Read the clock before the `asyncio.gather` of the fetches, not after
- [x] 2.4 Prompts: a signal marked "not counted in the stance vote" gets no inferred direction; Round 2 must not let provisional or partial data move a stance
- [x] 2.5 Tests in `test_macro_signals.py`: boundaries (09:00, 14:59, 15:00, 15:14, 15:15, a UTC input, Saturday, Sunday), no vote in session, same flow votes once settled, clock read before the fetch, naive datetime rejected, prompt wording; pin the clock in the two voting tests in `test_debate_agents.py`

## 3. News agent: sector tag precision

- [x] 3.1 Banking keywords in `news_feeds.py`: replace bare `ngân hàng` / `huy động` with phrases, full peer-bank brand names and a "bank + earnings/capital" pattern
- [x] 3.2 Exclude headlines about foreign banks for the banking sector (country names case-sensitive, Britain omitted)
- [x] 3.3 For sectors outside `FINANCIAL_SECTORS`, ignore headlines whose subject is a bank, exempting World Bank, ADB, State Bank and central banks
- [x] 3.4 Keep short bank tickers (ACB, VIB, OCB, SHB, MSB) out of the brand list (a regression found on live feeds: a basket story listing symbols was tagged banking news)
- [x] 3.5 Tests in `test_news_feeds.py` for each rule above, using the real noisy headlines

## 4. Verification

- [x] 4.1 Backend suite passes (396 tests)
- [x] 4.2 Live checks: post-close foreign-flow readings sampled at 15:12–15:20 Vietnam time (identical); VPB and SAB sector slots re-checked against the live feeds
- [x] 4.3 Independent code review addressed: clock order, prompt rule, bank-news recall, World Bank exemption, naive datetimes
