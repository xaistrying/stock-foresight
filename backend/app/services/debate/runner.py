"""Run control for the debate (`harden-debate-runtime`).

A debate run lives in a task owned by this module, not by the HTTP request:

- requests for a ticker that is already running JOIN that run instead of starting
  another, and get its result or its error;
- at most DEBATE_MAX_CONCURRENT_RUNS (default 2) runs are in flight; a request that
  would start another is rejected at once (`DebateBusy`), never queued;
- a run is bounded by DEBATE_RUN_TIMEOUT_SECONDS (default 180): expiry cancels it,
  which kills any `claude` subprocess, and raises `DebateTimeout` (no partial verdict);
- an abandoned caller (the client disconnected) does not cancel the run: it finishes,
  exports its report and frees its slot;
- the report is exported inside the run, so every joined request sees the same
  `report_file`;
- registered post-run hooks run once per run, after the export and before the result
  is released (design Decision 14);
- one INFO line per run records the stage durations (design Decision 7).

`progress(ticker)` reports the stage a run is in for the panel.

ponytail: the registry is per process. Under `uvicorn --workers N` every worker would
allow its own runs and a ticker could run once per worker; the Makefile starts one
worker. Share the state (a lock file, SQLite) if that ever changes.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial

from app.services.debate.engine import DebateEngine, DebateResult
from app.services.debate.llm_client import (
    LLMClient,
    hook_timeout_seconds,
    max_concurrent_runs,
    run_timeout_seconds,
)

logger = logging.getLogger(__name__)

RETRY_AFTER_SECONDS = 30
# The report export is a local file write; this only stops a stalled mount from holding a slot for ever.
EXPORT_TIMEOUT_SECONDS = 10
STAGES = ("round1", "round2", "synthesis")


class DebateBusy(RuntimeError):
    """The cap on concurrent runs is reached; try again after `retry_after` seconds."""

    retry_after = RETRY_AFTER_SECONDS


class DebateTimeout(RuntimeError):
    """The run did not finish within DEBATE_RUN_TIMEOUT_SECONDS."""


@dataclass(frozen=True)
class RunContext:
    """What a post-run hook is told about the run that just ended."""

    ticker: str
    result: DebateResult
    report_file: str | None  # basename written by the export, or None
    started_at: datetime  # timezone-aware UTC
    finished_at: datetime  # timezone-aware UTC
    stage_ms: dict[str, int]  # round1, round2, synthesis, total
    provider: str
    model: str
    joined: int  # requests that waited on this run, the first included


PostRunHook = Callable[[RunContext], "dict | None | Awaitable[dict | None]"]
Serialiser = Callable[[DebateResult, "str | None"], dict]

_hooks: list[PostRunHook] = []


def register_post_run_hook(hook: PostRunHook) -> None:
    """Call `hook(RunContext)` once per run, in registration order (design Decision 14).

    A hook may return a dict of extra JSON-safe response fields; it can not replace a
    field the response already has. A sync hook runs in a worker thread, an async one
    is awaited. A hook that raises or times out is logged and never fails the response.
    """
    _hooks.append(hook)


@dataclass
class _Run:
    started: float  # monotonic
    stage: str = "round1"
    joined: int = 1
    task: asyncio.Task | None = None


_runs: dict[str, _Run] = {}


def progress(ticker: str) -> dict:
    """`{ticker, running, stage, elapsed_ms}`; never starts a run, never an error."""
    run = _runs.get(ticker)
    if run is None:
        return {"ticker": ticker, "running": False, "stage": None, "elapsed_ms": None}
    return {
        "ticker": ticker,
        "running": True,
        "stage": run.stage,
        "elapsed_ms": int((time.monotonic() - run.started) * 1000),
    }


async def run_debate(ticker: str, eligibility: dict, serialise: Serialiser) -> dict:
    """Join the run in flight for `ticker` or start one; return its serialised response.

    `serialise(result, report_file)` builds the response dict. The same dict object goes
    to every joined request: treat it as read-only.
    Raises `DebateBusy` over the cap, `DebateTimeout` past the budget, or whatever the
    run raised.
    """
    run = _runs.get(ticker)
    if run is None:
        # No await between the cap check and the insert: one event loop needs no lock.
        if len(_runs) >= max_concurrent_runs():
            raise DebateBusy("Another analysis is already running; try again shortly.")
        run = _Run(started=time.monotonic())
        run.task = asyncio.create_task(_execute(ticker, eligibility, serialise, run))
        run.task.add_done_callback(partial(_finished, ticker, run))
        _runs[ticker] = run
    else:
        run.joined += 1
    # shield: a caller that is cancelled stops waiting, the run goes on.
    return await asyncio.shield(run.task)


async def shutdown() -> None:
    """Cancel the runs in flight and wait for them (application shutdown, before the LLM clients close)."""
    tasks = [run.task for run in _runs.values() if run.task is not None]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def _finished(ticker: str, run: _Run, task: asyncio.Task) -> None:
    if _runs.get(ticker) is run:
        del _runs[ticker]
    if not task.cancelled():
        # Retrieved here too, so no "never retrieved" warning whatever happens to the callers
        # (asyncio.shield already does it when its caller left; this does not depend on that).
        task.exception()


def _export(result: DebateResult) -> str | None:
    """The report's file name, or None when nothing was written. Never raises."""
    if result.verdict == "INSUFFICIENT_DATA":  # a refusal is not a report
        return None
    try:
        from app.services.debate.export import export_debate_report

        path = export_debate_report(result)
        return path.name if path else None
    except Exception as exc:
        logger.warning("Debate report export failed for %s: %s", result.ticker, exc)
        return None


