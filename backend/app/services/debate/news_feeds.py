"""Recent Vietnamese financial headlines from public RSS feeds, for the News agent.

Replaces scraping the sites' search pages: Vietstock's search URL now 404s,
Cafef's returned nothing the ticker filter accepted, and requiring the ticker
symbol in a headline throws away the market-wide news (VN-Index, rates, FX, GDP)
that moves most stocks. Headlines are tagged by how they relate to the ticker so
the agent can weigh company news differently from market backdrop.

Feed content is untrusted: XML goes through defusedxml (no entity expansion),
text is stripped of markup and control characters and length-capped before it
is ever placed in a prompt.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx
from defusedxml import ElementTree as SafeET

logger = logging.getLogger(__name__)

FEEDS = (
    "https://vnexpress.net/rss/kinh-doanh.rss",
    "https://cafef.vn/thi-truong-chung-khoan.rss",
    "https://vietstock.vn/830/chung-khoan/co-phieu.rss",
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = httpx.Timeout(10.0)
# httpx's timeout is per read, so a feed dripping a byte at a time is never cut
# off by it: bound the whole fetch, and the decoded size (a gzip bomb).
FETCH_TIMEOUT_SECONDS = 15
MAX_FEED_BYTES = 2_000_000
MAX_REDIRECTS = 3

# 7 calendar days ≈ 5 trading sessions, matching the prediction horizon
# (design.md Decision 6). The feeds themselves only reach back 1-5 days.
MAX_AGE = timedelta(days=7)
# Dates a feed gets wrong (e.g. local time labelled GMT) land slightly ahead of
# now; anything further is dropped rather than ranked first.
MAX_FUTURE = timedelta(days=1)
# Headlines show Vietnam's calendar date (UTC+7, no DST), not each feed's own offset.
ICT = timezone(timedelta(hours=7))
# Per-tag caps; the News agent's prompt takes MAX_HEADLINES of them.
LIMITS = {"ticker": 5, "sector": 4, "market": 10}
MAX_HEADLINES = sum(LIMITS.values())
TITLE_MAX = 200
SNIPPET_MAX = 160

# Market-wide / macro news. Deliberately narrower than "thị trường" or
# "cổ phiếu", which also match gold/property markets and single-company stories.
MARKET = re.compile(
    r"\b(?:vn-?index|hose|hnx|chứng khoán|khối ngoại|nâng hạng|lãi suất|tỷ giá"
    r"|gdp|lạm phát|vĩ mô|nhnn|ngân hàng nhà nước|fed)\b",
    re.IGNORECASE,
)
# Of the market headlines, the ones about the index itself go first: an index
# move is the most informative backdrop, and newest-first alone fills the slots
# with the last few hours of daily chatter (a monthly recap like "VN-Index giảm
# 64 điểm trong tháng 9" was the 36th of 36 candidates).
INDEX = re.compile(r"\bvn-?index\b", re.IGNORECASE)
# ...but index chatter can run to a dozen items a day, so it may take at most
# this many of the market slots; rates, FX and Fed stories get the rest.
INDEX_SLOTS = 4
# Market-wide foreign net flow ("khối ngoại bán ròng X tỷ trong tuần") is a macro
# signal the free data feeds cannot supply as numbers, so the press is the source:
# these headlines get reserved slots right after the index ones.
FOREIGN = re.compile(r"\b(?:khối ngoại)\b", re.IGNORECASE)
# Within those, a title with a market-wide cue (a week, a session, HOSE) is the
# recap of total flow; others are usually one-stock stories ("Khối ngoại bán ròng
# mạnh VHM") and only fill the reserved slots when no recap exists.
FOREIGN_MARKET_WIDE = re.compile(r"\b(?:tuần|phiên|toàn thị trường|hose|hnx)\b", re.IGNORECASE)
FOREIGN_SLOTS = 2

# Symbols that are also everyday upper-case words (VND the currency, VAT the
# tax). Bare matches would tag "USD/VND" or "thuế VAT" stories as company news,
# so these only match when the text says it is a stock: "cổ phiếu VND", "mã VND".
AMBIGUOUS_SYMBOLS = frozenset({"VND", "VAT"})

# ICB supersector codes as stored in ticker_universe.icb_code2 (checked against
# well-known tickers: SAB/VNM/MSN=3500, HPG/HSG/NKG=1700, ACB/TCB/VCB=8300 ...).
# Labels follow the ICB standard names.
SECTOR_BY_ICB = {
    "0500": "oil and gas",
    "1300": "chemicals",
    "1700": "basic resources",
    "2300": "construction and materials",
    "2700": "industrial goods and services",
    "3300": "automobiles and parts",
    "3500": "food and beverage",
    "3700": "personal and household goods",
    "4500": "health care",
    "5300": "retail",
    "5500": "media",
    "5700": "travel and leisure",
    "7500": "utilities",
    "8300": "banking",
    "8500": "insurance",
    "8600": "real estate",
    "8700": "financial services",
    "9500": "technology",
}
# Vietnamese keywords per sector label, matched against headline titles only.
# Avoid words with other common meanings: "đường" (sugar, but also road/path/
# "Thiên đường"), "tôn" ("tôn vinh"), bare "điện" ("điện thoại") all produced
# false matches on real headlines.
SECTOR_KEYWORDS = {
    "oil and gas": "dầu khí|giá dầu|xăng dầu",
    "chemicals": "hóa chất|phân bón|nhựa",
    "basic resources": "thép|kim loại|khoáng sản|quặng",
    "construction and materials": "xây dựng|vật liệu xây dựng|xi măng|đầu tư công|hạ tầng",
    "industrial goods and services": "công nghiệp|logistics|cảng biển|vận tải",
    "automobiles and parts": "ô tô|xe điện|linh kiện",
    "food and beverage": (
        "thực phẩm|đồ uống|nước giải khát|bia|rượu|sữa|thủy sản|nông sản|gạo"
        "|thuế tiêu thụ đặc biệt"
    ),
    "personal and household goods": "dệt may|may mặc|đồ gỗ|nội thất|trang sức",
    "health care": "dược|y tế|bệnh viện|thuốc",
    "retail": "bán lẻ|siêu thị|thương mại điện tử|tiêu dùng",
    "media": "truyền thông|quảng cáo|báo chí",
    "travel and leisure": "hàng không|du lịch|khách sạn|lưu trú",
    "utilities": "giá điện|điện lực|thủy điện|nhiệt điện|điện gió|điện mặt trời|năng lượng|khí đốt|nước sạch",
    # Not bare "ngân hàng": any story about one bank matched (foreign banks hacked,
    # one lender's asset sale), and "huy động" matched every capital-raising story.
    "banking": (
        "tín dụng|nợ xấu|lãi suất huy động|tiền gửi|ngành ngân hàng|nhóm ngân hàng"
        "|cổ phiếu ngân hàng|các ngân hàng|hệ thống ngân hàng|ngân hàng thương mại"
        "|lợi nhuận ngân hàng|ldr|nim"
        # Peer bank names: [ticker] only matches the symbol ("VPB" never matches
        # "VPBank"), so without these a bank's own results/funding news is untagged.
        # Full names only: bare symbols (ACB, VIB, OCB, SHB, MSB) also turn up in stock lists.
        "|vietcombank|vietinbank|bidv|agribank|techcombank|vpbank|mbbank|mb bank"
        "|sacombank|tpbank|hdbank|lpbank|seabank|eximbank|abbank|nam a bank|bac a bank"
        # A generic bank as the subject of results or capital-raising news.
        r"|ngân hàng\s.{0,40}?(?:báo lãi|lợi nhuận|lãi quý|tăng vốn|chia cổ tức|phát hành trái phiếu)"
    ),
    "insurance": "bảo hiểm",
    "real estate": "bất động sản|địa ốc|nhà ở|căn hộ|đất nền",
    "financial services": "công ty chứng khoán|môi giới|margin|tự doanh",
    "technology": "công nghệ|chuyển đổi số|bán dẫn|phần mềm",
}

# A story whose subject is a bank is not news about a non-financial sector, whatever
# its collateral is ("nhà máy nông sản" in a lender's asset sale matched food &
# beverage). Financial sectors keep them. Bank-wide macro stories ("Ngân hàng Nhà
# nước", rates) are still tagged [market] by MARKET.
FINANCIAL_SECTORS = frozenset({"banking", "insurance", "financial services", "real estate"})
# ...except institutions that are not a lender in the sector's own market: the World
# Bank/ADB (commodity and infrastructure outlooks), the State Bank and central banks
# (policy, tagged [market]).
BANK = re.compile(
    r"\bngân hàng\b(?!\s+(?:thế giới|phát triển châu á|nhà nước|trung ương))", re.IGNORECASE
)
# Foreign banks are not banking-sector news for a Vietnamese bank. Country names are
# case-sensitive on purpose ("Anh" the country vs "anh" the pronoun; Britain is left
# out for that reason).
FOREIGN_BANKS = re.compile(
    r"(?i:\bngân hàng\b|\bnhà băng\b)[^.:;]{0,25}?"
    r"\b(?:Mỹ|Hàn Quốc|Trung Quốc|Nhật Bản|châu Âu|Đức|Thụy Sĩ|Ấn Độ|Thái Lan|Singapore|Indonesia)\b"
)

# (published, title, snippet)
_Item = tuple[datetime, str, str]


def _clean(text: str | None, limit: int) -> str:
    """Plain single-line text for a prompt: entities decoded *then* markup
    stripped (so a double-escaped tag can't come back as markup), whitespace
    collapsed, and every Unicode control/format character dropped — that
    covers zero-width and bidi characters and the invisible "tag" block an LLM
    can read. `<[^<>]*>` is linear; `<[^>]+>` was quadratic on unclosed `<`."""
    text = re.sub(r"<[^<>]*>", " ", html.unescape(text or ""))
    text = unicodedata.normalize("NFC", re.sub(r"\s+", " ", text).strip())
    return "".join(c for c in text if unicodedata.category(c)[0] != "C")[:limit]


def _parse_feed(xml: bytes) -> list[_Item]:
    items: list[_Item] = []
    for item in SafeET.fromstring(xml).iter("item"):
        title = _clean(item.findtext("title"), TITLE_MAX)
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue  # undated: can't tell whether it is recent
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if title:
            items.append((published, title, _clean(item.findtext("description"), SNIPPET_MAX)))
    return items


async def _fetch_feed(client: httpx.AsyncClient, url: str) -> list[_Item]:
    async with asyncio.timeout(FETCH_TIMEOUT_SECONDS):
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():  # decoded, not wire, bytes
                body += chunk
                if len(body) > MAX_FEED_BYTES:
                    raise ValueError(f"feed larger than {MAX_FEED_BYTES} bytes")
    return _parse_feed(bytes(body))


def _ticker_pattern(ticker: str) -> re.Pattern[str]:
    # Case-sensitive whole word: symbols are written upper-case, and this keeps
    # "SAB" from matching "SABRE".
    symbol = re.escape(ticker)
    if ticker in AMBIGUOUS_SYMBOLS:
        return re.compile(rf"\b(?i:cổ phiếu|mã|cp)\s+{symbol}\b")
    return re.compile(rf"\b{symbol}\b")


def _select(items: list[_Item], ticker: str, sector: str | None, now: datetime) -> list[str]:
    ticker_re = _ticker_pattern(ticker)
    keywords = SECTOR_KEYWORDS.get(sector or "")
    sector_re = re.compile(rf"\b(?:{keywords})\b", re.IGNORECASE) if keywords else None
    skip_bank_stories = sector not in FINANCIAL_SECTORS
    skip_foreign_banks = sector == "banking"

    buckets: dict[str, list[str]] = {"ticker": [], "sector": [], "market": []}
    index_lines: list[str] = []  # market headlines about the index, newest first
    foreign_wide: list[str] = []  # ...about market-wide foreign flow (and not the index)
    foreign_other: list[str] = []  # ...about foreign flow, no market-wide cue
    seen: set[str] = set()
    for published, title, snippet in sorted(items, key=lambda i: i[0], reverse=True):
        if not -MAX_FUTURE <= now - published <= MAX_AGE or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        if ticker_re.search(title) or ticker_re.search(snippet):
            tag = "ticker"
        elif (
            sector_re
            and sector_re.search(title)
            and not (skip_bank_stories and BANK.search(title))
            and not (skip_foreign_banks and FOREIGN_BANKS.search(title))
        ):
            tag = "sector"
        elif MARKET.search(title):
            tag = "market"
        else:
            continue
        line = f"[{tag}] {published.astimezone(ICT):%Y-%m-%d} {title}"
        line = f"{line} — {snippet}" if snippet else line
        if tag == "market" and INDEX.search(title):
            index_lines.append(line)
        elif tag == "market" and FOREIGN.search(title):
            (foreign_wide if FOREIGN_MARKET_WIDE.search(title) else foreign_other).append(line)
        else:
            buckets[tag].append(line)

    # Index headlines first, then foreign flow, each capped so the rest (rates, FX,
    # Fed) keep slots; whatever those two had beyond their caps fills any slots left.
    foreign_lines = foreign_wide + foreign_other
    buckets["market"] = (
        index_lines[:INDEX_SLOTS]
        + foreign_lines[:FOREIGN_SLOTS]
        + buckets["market"]
        + index_lines[INDEX_SLOTS:]
        + foreign_lines[FOREIGN_SLOTS:]
    )
    return [line for tag in ("ticker", "sector", "market") for line in buckets[tag][: LIMITS[tag]]]


async def fetch_headlines(
    ticker: str,
    sector: str | None,
    *,
    client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Recent headlines tagged [ticker] / [sector] / [market], newest first
    within each tag, ticker-related first. `client` and `now` are injectable for
    tests.

    One feed failing is logged and skipped; every feed failing raises, so the
    caller can report "unavailable" rather than a misleading "no news".
    """
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            headers=HEADERS, timeout=TIMEOUT, follow_redirects=True, max_redirects=MAX_REDIRECTS
        )
    try:
        results = await asyncio.gather(
            *(_fetch_feed(client, url) for url in FEEDS), return_exceptions=True
        )
    finally:
        if owns_client:
            await client.aclose()

    items: list[_Item] = []
    for url, result in zip(FEEDS, results):
        if isinstance(result, Exception):
            logger.warning("News feed %s failed: %s", url, result)
        else:
            items.extend(result)
    if all(isinstance(result, Exception) for result in results):
        raise RuntimeError("all news feeds failed")

    return _select(items, ticker, sector, now or datetime.now(timezone.utc))
