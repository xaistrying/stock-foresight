---
name: vnstock
description: Coding assistant context for the vnstock Python library (free tier) — Vietnamese stock market data. Use whenever the user asks to fetch stock prices/OHLCV, company info, financial statements, indices, gold/exchange-rate data, or otherwise write Python code against vnstock for VN30/HOSE/HNX/UPCOM stocks.
---

# Vnstock (Free Tier) — Project Context

Source: distilled from `AGENTS.md` and `docs/` in the
[vnstock-hq/vnstock-agent-guide](https://github.com/vnstock-hq/vnstock-agent-guide) repo, scoped to
the **free/community tier** (the `vnstock` library only — not `vnstock_data`, `vnstock_ta`,
`vnstock_news`, or `vnstock_pipeline`, which all require a sponsor account).

Users of this project use the **free tier only**. Always write code against `vnstock`. Do not
suggest `vnstock_data` or other sponsor libraries unless the user directly asks about upgrading.

## Installation

```bash
pip install -U vnstock          # stable release (PyPI) — use this by default
pip install git+https://github.com/thinh-vu/vnstock  # latest from GitHub, may be unstable
```

Requires Python 3.10+ (3.12+ recommended). Dependencies (pandas, requests, beautifulsoup4, lxml,
pydantic, tenacity, python-dateutil, aiohttp, tqdm, packaging, python-dotenv) install automatically.

## Architecture: Unified UI is the standard (since v3.5.1+)

Always use the **Unified UI** (`vnstock.ui`) instead of the low-level Legacy API (`Quote`,
`Company`, `Listing`, `Finance`, `Trading`) unless you need a specific method that only exists in
the Legacy API (see "Legacy API" section below).

```python
from vnstock.ui import Reference, Market, Fundamental, Retail

ref = Reference()
mkt = Market()
fun = Fundamental()
ret = Retail()
```

Discover the API by calling:

```python
from vnstock.ui import show_api, show_doc

show_api()                    # print the full API tree
show_doc("Market.equity")     # details on a method's params/return type
```

Underlying Adapter Pattern: `Unified API Layer -> Provider Registry -> Explorer (VCI, KBS, MSN) /
Connector (FMP, DNSE)`. The Provider Registry automatically picks the best source and falls back
if one fails.

## The 4 data domains available on the free tier

| Domain | Role | Import |
|---|---|---|
| `Reference` | Static catalog: stock lists, indices, company profiles | `from vnstock.ui import Reference` |
| `Market` | Dynamic price data: OHLCV, quotes, trades | `from vnstock.ui import Market` |
| `Fundamental` | Financial statements, valuation ratios | `from vnstock.ui import Fundamental` |
| `Retail` | Gold prices, exchange rates | `from vnstock.ui import Retail` |

The `Macro`, `Insights` (screener, ranking), and `Analytics` (market-wide valuation) domains are
**sponsor-only (`vnstock_data`)** — do not write code that assumes these domains exist on free
`vnstock`. The screener is currently **non-functional** even in advanced usage (TCBS API changed
and now requires auth) — if the user needs to filter stocks, pull `ratio()` per symbol and filter
with pandas instead of relying on a screener.

### Reference — catalog lookups

```python
from vnstock.ui import Reference
ref = Reference()

ref.equity.list()                          # all listed stock symbols (source='kbs' default)
ref.equity.list_by_exchange(exchange="HOSE")
ref.equity.list_by_group(group="VN30")
ref.equity.list_by_industry()

ref.index.list()                           # index list (VNINDEX, VN30...)
ref.index.members("VN30")                  # constituent symbols of an index

vcb = ref.company("VCB")
vcb.info(); vcb.shareholders(); vcb.officers(); vcb.subsidiaries()
vcb.ownership(); vcb.insider_trading(); vcb.capital_history()
vcb.news(); vcb.events()

ref.etf.list(); ref.futures.list(); ref.warrant.list(); ref.bond.list(); ref.fund.list()

ref.search.symbol("Ngân hàng")             # search symbols by keyword
```

> The VCI source for `list_by_industry()` is unstable on Google Colab (bot-blocked) — the system
> automatically falls back to KBS in that case.

### Market — price & trades

```python
from vnstock.ui import Market
mkt = Market()

df = mkt.equity("FPT").ohlcv(start="2024-01-01", end="2024-01-31")  # resolution='1D' default
quote_vcb = mkt.equity("VCB").quote()      # current quote/price board
mkt.equity("VCB").trades()                  # tick-by-tick intraday trades

vnindex = mkt.index("VNINDEX").ohlcv(start="2024-01-01", end="2024-01-31")

mkt.forex.ohlcv()      # exchange rates, e.g. "USDVND"
mkt.crypto.ohlcv()     # crypto price, e.g. "BTC" (MSN source on free tier, not Binance API)
mkt.commodity.ohlcv()  # commodity price, e.g. "Gold" (MSN source)
mkt.fund.history() / mkt.fund.nav()
mkt.etf.ohlcv() / .quote() / .trades()
mkt.futures.ohlcv() / .quote() / .trades()
mkt.warrant.ohlcv() / .quote() / .trades()

# Fetch a quick quote for one or many symbols at once
mkt.quote("VCB")
mkt.quote(["VCB", "HPG", "FPT"])
```

The free tier is only guaranteed stable at `resolution='1D'`. Intraday minute-level data (1m/5m/15m)
and fine-grained tick data are sponsor features — don't promise that level of detail on free tier.

**`count` and the community-tier 8-year OHLCV limit** (confirmed by hands-on testing, 2026-07):

- `ohlcv()` takes an optional `count` parameter (not in the official docs, discovered via testing).
  It caps rows returned **counted backward from `end`, not forward from `start`**. If `[start, end]`
  spans more sessions than `count`, the *oldest* rows are silently dropped — you get exactly `count`
  rows ending at `end`. No error, no warning for this specific case.
- **Never omit `count` for a wide date range.** With `count` omitted entirely, `ohlcv()` was
  observed returning only ~100 rows for an 8+ year `start`/`end` range — a small, silent, wrong
  slice, with no warning at all. Always pass an explicit, generously large `count` (e.g. `5000`).
- **Community (free) tier hard-caps daily OHLCV at 8 years, measured back from the query's `end`
  parameter — not from today's date.** Confirmed identical on both `source='kbs'` and
  `source='vci'`. When the requested range exceeds 8 years back from `end`, the library logs this
  warning and truncates instead of raising an exception:
```
  ⚠️ Phiên bản cộng đồng: Dữ liệu OHLCV (1D) giới hạn tối đa 8 năm.
  ⚠️ Community edition: OHLCV data (1D) limited to 8 years.
```
  A single call cannot return more than 8 years of history relative to whatever `end` you pass.
  Sliding `end` earlier doesn't help reach older data within one call; to walk further back,
  repeat the query with progressively earlier `end` values and stop once the returned earliest
  date stops moving.
- **`df['time'].min()` from one bounded call is ambiguous** — it may be the ticker's true listing
  date (if listed less than 8 years before `end`), or just the 8-year tier boundary (if the ticker
  is actually older). One call can't distinguish the two; don't treat it as a confirmed listing
  date without a follow-up query using an earlier `end`.
- **Illustrative sanity-check range, not a constant** (observed 2026-07, `end≈2026-07-25`,
  `count=8000`, across multiple VN30 constituents): full 8-year windows returned between
  **1990 and 1997** sessions depending on the ticker. The spread exists even though `end` was
  effectively the same day for all of them — [likely explanation, unconfirmed] individual
  trading halts/suspension days differ per ticker. Treat ~1990–2000 as a rough ballpark for
  "did this look like a full 8-year pull," not an exact number — it will also drift across
  different `end` dates as holiday-calendar composition changes year to year. If a backfill
  for a ticker with known long trading history returns something far below this ballpark
  (with no tier-limit warning logged), that's a signal to check the ticker's listing date or
  data availability, not assume the request itself failed.

### Fundamental — financial statements

```python
from vnstock.ui import Fundamental
fun = Fundamental()

fun.equity("VCB").income_statement(period="year")   # period: 'year' | 'quarter'
fun.equity("VCB").balance_sheet(period="year")
fun.equity("VCB").cash_flow(period="year")
fun.equity("VCB").ratio()                            # P/E, P/B, ROE, ROA...

# orient='report' (default): rows=line items, columns=reporting periods — good for reading
# orient='time_series': rows=periods, columns=line items — good for charting / ML
df = fun.equity("VCB").income_statement(period="quarter", orient="time_series", limit=8)
```

`financial_health()` (scorecard) and `note()` (financial statement notes) are sponsor-only — free
tier only has the 4 methods above.

### Retail — gold & exchange rate

```python
from vnstock.ui import Retail
ret = Retail()

ret.gold(source="sjc")           # or source="btmc"
ret.exchange_rate()              # current Vietcombank rate, date="YYYY-MM-DD" for a past date
```

## Legacy API (use only when necessary)

Before v3.5.1, vnstock used low-level classes `Quote`, `Listing`, `Company`, `Finance`, `Trading`.
They still work and **require an explicit `source`** (no auto-fallback like the Unified UI). Only
use them when:
- You need a specific method not yet wrapped by the Unified UI, e.g. `capital_history()`
  (KBS-only), `ratio_summary()` (VCI-only), `price_depth()` (order book), `trading_stats()` /
  `side_stats()` (VCI-only).
- You need to pin a single data source and disable Unified UI's auto-selection/fallback.

```python
from vnstock import Quote, Listing, Company, Finance, Trading

quote = Quote(source="vci", symbol="VCB")     # or source="kbs"
df = quote.history(start="2024-01-01", end="2024-12-31", interval="1D")

listing = Listing(source="vci")
company = Company(source="vci", symbol="VCB")
finance = Finance(source="vci", symbol="VCB")
trading = Trading(source="vci")
```

For new code, prefer the Unified UI. Only fall back to the Legacy API when the Unified UI is
genuinely missing the method you need.

## Data sources

- **VCI, KBS**: the most stable sources for listings, prices, company info, and financial
  statements — prefer these.
- **MSN**: used for forex/crypto/commodity — only basic coverage, less stable than VCI/KBS.
- **FMP**: external API, needs its own `FMP_API_KEY` if used directly through the Legacy API.
- **TCBS has been fully removed** — never use `source="tcbs"`; always use `"vci"` or `"kbs"`.
- VCI can be blocked on Google Colab (anti-bot measures) — if the code runs on Colab, be ready to
  fall back to KBS, or let the Unified UI handle it automatically.

## Rate limits (free/community tier)

| Tier | Requests/min | Requests/hour | Requests/day | Requests/month |
|---|---|---|---|---|
| Guest (unregistered) | 20 | — | — | — |
| Community (free registration) | 60 | 3,600 | 10,000 | 100,000 |

Register a free API key to go from 20 to 60 req/min:

```python
from vnstock.core.utils.auth import register_user, check_status

register_user()   # logs in via https://vnstocks.com/login, saves the API key locally
check_status()    # checks current tier & limits
```

Exceeding the limit raises `RateLimitExceeded` (`from vnstock.core.quota import
RateLimitExceeded`) — always catch this when writing code that calls the API repeatedly, and
recommend local caching or reduced call frequency instead of a sponsor upgrade (since this project
is free-tier only).

```python
from vnstock.core.quota import RateLimitExceeded

try:
    df = mkt.equity("VCB").ohlcv(start="2024-01-01", end="2024-12-31")
except RateLimitExceeded as e:
    print(f"API rate limit reached: {e}")
    # suggestion: cache results locally, reduce call frequency, or batch multiple symbols per call
```

## Configuration & environment

```python
from vnstock.config import Config

Config.TIMEOUT = 30
Config.RETRIES = 3
Config.BACKOFF_MULTIPLIER = 2
Config.BACKOFF_MIN = 1
Config.BACKOFF_MAX = 30
```

`.env` for timeout/retry settings or external API keys (FMP/DNSE) if using the Legacy API directly
against those sources — not needed for the usual VCI/KBS flow:

```bash
VNSTOCK_TIMEOUT=30
VNSTOCK_RETRIES=5
FMP_API_KEY=your_fmp_api_key_here
```

The free library can be installed globally or in a virtualenv — no dedicated venv is required the
way sponsor tiers recommend.

## Rules for writing code for the user

1. **Always use the Unified UI (`vnstock.ui`)** unless a method only exists in the Legacy API.
2. **Never suggest `vnstock_data` / `vnstock_ta` / `vnstock_news` / `vnstock_pipeline`** — these
   require a sponsor account the user doesn't have.
3. **Never use `source="tcbs"`** — always `"vci"` or `"kbs"`.
4. **Always catch `RateLimitExceeded`** in code that calls the API in a loop or on a schedule.
5. **Real-time data is only accurate during trading hours** (9:00–15:00 Vietnam time); outside
   those hours, `quote()`/`trades()` return the most recent session's data.
6. **Batch multiple symbols per call** when the API supports it (e.g.
   `mkt.quote(["VCB","HPG","FPT"])`) to save on rate limit, instead of looping over single-symbol
   calls.
7. **Cache results locally** (CSV/parquet/SQLite) for low-frequency data (quarterly/yearly
   financial statements, stock lists) — don't re-fetch on every script run.
8. **Always pass an explicit, large `count` when calling `ohlcv()` for a wide date range**
   (e.g. `count=5000`) — never omit it. Omitting `count` was observed returning a small,
   silent default slice (~100 rows) with no warning, even for an 8+ year `start`/`end` range.
   Also expect a logged (not raised) warning when the community-tier 8-year limit binds —
   see "Market — price & trades" above.
9. When unsure whether a method exists on the free tier, suggest the user run `show_api()` /
   `show_doc("<Domain>.<method>")` themselves to confirm before writing code that assumes it.

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'vnstock'` | Not installed | `pip install -U vnstock` |
| `ImportError: cannot import name 'Quote'` | Wrong import style | Use `from vnstock import Quote`, not `from vnstock.Quote import Quote` |
| `HTTPError: 429 Too Many Requests` / `RateLimitExceeded` | Rate limit exceeded | `register_user()` to raise the limit, or cache/reduce call frequency |
| `NotImplementedError` when using the Legacy API | The source doesn't support that method (e.g. `source="msn"` for `Finance`) | Switch to `source="vci"` or `"kbs"` |
| `ConnectionError` | Slow network/timeout | Raise `Config.TIMEOUT`, check proxy settings if needed |

## Deeper reference (if needed)

This skill deliberately trims the source guide down to the free tier. For more depth on:
- Individual Legacy API methods: `docs/vnstock/advanced-usage/`
- Upgrading to the sponsor tier: `docs/vnstock/08-migration-guide.md`
- Setup/debug/vibe-coding workflow: `docs/setup-and-debug/`

clone `https://github.com/vnstock-hq/vnstock-agent-guide.git` into a temp directory and read those
files directly — they aren't kept in this repo since most of the source guide targets the sponsor
tier.