async def _bounded_export(result: DebateResult) -> str | None:
    """`_export` in a worker thread, abandoned (not killed) after EXPORT_TIMEOUT_SECONDS."""
    try:
        async with asyncio.timeout(EXPORT_TIMEOUT_SECONDS):
            return await asyncio.to_thread(_export, result)
    except TimeoutError:
        logger.warning("Debate report export for %s timed out after %ss; abandoned", result.ticker, EXPORT_TIMEOUT_SECONDS)
        return None


def _stage_ms(started: float, marks: dict[str, float], now: float, finished: bool) -> dict[str, int]:
    """Durations of the stages that FINISHED; `total` always. A stage still running when a
    run is cut off is left out. A finished run that skipped a stage reports 0 for it."""
    begun = [name for name in STAGES if name in marks]
    out: dict[str, int] = {}
    for index, name in enumerate(begun):
        end = marks[begun[index + 1]] if index + 1 < len(begun) else (now if finished else None)
        if end is not None:
            out[name] = round((end - marks[name]) * 1000)
    if finished:
        for name in STAGES:
            out.setdefault(name, 0)
    out["total"] = round((now - started) * 1000)
    return out


async def _execute(ticker: str, eligibility: dict, serialise: Serialiser, run: _Run) -> dict:
    started_at = datetime.now(timezone.utc)
    marks: dict[str, float] = {}

    def on_stage(name: str) -> None:
        run.stage = name
        marks[name] = time.monotonic()

    status, hook_failures = "error", 0
    provider = model = "unknown"
    stage_ms: dict[str, int] | None = None
    try:
        llm = LLMClient()
        provider, model = llm.provider, llm.model
        budget = run_timeout_seconds()
        ceiling = asyncio.timeout(budget)
        try:
            async with ceiling:
                result = await DebateEngine().run(ticker, eligibility, on_stage=on_stage)
        except TimeoutError:
            if not ceiling.expired():
                raise
            status = "timeout"
            raise DebateTimeout(f"The analysis did not finish within {budget:g} s.") from None

        report_file = await _bounded_export(result)
        # `total` stops here: the hooks are outside the run budget and the stage times.
        stage_ms = _stage_ms(run.started, marks, time.monotonic(), finished=True)
        context = RunContext(
            ticker=ticker, result=result, report_file=report_file, started_at=started_at,
            finished_at=datetime.now(timezone.utc), stage_ms=stage_ms, provider=provider,
            model=model, joined=run.joined,
        )
        payload = serialise(result, report_file)
        hook_failures = await _run_hooks(context, payload)
        status = "ok"
        return payload
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    finally:
        stage_ms = stage_ms or _stage_ms(run.started, marks, time.monotonic(), finished=False)
        logger.info(
            "Debate run ticker=%s provider=%s model=%s status=%s round1_ms=%s round2_ms=%s "
            "synthesis_ms=%s total_ms=%s joined=%d hook_failures=%d",
            ticker, provider, model, status,
            stage_ms.get("round1", "n/a"), stage_ms.get("round2", "n/a"),
            stage_ms.get("synthesis", "n/a"), stage_ms["total"], run.joined, hook_failures,
        )


async def _run_hooks(context: RunContext, payload: dict) -> int:
    """Call every hook once, merge what they return into `payload`; returns the failures
    (raised or timed out). A failure is logged at ERROR with the traceback, never with
    the result text, and never stops the next hook."""
    failures = 0
    for hook in tuple(_hooks):
        name = getattr(hook, "__name__", repr(hook))
        ceiling = asyncio.timeout(hook_timeout_seconds())
        try:
            async with ceiling:
                if inspect.iscoroutinefunction(hook):
                    extra = await hook(context)
                else:
                    extra = await asyncio.to_thread(hook, context)
                if inspect.isawaitable(extra):  # a callable object whose __call__ is async
                    extra = await extra
        except Exception as exc:
            failures += 1
            if isinstance(exc, TimeoutError) and ceiling.expired():
                logger.error("Post-run hook %s for %s timed out and was abandoned", name, context.ticker)
            else:
                logger.error("Post-run hook %s for %s failed", name, context.ticker, exc_info=True)
            continue
        _merge(payload, extra, name)
    return failures


def _merge(payload: dict, extra: object, hook_name: str) -> None:
    """Add a hook's fields to `payload`; a key the response already has is refused."""
    if extra is None:
        return
    try:
        if not isinstance(extra, dict) or not all(isinstance(key, str) for key in extra):
            raise TypeError("not a dict with string keys")
        json.dumps(extra, allow_nan=False)  # what the response will be rendered with
    except (TypeError, ValueError):
        logger.error("Post-run hook %s returned something that is not a JSON-safe dict; ignored", hook_name)
        return
    for key, value in extra.items():
        if key in payload:
            logger.error("Post-run hook %s returned key '%s', which the response already has; refused", hook_name, key)
        else:
            payload[key] = value
