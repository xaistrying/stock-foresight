"""Orchestrate one run of the weekly brief.

Order (design D3): holdings, issued log, model and disclaimer check, refresh, facts, render, output,
log append. Every refusal comes before a vendor call, and the log line is appended only after the
brief has actually been written to stdout (through `emit`) or to `--out`. The function returns a
`RunResult`; the script prints the messages and exits with the code, so nothing here prints.
"""

from __future__ import annotations

import contextlib
import logging
import os
import stat
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from app.ml.volatility import HarModel, load_model
from app.services.brief.compose import BriefTextGuardError, TickerReport, build_brief
from app.services.brief.company_facts import CompanyFacts, ShareCountFn, gather_company_facts, stop_after_failure
from app.services.brief.facts import MarketFacts, gather_market_facts
from app.services.brief.holdings import (
    Holding, HoldingsError, default_holdings_path, directory_warnings, load_holdings,
)
from app.services.brief.issued_log import (
    IssuedEntry, IssuedLogError, LogRead, append_entries, issued_log_path, read_log,
)
from app.services.brief.refresh import RefreshOutcome, refresh_tickers
from app.services.brief.share_cache import ShareCache, share_cache_path
from app.services.brief.timing import ict_now
from app.services.brief.wording import DisclaimerCoverageMismatch, disclaimer_for

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
OUTPUT_MODE = 0o600
EXIT_OK, EXIT_REFUSED = 0, 1
Lines = tuple[str, ...]


@dataclass(frozen=True)
class RunOptions:
    holdings_path: Path | None  # None: the default path
    redact: bool = False
    out: Path | None = None  # None: the brief goes to stdout (through `emit`)
    refresh: bool = True
    sizing: bool = True  # False (--no-sizing): no share-count vendor call, and trade lines show the no-size wording


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    brief: Lines  # empty when the run was refused
    messages: tuple[str, ...]  # for stderr
    written_to: Path | None = None


def write_output(path: Path, lines: Lines) -> None:
    """Write the brief to `path` (never through a symlink), mode 600 even if the file already existed."""
    data = memoryview(("\n".join(lines) + "\n").encode("utf-8"))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC, OUTPUT_MODE)
    try:
        os.fchmod(descriptor, OUTPUT_MODE)
        while data:
            data = data[os.write(descriptor, data):]
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class Steps:
    """The calls a run makes, replaceable one by one so tests can record order and inject failures."""

    load_holdings: Callable[..., tuple[Holding, ...]] = load_holdings
    read_log: Callable[[Path], LogRead] = read_log
    load_model: Callable[[], HarModel | None] = load_model
    disclaimer_for: Callable[[float], str] = disclaimer_for
    refresh_tickers: Callable[..., tuple[RefreshOutcome, ...]] = refresh_tickers
    gather: Callable[..., MarketFacts] = gather_market_facts
    gather_company: Callable[..., CompanyFacts] = gather_company_facts
    build_brief: Callable[..., Lines] = build_brief
    write_output: Callable[[Path, Lines], None] = write_output
    append_entries: Callable[[Path, tuple[IssuedEntry, ...]], None] = append_entries


@dataclass(frozen=True)
class _Preflight:
    holdings: tuple[Holding, ...]
    log: LogRead
    log_path: Path
    messages: tuple[str, ...]


def run_weekly_brief(
    options: RunOptions,
    *,
    repo_root: Path = REPO_ROOT,
    now: datetime | None = None,
    loader: Callable[..., dict] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    steps: Steps = Steps(),
    emit: Callable[[Lines], None] | None = None,
    share_count_fn: ShareCountFn | None = None,
) -> RunResult:
    """`share_count_fn` is the one vendor call for a share count (the script passes it); the brief package never imports it."""
    now = now or datetime.now(timezone.utc)
    prepared = _preflight(options, repo_root, now, steps)
    if isinstance(prepared, RunResult):
        return prepared
    return _render_and_log(prepared, options, now, loader, sleep, steps, emit, share_count_fn)


def _preflight(options: RunOptions, repo_root: Path, now: datetime, steps: Steps) -> _Preflight | RunResult:
    """Everything that can refuse the run, before any vendor call."""
    path = options.holdings_path or default_holdings_path()
    try:
        holdings = steps.load_holdings(path, repo_root=repo_root, today=ict_now(now).date())
    except HoldingsError as error:
        return _refused(str(error))
    messages = [f"warning: {w}" for w in directory_warnings(path)]
    log_path = issued_log_path(path.resolve())
    if (refusal := _location_refusal(options, repo_root, path, log_path)) is not None:
        return _refused(refusal, *messages)

    log = steps.read_log(log_path)
    if log.skipped:
        messages.append(f"warning: {log.skipped} line{'s' if log.skipped != 1 else ''} of {log_path} could not be read and were skipped")
    model = steps.load_model()
    if model is not None:
        try:
            steps.disclaimer_for(model.range_coverage)
        except DisclaimerCoverageMismatch as error:
            return _refused(str(error), *messages)
    return _Preflight(holdings, log, log_path, tuple(messages))


