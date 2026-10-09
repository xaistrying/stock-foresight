"""What a snapshot run reports: per-fetch results, the exit code and the printed summary.

Pure: no vendor library, no database. Because the snapshot clock ticks only when the script runs, the
summary states for every ticker and kind how long ago the previous successful fetch was, so a lapse is
visible; it repeats every `possible gap` and every failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.company_feed.normalise import ItemRecord
from app.services.company_feed.store import SUCCESS_STATUSES

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

_SECONDS_PER_HOUR = 3600
_HOURS_PER_DAY = 24


@dataclass(frozen=True)
class FetchReport:
    ticker: str  # '' for an RSS feed
    source: str
    kind: str
    status: str
    items_returned: int | None = None
    items_new: int | None = None  # new versions stored (in a dry run: that would be stored)
    error_class: str | None = None
    previous_success_at: str | None = None  # the earlier successful fetch of this ticker, kind and source
    possible_gap: bool = False
    write_failed: bool = False
    skipped_cells: int = 0
    rate_limit_waits: int = 0
    would_store: tuple[ItemRecord, ...] = ()  # filled in a dry run only

    @property
    def label(self) -> str:
        return f"{self.ticker} {self.kind}" if self.ticker else f"rss {self.source}"

    @property
    def succeeded(self) -> bool:
        return self.status in SUCCESS_STATUSES and not self.write_failed


@dataclass(frozen=True)
class RunSummary:
    reports: tuple[FetchReport, ...]
    not_attempted: tuple[str, ...] = ()  # tickers (or "TICKER:kind") a rate limit stopped the run before
    write_failures: int = 0
    warnings: tuple[str, ...] = ()
    dry_run: bool = False

    @property
    def exit_code(self) -> int:
        """0 only when every fetch ended `ok` or `empty`, every write succeeded and nothing was left unattempted."""
        clean = all(report.succeeded for report in self.reports) and not self.not_attempted
        return EXIT_OK if clean and self.write_failures == 0 else EXIT_FAILED


def describe_age(previous_success_at: str | None, now: datetime) -> str:
    if previous_success_at is None:
        return "no previous successful fetch"
    age = now - datetime.fromisoformat(previous_success_at)
    hours = age.total_seconds() / _SECONDS_PER_HOUR
    if hours < _HOURS_PER_DAY:
        return f"previous successful fetch {hours:.1f} hours ago"
    return f"previous successful fetch {hours / _HOURS_PER_DAY:.1f} days ago"


def _line(report: FetchReport, now: datetime, dry_run: bool) -> str:
    verb = "would store" if dry_run else "new"
    detail = report.status if report.error_class is None else f"{report.status} ({report.error_class})"
    if report.items_returned is not None:
        new = "?" if report.items_new is None else report.items_new
        detail += f", {report.items_returned} returned, {new} {verb}"
    if report.write_failed:
        detail += ", WRITE FAILED"
    if report.skipped_cells:
        detail += f", {report.skipped_cells} non-scalar cell(s) skipped"
    if report.rate_limit_waits:
        detail += f", {report.rate_limit_waits} rate-limit wait(s)"
    return f"  {report.label}: {detail}; {describe_age(report.previous_success_at, now)}"


def _preview(report: FetchReport) -> list[str]:
    return [f"      {record.published_at or '-'}  {record.title or '-'}" for record in report.would_store]


def format_summary(summary: RunSummary, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    lines = ["Company feed snapshot" + (" (dry run: nothing written)" if summary.dry_run else "")]
    for report in summary.reports:
        lines.append(_line(report, now, summary.dry_run))
        lines.extend(_preview(report))
    if not summary.reports:
        lines.append("  nothing was fetched")

    problems = [f"  {r.label}: {r.status}" + (f" ({r.error_class})" if r.error_class else "") for r in summary.reports if not r.succeeded]
    gaps = [f"  possible gap: {r.label} returned {r.items_returned} items, all new" for r in summary.reports if r.possible_gap]
    for title, entries in (
        ("Failures:", problems),
        ("Possible gaps (items were probably missed between runs):", gaps),
        ("Warnings:", [f"  {warning}" for warning in summary.warnings]),
        ("Not attempted (stopped by the rate limit):", [f"  {entry}" for entry in summary.not_attempted]),
    ):
        if entries:
            lines.extend([title, *entries])
    if summary.write_failures:
        lines.append(f"Write failures: {summary.write_failures}")
    lines.append(f"Exit code {summary.exit_code}")
    return "\n".join(lines)
