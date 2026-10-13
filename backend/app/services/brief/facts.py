"""Everything the brief says about one ticker that comes from prices, the model and the issued log.

`MarketFacts` holds no holdings data: the market sections render it and nothing else. Gathering is
fenced per holding, so a failure degrades one holding to a plain status and never removes it. The
price history and the model travel with the facts (as defaulted fields) so later sections can use
them without reading the database again.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import TYPE_CHECKING

import numpy as np

from app.ml.volatility import HarModel, load_model, read_recent_closes
from app.services.brief import corporate_actions
from app.services.brief.adjustment_status import AdjustmentStatus, adjustment_status
from app.services.brief.feed_source import Event, FeedSnapshot, read_events
from app.services.brief.issued_log import LogRead
from app.services.brief.levels import Readjusted, detect_readjusted
from app.services.brief.prices import read_opens
from app.services.brief.refresh import RefreshOutcome
from app.services.brief.timing import provisional_bar, stale_reasons
from app.services.brief.week import WeekFacts, week_facts
from app.services.range import RangeResult, TickerNotLoaded, compute_range

if TYPE_CHECKING:
    from app.services.brief.company_facts import CompanyFacts

logger = logging.getLogger(__name__)

NO_PRICES = "no_prices"
ERROR = "error"
MODEL_UNAVAILABLE = "model_unavailable"
SKIPPED = "skipped"  # the refresh state when --no-refresh is given


@dataclass(frozen=True)
class MarketFacts:
    ticker: str
    refresh: str  # ok | failed | not_attempted | skipped
    refresh_detail: str
    last_bar: str | None
    close: float | None  # thousand VND, as stored
    provisional: bool
    status: str  # a range status, or no_prices | error
    reasons: tuple[str, ...]
    band_pct: float | None  # half-width of the typical 5-session move, percent
    band_lo: float | None  # close x exp(-band/100)
    band_hi: float | None
    range_coverage: float | None  # None when not measured for this ticker
    calibrated: bool | None
    model_version: str | None
    week: WeekFacts | None
    readjusted: Readjusted | None
    error_class: str | None
    stale_reasons: tuple[str, ...] = ()  # set across the holdings by `with_staleness`
    dates: tuple[str, ...] = ()  # stored bars, ascending (at most the model's history window)
    opens: tuple[float, ...] = ()  # aligned with `dates`; nan where a bar has no stored open
    closes: tuple[float, ...] = ()  # aligned with `dates`
    model: HarModel | None = None
    feed: FeedSnapshot | None = None  # None: the feed was not read, and no feed line is printed
    ex_status: tuple[tuple[Event, AdjustmentStatus], ...] = ()  # each past ex-date's adjustment status
    company: CompanyFacts | None = None  # the announcements the COMPANY block needs; None: not read, and no block is printed


def gather_market_facts(
    ticker: str,
    *,
    refresh: RefreshOutcome | None,
    log: LogRead,
    now: datetime,
    range_fn: Callable[[str], RangeResult] = compute_range,
    closes_fn: Callable[[str], tuple[list[str], np.ndarray]] = read_recent_closes,
    model_fn: Callable[[], HarModel | None] = load_model,
    opens_fn: Callable[[str, Sequence[str]], tuple[float, ...]] = read_opens,
    feed_fn: Callable[[str], FeedSnapshot] = read_events,
) -> MarketFacts:
    """Facts for one ticker; any failure becomes a degraded `MarketFacts`, never an exception."""
    facts = _prices_and_range(
        ticker, refresh=refresh, log=log, now=now, range_fn=range_fn, closes_fn=closes_fn, model_fn=model_fn, opens_fn=opens_fn,
    )
    if not facts.dates:
        return facts  # no stored prices: there is no last bar to date the feed lines against
    feed = feed_fn(ticker)
    try:
        statuses = _ex_statuses(feed, facts, facts.model or _model(model_fn))
    except Exception:  # noqa: BLE001 - the statuses are context: without them each ex-date reads "could not be told"
        logger.exception("computing the adjustment statuses for %s failed", ticker)
        statuses = ()
    return replace(facts, feed=feed, ex_status=statuses)


def _ex_statuses(
    feed: FeedSnapshot, facts: MarketFacts, model: HarModel | None,
) -> tuple[tuple[Event, AdjustmentStatus], ...]:
    """The stored-bars status of each cash dividend and count-changing issue that has gone ex (none without a model or opens)."""
    if feed.status != "fetched" or model is None or len(facts.opens) != len(facts.dates):
        return ()
    last = date.fromisoformat(facts.dates[-1])
    candidates = (*corporate_actions.cash_dividends(feed.events), *corporate_actions.count_changing_issues(feed.events))
    return tuple(
        (event, adjustment_status(event, facts.dates, facts.opens, facts.closes, model))
        for event in candidates if event.exright_date <= last
    )


def _prices_and_range(
    ticker: str,
    *,
    refresh: RefreshOutcome | None,
    log: LogRead,
    now: datetime,
    range_fn: Callable[[str], RangeResult],
    closes_fn: Callable[[str], tuple[list[str], np.ndarray]],
    model_fn: Callable[[], HarModel | None],
    opens_fn: Callable[[str, Sequence[str]], tuple[float, ...]],
) -> MarketFacts:
    fields: dict = dict(
        ticker=ticker, refresh=refresh.state if refresh else SKIPPED, refresh_detail=refresh.detail if refresh else "",
        last_bar=None, close=None, provisional=False, status=NO_PRICES, reasons=(), band_pct=None, band_lo=None,
        band_hi=None, range_coverage=None, calibrated=None, model_version=None, week=None, readjusted=None,
        error_class=None,
    )
    try:
        dates, closes = closes_fn(ticker)
    except Exception as error:  # noqa: BLE001 - fenced per holding by design
        logger.exception("reading stored closes for %s failed", ticker)
        return MarketFacts(**{**fields, "status": ERROR, "error_class": type(error).__name__})
    if len(closes) == 0:
        return MarketFacts(**fields)

    entries = log.for_ticker(ticker)
    fields |= dict(
        last_bar=dates[-1], close=float(closes[-1]), provisional=provisional_bar(dates[-1], now),
        week=week_facts(dates, closes, entries), readjusted=detect_readjusted(entries, dates, closes),
        dates=tuple(dates), closes=tuple(float(c) for c in closes), opens=_opens(opens_fn, ticker, dates),
    )
    try:
        result = range_fn(ticker)
    except TickerNotLoaded:  # the two reads disagree: say nothing about prices rather than something inconsistent
        return MarketFacts(**fields | _no_prices_fields())
    except Exception as error:  # noqa: BLE001 - fenced per holding by design
        logger.exception("gathering the range for %s failed", ticker)
        return MarketFacts(**{**fields, "status": ERROR, "error_class": type(error).__name__})

    model = _model(model_fn)
    if model is None and result.status in ("ok", "uncalibrated"):  # the range loaded a model the second read cannot: withhold it
        return MarketFacts(**{**fields, "status": MODEL_UNAVAILABLE})
    fields |= dict(
        status=result.status, reasons=tuple(result.reasons), model=model,
        model_version=model.model_version if model else None,
    )
    if result.range_5s_pct is not None:
        band, close = result.range_5s_pct, fields["close"]
        fields |= dict(
            band_pct=band, band_lo=close * math.exp(-band / 100), band_hi=close * math.exp(band / 100),
            range_coverage=result.range_coverage, calibrated=result.status == "ok",
        )
    return MarketFacts(**fields)


def _no_prices_fields() -> dict:
    return dict(
        last_bar=None, close=None, provisional=False, status=NO_PRICES, week=None, readjusted=None,
        dates=(), opens=(), closes=(),
    )


def _model(model_fn: Callable[[], HarModel | None]) -> HarModel | None:
    try:
        return model_fn()
    except Exception:  # noqa: BLE001 - a model that cannot load is "model unavailable", not a crash
        logger.exception("loading the volatility model failed")
        return None


def _opens(opens_fn: Callable[[str, Sequence[str]], tuple[float, ...]], ticker: str, dates: Sequence[str]) -> tuple[float, ...]:
    try:
        return opens_fn(ticker, dates)
    except Exception:  # noqa: BLE001 - opens are optional context; the brief does not depend on them
        logger.warning("reading stored opens for %s failed", ticker, exc_info=True)
        return ()


def with_staleness(facts: tuple[MarketFacts, ...], now: datetime) -> tuple[MarketFacts, ...]:
    """Each holding's staleness against the newest last bar among them and the run date."""
    newest = max((f.last_bar for f in facts if f.last_bar), default=None)
    return tuple(replace(f, stale_reasons=stale_reasons(f.last_bar, newest, now)) for f in facts)
