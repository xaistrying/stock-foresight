"""One snapshot run: RSS first, then each ticker's VCI news and events, paced under vnai's limit.

Started only by `backend/scripts/snapshot_company_feed.py`, by hand (design Decision 1): nothing else
imports this module. The fetchers, the store functions, the clock and `sleep` are parameters (`Tools`),
so tests inject stubs the way `bulk_ingestion` does.

Failures are per fetch and never silent (the `debate-outcome-log` pattern, design Decision 8): a fetch
that raises is logged at ERROR with its traceback naming ticker and kind, recorded as an `error` fetch
row, and the run continues. A write that fails is logged, counted and does not stop the run. vnai's rate
limit is paced under and, when hit, waited out and retried; only a persistent limit stops the run.
Anything that is not vnai's limiter and exits the process (`SystemExit`) is honoured.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable

import pandas as pd

from app.services.bulk_ingestion import (
    DEFAULT_SYMBOLS_PER_MINUTE,
    MAX_RATE_LIMIT_WAITS,
    RATE_LIMIT_WAIT_SECONDS,
)
from app.services.company_feed import fetch, rss, store
from app.services.company_feed.normalise import VENDOR_KINDS, NormalisedFrame, frame_to_records
from app.services.company_feed.store import FetchRow, PlannedFetch
from app.services.company_feed.summary import FetchReport, RunSummary

logger = logging.getLogger(__name__)

SECONDS_PER_MINUTE = 60.0


@dataclass(frozen=True)
class Options:
    """Operational knobs, all with the defaults design Decision 7 gives (none is a threshold on a price move)."""

    tickers_per_minute: float = DEFAULT_SYMBOLS_PER_MINUTE  # two vendor requests a ticker: 16 a minute against vnai's 20
    include_rss: bool = True
    dry_run: bool = False
    rate_limit_wait: float = RATE_LIMIT_WAIT_SECONDS
    max_rate_limit_waits: int = MAX_RATE_LIMIT_WAITS

    def __post_init__(self) -> None:
        if not self.tickers_per_minute > 0:
            raise ValueError("tickers_per_minute must be positive")


@dataclass(frozen=True)
class Tools:
    """Everything a run touches outside itself: the real ones by default, stubs in tests."""

    fetch_frame: Callable[[str, str], pd.DataFrame] = fetch.fetch_company_frame
    fetch_feeds: Callable[[], Awaitable[list[rss.FeedResult]]] = rss.fetch_feeds
    vnstock_version: Callable[[], str | None] = fetch.installed_vnstock_version
    record: Callable[..., store.StoredFetch] = store.record_fetch
    new_records: Callable[..., list] = store.new_records
    last_fetch: Callable[..., store.LastFetch | None] = store.last_fetch
    now: Callable[[], datetime] = store.utc_now
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep


class _Run:
    """The accumulators of one run (local to it; the result is the frozen `RunSummary`)."""

    def __init__(self, options: Options, tools: Tools) -> None:
        self.options, self.tools = options, tools
        self.reports: list[FetchReport] = []
        self.warnings: list[str] = []
        self.write_failures = 0
        self._warned_body_columns: set[str] = set()

    # --- one fetch ---------------------------------------------------------------------------

    def _previous_success(self, ticker: str, kind: str, source: str) -> str | None:
        try:
            previous = self.tools.last_fetch(ticker, kind, source)
        except Exception:  # noqa: BLE001 — the age is a report line, not a reason to stop
            logger.exception("Could not read the previous fetch of %s %s from the company feed log", ticker or source, kind)
            self.warnings.append(f"could not read the previous fetch of {ticker or source} {kind}")
            return None
        return previous.last_success_at if previous else None

    def _attempt(self, ticker: str, kind: str) -> tuple[pd.DataFrame | None, Exception | None, int]:
        """`(frame, error, rate-limit waits)`. `error` is a `RateLimited` once the allowed waits are used up."""
        waits = 0
        while True:
            try:
                return self.tools.fetch_frame(ticker, kind), None, waits
            except fetch.RateLimited as error:
                if waits >= self.options.max_rate_limit_waits:
                    logger.error("Giving up on %s %s after %d rate-limit waits", ticker, kind, waits, exc_info=True)
                    return None, error, waits
                waits += 1
                logger.warning(
                    "Rate limit on %s %s; waiting %.0fs (wait %d of %d)",
                    ticker, kind, self.options.rate_limit_wait, waits, self.options.max_rate_limit_waits,
                )
                self.tools.sleep(self.options.rate_limit_wait)
            except Exception as error:  # noqa: BLE001 — one ticker's failure must not end the run
                logger.exception("Company feed fetch failed for %s %s", ticker, kind)
                return None, error, waits

    def _normalise(self, frame: pd.DataFrame, ticker: str, kind: str) -> tuple[NormalisedFrame | None, Exception | None]:
        try:
            normalised = frame_to_records(frame, kind=kind, ticker=ticker, source=fetch.VENDOR_SOURCE)
        except Exception as error:  # noqa: BLE001
            logger.exception("Company feed fetch failed for %s %s", ticker, kind)
            return None, error
        for column in normalised.body_columns_filled:
            if column not in self._warned_body_columns:
                self._warned_body_columns.add(column)
                message = f"the vendor's {kind} frame has a non-empty body column {column!r}; it is not stored"
                logger.warning("%s", message)
                self.warnings.append(message)
        return normalised, None

    def fetch_vendor(self, ticker: str, kind: str, version: str | None) -> FetchReport:
        previous_at = self._previous_success(ticker, kind, fetch.VENDOR_SOURCE)
        frame, error, waits = self._attempt(ticker, kind)
        normalised = None
        if error is None:
            normalised, error = self._normalise(frame, ticker, kind)
        if error is not None:
            status = store.STATUS_RATE_LIMITED if isinstance(error, fetch.RateLimited) else store.STATUS_ERROR
            row = FetchRow(ticker, fetch.VENDOR_SOURCE, kind, status, error=error, vnstock_version=version)
            return self._store(PlannedFetch(row), previous_at, waits=waits)
        status = store.STATUS_EMPTY if frame.empty else store.STATUS_OK
        row = FetchRow(ticker, fetch.VENDOR_SOURCE, kind, status, items_returned=len(frame), vnstock_version=version)
        return self._store(PlannedFetch(row, normalised.records), previous_at, waits=waits, skipped=normalised.skipped_cells)

    def _store(self, plan: PlannedFetch, previous_at: str | None, *, waits: int = 0, skipped: int = 0) -> FetchReport:
        row = plan.row
        items_new: int | None = None
        write_failed = False
        would_store: tuple = ()
        try:
            if self.options.dry_run:
                would_store = tuple(self.tools.new_records(plan.records))
                items_new = len(would_store)
            else:
                items_new = self.tools.record(row, plan.records, fetched_at=self.tools.now()).items_new
        except Exception:  # noqa: BLE001 — the items return in the next frame, so the run goes on
            logger.exception("Could not %s the %s %s fetch", "check" if self.options.dry_run else "write", row.ticker or row.source, row.kind)
            self.write_failures += 1
            write_failed = True
        possible_gap = (
            row.kind in VENDOR_KINDS and row.status == store.STATUS_OK and previous_at is not None
            and row.items_returned == fetch.VENDOR_ITEM_CAP and items_new == len(plan.records)  # a repeated row is one record
        )
        if possible_gap:
            logger.warning(
                "possible gap: %s %s returned %d items, all new, after an earlier successful fetch (%s): "
                "items were probably missed between runs",
                row.ticker, row.kind, row.items_returned, previous_at,
            )
        report = FetchReport(
            ticker=row.ticker, source=row.source, kind=row.kind, status=row.status, items_returned=row.items_returned,
            items_new=items_new, error_class=type(row.error).__name__ if row.error is not None else None,
            previous_success_at=previous_at, possible_gap=possible_gap, write_failed=write_failed,
            skipped_cells=skipped, rate_limit_waits=waits, would_store=would_store,
        )
        self.reports.append(report)
        return report

    # --- the run -----------------------------------------------------------------------------

    def fetch_rss(self) -> None:
        try:
            results = asyncio.run(self.tools.fetch_feeds())
        except Exception as error:  # noqa: BLE001
            logger.exception("Could not fetch the RSS feeds")
            results = [rss.FeedResult(url=url, error=error) for url in rss.FEEDS]
        for result, plan in zip(results, rss.plan_fetches(results)):
            if result.error is not None:
                logger.error("Company feed fetch failed for rss %s", result.url, exc_info=result.error)
            self._store(plan, self._previous_success("", "rss", result.url))

    def fetch_ticker(self, ticker: str) -> tuple[str, ...] | None:
        """Both kinds for one ticker. None to carry on; the kinds still unattempted if the rate limit stopped the run."""
        version = self.tools.vnstock_version()
        for position, kind in enumerate(VENDOR_KINDS):
            if self.fetch_vendor(ticker, kind, version).status == store.STATUS_RATE_LIMITED:
                return VENDOR_KINDS[position + 1:]
        return None

    def run(self, tickers: tuple[str, ...]) -> RunSummary:
        if self.options.include_rss:
            self.fetch_rss()  # unmetered by vnai, so it is done before anything a rate limit could stop
        interval = SECONDS_PER_MINUTE / self.options.tickers_per_minute
        last_start: float | None = None
        not_attempted: tuple[str, ...] = ()
        for index, ticker in enumerate(tickers):
            if last_start is not None:
                wait = last_start + interval - self.tools.clock()
                if wait > 0:
                    self.tools.sleep(wait)
            last_start = self.tools.clock()
            unattempted_kinds = self.fetch_ticker(ticker)
            if unattempted_kinds is not None:
                not_attempted = tuple(f"{ticker}:{kind}" for kind in unattempted_kinds) + tickers[index + 1:]
                break
        return RunSummary(
            reports=tuple(self.reports), not_attempted=not_attempted, write_failures=self.write_failures,
            warnings=tuple(self.warnings), dry_run=self.options.dry_run,
        )


def run_snapshot(tickers: tuple[str, ...], options: Options | None = None, tools: Tools | None = None) -> RunSummary:
    """Fetch and store RSS items (unless `options.include_rss` is off) and each ticker's VCI news and events.

    Tickers are started at most `options.tickers_per_minute` a minute, each at least one interval after the
    previous one started. In a dry run everything is fetched and reported and nothing is written."""
    return _Run(options or Options(), tools or Tools()).run(tickers)