def _render_and_log(
    prepared: _Preflight, options: RunOptions, now: datetime, loader, sleep, steps: Steps, emit, share_count_fn,
) -> RunResult:
    messages = list(prepared.messages)
    tickers = tuple(h.ticker for h in prepared.holdings)
    cache = _open_cache(prepared.log_path, messages) if options.sizing else None  # beside the holdings file
    share_count_fn = stop_after_failure(share_count_fn) if share_count_fn is not None else None  # no further vendor call after a failure
    # vnai prints promotional and rate-limit text to stdout; the brief owns stdout, so it goes to stderr
    with contextlib.redirect_stdout(sys.stderr):
        outcomes = (
            {o.ticker: o for o in steps.refresh_tickers(tickers, loader=loader, sleep=sleep)} if options.refresh else {}
        )
        reports = tuple(
            TickerReport(h, _with_company(
                steps.gather(h.ticker, refresh=outcomes.get(h.ticker), log=prepared.log, now=now),
                prepared, options, now, steps, cache, share_count_fn,
            ))
            for h in prepared.holdings
        )
    messages += cache.notes if cache is not None else []
    try:
        brief = steps.build_brief(reports, redact=options.redact, now=now)
    except (BriefTextGuardError, DisclaimerCoverageMismatch) as error:
        return _refused(str(error), *messages)

    try:
        written_to = _output(brief, options, steps, emit)
    except OSError as error:
        return _refused(f"the brief could not be written ({type(error).__name__}); no log line was added", *messages)
    try:
        steps.append_entries(prepared.log_path, tuple(_entry(r, now) for r in reports))
    except IssuedLogError as error:
        messages.append(f"error: {error}; next week's comparison will not find this run")
        return RunResult(EXIT_REFUSED, brief, tuple(messages), written_to)
    return RunResult(EXIT_OK, brief, tuple(messages), written_to)


def _open_cache(log_path: Path, messages: list[str]) -> ShareCache | None:
    """The share-count cache, or None with a message when it cannot even be opened: sizing then needs a fetch, and the
    brief is still written."""
    try:
        return ShareCache(share_cache_path(log_path))
    except OSError as error:
        messages.append(f"warning: the share-count cache could not be opened ({type(error).__name__}); it was not used")
        return None


def _with_company(
    facts: MarketFacts, prepared: _Preflight, options: RunOptions, now: datetime, steps: Steps, cache: ShareCache | None,
    share_count_fn: ShareCountFn | None,
) -> MarketFacts:
    """The announcements for a holding that has a last bar; without one there is nothing to date them against."""
    if facts.last_bar is None:
        return facts
    company = steps.gather_company(
        facts.ticker, facts, prepared.log, now, sizing=options.sizing, cache=cache, fetch_fn=share_count_fn,
    )
    return replace(facts, company=company)


def _output(brief: Lines, options: RunOptions, steps: Steps, emit: Callable[[Lines], None] | None) -> Path | None:
    if options.out is not None:
        steps.write_output(options.out, brief)
        return options.out
    if emit is not None:
        emit(brief)
    return None


def _refused(*messages: str) -> RunResult:
    return RunResult(EXIT_REFUSED, (), tuple(m if m.startswith(("error", "warning")) else f"error: {m}" for m in messages))


def _location_refusal(options: RunOptions, repo_root: Path, holdings_path: Path, log_path: Path) -> str | None:
    root = repo_root.resolve()
    if log_path.resolve().is_relative_to(root):
        return f"the issued-brief log would be inside the repository ({log_path}); keep the holdings file outside it"
    if options.out is None:
        return None
    target = options.out.resolve()
    if target.is_relative_to(root / "reports"):
        return f"--out {options.out} is inside the repository's reports/ folder, which is for uploads; choose another place"
    if target.is_relative_to(root):
        return f"--out {options.out} is inside the repository; write the brief outside it"
    for protected in (holdings_path, log_path):
        if _same_file(target, protected):
            return f"--out {options.out} is the holdings file or the issued-brief log; choose another place"
    return None


def _same_file(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return first.resolve() == second.resolve()


def stdout_warnings(descriptor: int, repo_root: Path, *, redact: bool) -> tuple[str, ...]:
    """Warn when stdout is a file the brief should not land in: inside the repository, or readable by others."""
    if redact:
        return ()
    try:
        info = os.fstat(descriptor)
    except OSError:
        return ()
    if not stat.S_ISREG(info.st_mode):
        return ()
    warnings = []
    if info.st_mode & 0o077:
        warnings.append("warning: stdout is a file readable by other users; the full brief holds your positions")
    try:
        target = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
    except OSError:
        target = None
    if target is not None and target.resolve().is_relative_to(repo_root.resolve()):
        warnings.append(f"warning: stdout is a file inside the repository ({target}); do not commit the full brief")
    return tuple(warnings)


def _entry(report: TickerReport, now: datetime) -> IssuedEntry:
    facts = report.facts
    return IssuedEntry(
        issued_at=now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        ticker=facts.ticker, as_of=facts.last_bar,
        close=None if facts.close is None else round(facts.close, 2),
        provisional=facts.provisional, status=facts.status, band_pct=facts.band_pct,
        band_lo=_round(facts.band_lo), band_hi=_round(facts.band_hi), calibrated=facts.calibrated,
        model_version=facts.model_version, refreshed=facts.refresh == "ok",
    )


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)
