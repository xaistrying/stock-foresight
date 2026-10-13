"""Fixtures for the dividend and ex-date lines (`add-dividend-and-ex-date-lines`).

Event rows carry dates, amounts, ratios and event codes in the shape the company feed stored on
2026-10-12. The log is vendor data under a personal-use licence and is not to be shared, so no real
title is here: every title is a placeholder, except the title of an `ISS` row, which is only the
keyword phrase that defines its class. SAB's older dividends are synthetic dates in the stored shape;
the rows the scenarios depend on (ex-dates, amounts, ratios, the oldest published date) are the
measured ones. No real holding appears anywhere. Nothing here calls the vendor or the real log.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.ml.volatility import HarModel, parse_artifact
from app.services.company_feed import store
from app.services.company_feed.normalise import frame_to_records
from app.services.company_feed.store import FetchRow

from .company_feed_helpers import events_frame, events_row
from .test_brief_support import ARTIFACT

BONUS, STOCK_DIV, RIGHTS, PLACEMENT, EMPLOYEE = "Cổ phiếu thưởng", "Trả Cổ tức bằng Cổ phiếu", "Quyền mua", "riêng lẻ", "CBCNV"
FETCHED_AT = datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc)


def div_row(ticker: str, n: int, *, published: str, ex: str | None, vnd: float, record: str | None = None, payout: str | None = None) -> dict:
    """A cash dividend; the title is a placeholder that differs per row so the log keeps each row as its own item."""
    return events_row(
        ticker=ticker, event_code="DIV", event_title_vi=f"placeholder {ticker} div {n}", public_date=published,
        exright_date=ex if ex is not None else np.nan, record_date=record or np.nan, payout_date=payout or np.nan,
        value_per_share=vnd, exercise_ratio=np.nan,
    )


def iss_row(ticker: str, keyword: str, n: int, *, published: str, ex: str | None, ratio: float) -> dict:
    """A share issue; its title is only the keyword phrase that defines the class (plus a counter so rows stay distinct)."""
    return events_row(
        ticker=ticker, event_code="ISS", event_title_vi=f"{keyword} {n}", public_date=published,
        exright_date=ex if ex is not None else np.nan, record_date=np.nan, payout_date=np.nan,
        value_per_share=np.nan, exercise_ratio=ratio, category="ISSUE",
    )


def other_row(ticker: str, code: str, *, published: str) -> dict:
    return events_row(
        ticker=ticker, event_code=code, event_title_vi=f"placeholder {ticker} {code}", public_date=published,
        exright_date=np.nan, record_date=np.nan, payout_date=np.nan, value_per_share=np.nan, exercise_ratio=np.nan,
    )


def _sab_older_dividends() -> list[dict]:
    """15 synthetic dividends before the measured ones, so SAB has 18 DIV rows in all."""
    rows = []
    for n in range(15):
        year, half = 2017 + n // 2, n % 2
        ex = f"{year}-{'06' if half == 0 else '12'}-{14 + n:02d}"
        published = f"{year}-{'05' if half == 0 else '11'}-{20 + n % 5:02d}"
        rows.append(div_row("SAB", n, published=published, ex=ex, vnd=1500.0 + 100 * n, record=ex))
    return rows


def sab_rows() -> list[dict]:
    """SAB: 18 DIV rows (ex 2025-06-30, 2026-01-12 and 2026-07-28 measured), a 100% bonus ex 2023-09-14, and one row
    per other code, the oldest published 2017-05-15."""
    return [
        *_sab_older_dividends(),
        div_row("SAB", 15, published="2025-05-20", ex="2025-06-30", vnd=3000.0, record="2025-07-01", payout="2025-07-31T00:00:00"),
        div_row("SAB", 16, published="2025-12-20", ex="2026-01-12", vnd=2000.0, record="2026-01-13", payout="2026-02-12T00:00:00"),
        div_row("SAB", 17, published="2026-05-08T00:00:00", ex="2026-07-28", vnd=3000.0, record="2026-07-29", payout="2026-08-28T00:00:00"),
        iss_row("SAB", BONUS, 1, published="2023-08-01", ex="2023-09-14", ratio=1.0),
        other_row("SAB", "AGME", published="2017-05-15"),
        other_row("SAB", "AIS", published="2018-03-01"),
        other_row("SAB", "EGME", published="2019-04-02"),
    ]


def vpb_rows() -> list[dict]:
    """VPB: 4 DIV rows (oldest 2023-10-20), 50% bonus, 26.04% stock dividend, placement with no ex-date, a private
    placement with ex-date and ratio 0.0, an employee issue with no ex-date; the oldest event is 2022-07-19."""
    return [
        div_row("VPB", 0, published="2023-10-20", ex="2023-11-10", vnd=500.0, record="2023-11-13"),
        div_row("VPB", 1, published="2024-04-15", ex="2024-05-06", vnd=600.0, record="2024-05-07"),
        div_row("VPB", 2, published="2025-05-02", ex="2025-05-22", vnd=700.0, record="2025-05-23"),
        div_row("VPB", 3, published="2026-03-05", ex="2026-03-25", vnd=800.0, record="2026-03-26"),
        iss_row("VPB", BONUS, 1, published="2022-07-19", ex="2022-09-28", ratio=0.5),
        iss_row("VPB", STOCK_DIV, 2, published="2026-08-20", ex="2026-09-24", ratio=0.2604104),
        iss_row("VPB", PLACEMENT, 3, published="2026-04-24", ex=None, ratio=0.0624),
        iss_row("VPB", PLACEMENT, 4, published="2023-10-20", ex="2023-10-20", ratio=0.0),
        iss_row("VPB", EMPLOYEE, 5, published="2025-02-10", ex=None, ratio=0.002),
    ]


def other_ticker_rows() -> dict[str, list[dict]]:
    return {
        "FPT": [
            iss_row("FPT", BONUS, 1, published="2025-06-10", ex="2025-07-21", ratio=0.15),
            iss_row("FPT", BONUS, 2, published="2026-08-12", ex="2026-09-21", ratio=0.10),
            iss_row("FPT", EMPLOYEE, 3, published="2025-04-01", ex="2025-05-07", ratio=0.00472),
        ],
        "KBC": [iss_row("KBC", PLACEMENT, 1, published="2025-05-20", ex="2025-06-24", ratio=0.3257)],
        "SSI": [iss_row("SSI", RIGHTS, 1, published="2025-11-01", ex="2025-12-08", ratio=0.2)],
        "VCB": [
            iss_row("VCB", BONUS, 1, published="2026-04-28", ex=None, ratio=0.1279),
            iss_row("VCB", BONUS, 2, published="2019-04-26", ex=None, ratio=0.5),
            iss_row("VCB", STOCK_DIV, 3, published="2020-06-26", ex=None, ratio=0.2),
        ],
        "MWG": [div_row("MWG", 0, published="2026-09-20", ex="2026-10-07", vnd=1000.0, record="2026-10-08")],
    }


def all_rows() -> dict[str, list[dict]]:
    return {"SAB": sab_rows(), "VPB": vpb_rows(), **other_ticker_rows()}


def load_feed(rows_by_ticker: dict[str, list[dict]] | None = None, *, fetched_at: datetime = FETCHED_AT) -> None:
    """Store `rows_by_ticker` as one successful `events` fetch each, into the (temporary) company feed log."""
    for ticker, rows in (all_rows() if rows_by_ticker is None else rows_by_ticker).items():
        records = frame_to_records(events_frame(*rows), kind="events", ticker=ticker, source="vci").records
        store.record_fetch(
            FetchRow(ticker=ticker, source="vci", kind="events", status="ok", items_returned=len(rows)),
            records, fetched_at=fetched_at,
        )


def record_status(ticker: str, status: str, *, fetched_at: datetime = FETCHED_AT, error: BaseException | None = None) -> None:
    """A fetch row with no items: `empty`, `error` or `rate_limited`."""
    store.record_fetch(
        FetchRow(ticker=ticker, source="vci", kind="events", status=status, items_returned=0, error=error), (),
        fetched_at=fetched_at,
    )


# --- stored bars -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Bars:
    dates: tuple[str, ...]
    opens: tuple[float, ...]
    closes: tuple[float, ...]


def _weekdays_before(day: str, count: int) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(end=pd.Timestamp(day) - pd.tseries.offsets.BDay(1), periods=count)]


def bars_from(window: list[tuple[str, float, float]], *, history: int = 70, level: float | None = None) -> Bars:
    """`window` is (date, open, close) for the last bars; `history` earlier weekday bars hover around `level`."""
    level = window[0][2] if level is None else level
    earlier = [level * (1 + 0.004 * ((i % 4) - 1.5)) for i in range(history)]
    dates = [*_weekdays_before(window[0][0], history), *(d for d, _, _ in window)]
    opens = [*earlier, *(o for _, o, _ in window)]
    closes = [*earlier, *(c for _, _, c in window)]
    return Bars(tuple(dates), tuple(opens), tuple(closes))


def sab_week_bars(history: int = 70) -> Bars:
    """SAB 2026-07-23 to 2026-07-30; a 3,000 VND dividend went ex on 2026-07-28 and the history is adjusted for it."""
    closes = [("2026-07-23", 43.97), ("2026-07-24", 43.51), ("2026-07-27", 43.60), ("2026-07-28", 43.15),
              ("2026-07-29", 43.00), ("2026-07-30", 43.40)]
    return bars_from([(d, 43.00 if d == "2026-07-28" else c, c) for d, c in closes], history=history, level=44.0)


def raw_history_bars(history: int = 70) -> Bars:
    """Not yet adjusted: previous close 46.60, the ex-day open 43.60 (a 3,000 VND dividend ex 2026-07-28)."""
    return bars_from([("2026-07-24", 46.55, 46.55), ("2026-07-27", 46.60, 46.60), ("2026-07-28", 43.60, 43.40),
                      ("2026-07-29", 43.30, 43.35), ("2026-07-30", 43.40, 43.45), ("2026-07-31", 43.40, 43.40)], history=history, level=46.6)


def stock_bars(open_price: float) -> Bars:
    """A 10% bonus ex 2026-09-21: previous close 30.00, ex-day open 27.30 (not adjusted) or 29.80 (adjusted)."""
    return bars_from([("2026-09-18", 30.00, 30.00), ("2026-09-21", open_price, open_price)], level=30.0)


def small_dividend_bars() -> Bars:
    """A 500 VND dividend on a 22.90 price, ex 2026-07-28."""
    return bars_from([("2026-07-27", 22.90, 22.90), ("2026-07-28", 22.80, 22.85)], level=22.9)


def model_with_sigma(sigma_daily_pct: float) -> HarModel:
    """A model whose daily sigma is the given percent whatever the prices (zero coefficients)."""
    raw = {**ARTIFACT, "intercept": math.log(sigma_daily_pct / 100), "coef": {"rv5": 0.0, "rv20": 0.0, "rv60": 0.0}}
    return parse_artifact(raw)


def d(text: str) -> date:
    return date.fromisoformat(text)


def days_after(text: str, days: int) -> date:
    return d(text) + timedelta(days=days)
