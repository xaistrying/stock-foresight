"""Frame builders for the company feed tests: the VCI column names measured on 2026-10-09
(SAB, `Reference().company(symbol).news(source="vci")` and `.events(source="vci")`), with
synthetic values. Nothing here calls the vendor."""

from __future__ import annotations

from datetime import timedelta
from email.utils import format_datetime

import httpx
import numpy as np
import pandas as pd

NEWS_COLUMNS = (
    "id", "news_id", "language", "news_category_code", "icb_code", "com_group_code", "ticker",
    "news_title", "friendly_title", "news_sub_title", "friendly_sub_title", "news_short_content",
    "news_full_content", "news_image_url", "news_small_image_url", "news_source",
    "news_source_link", "news_author", "news_keyword", "friendly_keyword", "public_date",
)
EVENTS_COLUMNS = (
    "id", "event_name_vi", "event_name_en", "ticker", "event_code", "event_title_vi",
    "event_title_en", "display_date1", "display_date2", "public_date", "record_date",
    "exright_date", "payout_date", "value_per_share", "exercise_ratio", "category",
    "issue_date", "listing_date", "start_date", "end_date", "action_type_vi", "action_type_en",
)

_NEWS_DEFAULTS = {
    "id": "6a98be861578f9da77c4aba8", "news_id": 12137682, "language": 0,
    "news_category_code": None, "icb_code": None, "com_group_code": None, "ticker": None,
    "news_title": "SAB: Giải trình BCTC bán niên soát xét năm 2026", "friendly_title": None,
    "news_sub_title": None, "friendly_sub_title": None, "news_short_content": None,
    "news_full_content": None, "news_image_url": "https://cdn.example.invalid/logo.png",
    "news_small_image_url": "", "news_source": None, "news_source_link": None,
    "news_author": None, "news_keyword": None, "friendly_keyword": None,
    "public_date": "2026-08-28T17:39:58",
}
_EVENTS_DEFAULTS = {
    "id": "69effda3db487120c6897f20", "event_name_vi": "Trả cổ tức bằng tiền mặt",
    "event_name_en": "Cash Dividend", "ticker": "SAB", "event_code": "DIV",
    "event_title_vi": "Trả cổ tức bằng tiền mặt - Đợt 2 2025 - 3,000 VND",
    "event_title_en": "Cash Dividend - Interim 2 2025 - 3,000 VND",
    "display_date1": "2026-07-28T00:00:00", "display_date2": "2026-05-08T00:00:00",
    "public_date": "2026-05-08T00:00:00", "record_date": "2026-07-29",
    "exright_date": "2026-07-28", "payout_date": "2026-08-28T00:00:00",
    "value_per_share": 3000.0, "exercise_ratio": 0.3, "category": "DIVIDEND",
    "issue_date": np.nan, "listing_date": np.nan, "start_date": np.nan, "end_date": np.nan,
    "action_type_vi": np.nan, "action_type_en": np.nan,
}


def news_row(**overrides) -> dict:
    return {**_NEWS_DEFAULTS, **overrides}


def events_row(**overrides) -> dict:
    return {**_EVENTS_DEFAULTS, **overrides}


def news_frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows) or [news_row()], columns=list(NEWS_COLUMNS))


def events_frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows) or [events_row()], columns=list(EVENTS_COLUMNS))


def many_news(count: int, *, prefix: str = "Tin") -> pd.DataFrame:
    """`count` distinct news rows, newest first, one day apart."""
    return news_frame(*(
        news_row(news_id=1000 + i, news_title=f"{prefix} số {i}", public_date=f"2026-08-{28 - i % 28:02d}T09:{i % 60:02d}:00")
        for i in range(count)
    ))


def many_events(count: int, *, prefix: str = "Sự kiện") -> pd.DataFrame:
    return events_frame(*(
        events_row(event_title_vi=f"{prefix} số {i}", public_date=f"2026-05-{1 + i % 28:02d}T00:00:00")
        for i in range(count)
    ))


# --- RSS ---------------------------------------------------------------------------------------

FEED_A, FEED_B, FEED_C = (
    "https://vnexpress.net/rss/kinh-doanh.rss",
    "https://cafef.vn/thi-truong-chung-khoan.rss",
    "https://vietstock.vn/830/chung-khoan/co-phieu.rss",
)


def rss_body(*items) -> str:
    """items: (title, published datetime, description)"""
    body = "".join(
        f"<item><title>{title}</title><pubDate>{format_datetime(published)}</pubDate>"
        f"<description><![CDATA[{description}]]></description></item>"
        for title, published, description in items
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>{body}</channel></rss>'


def rss_items(count: int, *, prefix: str, start):
    return [(f"{prefix} {i}", start - timedelta(minutes=10 * i), f"Mô tả {prefix} {i}") for i in range(count)]


def feed_client(feeds: dict):
    """An httpx client serving `feeds`: url -> RSS body, an int HTTP status, or an exception to raise."""
    def handler(request: httpx.Request) -> httpx.Response:
        result = feeds.get(str(request.url), 404)
        if isinstance(result, BaseException):
            raise result
        if isinstance(result, int):
            return httpx.Response(result)
        return httpx.Response(200, content=result.encode())

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
