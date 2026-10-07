"""The debate runner: in-flight de-duplication, the concurrency cap, the run budget,
progress, the per-run log line and post-run hooks (`harden-debate-runtime`, task group 3).

The engine is a stub; no LLM, network or database is touched.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import re
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.debate import runner
from app.services.debate.engine import AgentPosition, DebateResult, SynthesisResult
from app.services.debate.runner import DebateBusy, DebateTimeout, RunContext

SECRET_TEXT = "THE-MODEL-WROTE-THIS-SENTENCE"


def _result(ticker: str = "VCB") -> DebateResult:
    positions = {a: AgentPosition(a, "bull", ["a bullet"]) for a in ("technical", "news", "macro")}
    return DebateResult(
        ticker=ticker, as_of="2026-10-07", verdict="BUY_SIGNAL", agreement_level="unanimous",
        round1=positions, round2=dict(positions),
        synthesis=SynthesisResult("BUY_SIGNAL", "unanimous", SECRET_TEXT, SECRET_TEXT),
        duration_ms=1, data_as_of="2026-10-07", data_age_sessions=0,
    )


def serialise(result: DebateResult, report_file: str | None) -> dict:
    return {
        "ticker": result.ticker, "verdict": result.verdict,
        "report_saved": report_file is not None, "report_file": report_file,
    }


@pytest.fixture(autouse=True)
def isolated_runner(monkeypatch):
    """A fresh registry and hook list per test, default settings, and a stubbed export."""
    monkeypatch.setattr(runner, "_runs", {})
    monkeypatch.setattr(runner, "_hooks", [])
    for name in ("DEBATE_RUN_TIMEOUT_SECONDS", "DEBATE_MAX_CONCURRENT_RUNS", "DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("DEBATE_LLM_MODEL", "stub-model")
    exports: list[str] = []

    def export(result):
        exports.append(result.ticker)
        return Path(f"/tmp/{result.as_of}_{result.ticker}.md")

    monkeypatch.setattr("app.services.debate.export.export_debate_report", export)
    return SimpleNamespace(exports=exports)


@pytest.fixture
def engine(monkeypatch):
    """A stub engine. `calls` lists the tickers it ran; `finished` those that completed."""
    state = SimpleNamespace(calls=[], finished=[], stage_delay=0.0, fail=None, gate=None)

    class FakeEngine:
        async def run(self, ticker, eligibility=None, on_stage=None):
            state.calls.append(ticker)
            for stage in ("round1", "round2", "synthesis"):
                if on_stage:
                    on_stage(stage)
                await asyncio.sleep(state.stage_delay)
                if state.gate is not None and stage == "round2":
                    await state.gate.wait()
            if state.fail is not None:
                raise state.fail
            state.finished.append(ticker)
            return _result(ticker)

    monkeypatch.setattr(runner, "DebateEngine", FakeEngine)
    return state


async def run(ticker: str = "VCB") -> dict:
    return await runner.run_debate(ticker, {"eligible": True, "as_of": "2026-10-07"}, serialise)


async def drained(ticker: str, seconds: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + seconds
    while runner.progress(ticker)["running"]:
        assert asyncio.get_running_loop().time() < deadline, "the run never ended"
        await asyncio.sleep(0.01)


# ===========================================================================
# De-duplication, cap, budget, abandonment
# ===========================================================================


@pytest.mark.asyncio
async def test_two_requests_for_one_ticker_start_one_run_and_both_get_the_same_result(engine):
    engine.stage_delay = 0.05

    first, second = await asyncio.gather(run("VCB"), run("VCB"))

    assert engine.calls == ["VCB"]
    assert first == second
    assert first["verdict"] == "BUY_SIGNAL"


@pytest.mark.asyncio
async def test_the_same_error_is_shared_by_every_joined_request(engine):
    engine.stage_delay = 0.05
    engine.fail = RuntimeError("boom")

    results = await asyncio.gather(run("VCB"), run("VCB"), return_exceptions=True)

    assert engine.calls == ["VCB"]
    assert all(isinstance(r, RuntimeError) and str(r) == "boom" for r in results)


@pytest.mark.asyncio
async def test_the_third_distinct_ticker_over_the_cap_is_rejected_at_once_without_an_engine_call(engine, monkeypatch):
    monkeypatch.setenv("DEBATE_MAX_CONCURRENT_RUNS", "2")
    engine.stage_delay = 0.2
    running = [asyncio.create_task(run("VCB")), asyncio.create_task(run("FPT"))]
    await asyncio.sleep(0.05)

    with pytest.raises(DebateBusy) as busy:
        await run("ACB")

    assert sorted(engine.calls) == ["FPT", "VCB"]  # nothing started for ACB
    assert busy.value.retry_after == 30
    await asyncio.gather(*running)


@pytest.mark.asyncio
async def test_joiners_do_not_count_against_the_cap(engine, monkeypatch):
    monkeypatch.setenv("DEBATE_MAX_CONCURRENT_RUNS", "1")
    engine.stage_delay = 0.1

    first, second, third = await asyncio.gather(run("VCB"), run("VCB"), run("VCB"))

    assert first == second == third and engine.calls == ["VCB"]


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "failure", "timeout"])
async def test_a_slot_is_freed_after_success_failure_and_timeout(engine, monkeypatch, outcome):
    monkeypatch.setenv("DEBATE_MAX_CONCURRENT_RUNS", "1")
    if outcome == "failure":
        engine.fail = RuntimeError("boom")
    if outcome == "timeout":
        monkeypatch.setenv("DEBATE_RUN_TIMEOUT_SECONDS", "0.1")
        engine.stage_delay = 5
    try:
        await run("VCB")
    except (RuntimeError, DebateTimeout):
        pass
    engine.stage_delay, engine.fail = 0.0, None
    monkeypatch.delenv("DEBATE_RUN_TIMEOUT_SECONDS", raising=False)

    assert (await run("FPT"))["ticker"] == "FPT"


@pytest.mark.asyncio
async def test_an_abandoned_caller_does_not_cancel_the_run_and_its_report_is_still_exported(
    engine, isolated_runner
):
    engine.stage_delay = 0.1
    caller = asyncio.create_task(run("VCB"))
    await asyncio.sleep(0.05)

    caller.cancel()  # the client disconnected
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert runner.progress("VCB")["running"]
    await drained("VCB")

    assert engine.finished == ["VCB"]
    assert isolated_runner.exports == ["VCB"]


@pytest.mark.asyncio
async def test_a_later_request_joins_a_run_whose_first_caller_left(engine):
    engine.stage_delay = 0.1
    first = asyncio.create_task(run("VCB"))
    await asyncio.sleep(0.05)
    first.cancel()

    joined = await run("VCB")

    assert engine.calls == ["VCB"] and joined["verdict"] == "BUY_SIGNAL"


@pytest.mark.asyncio
async def test_a_run_past_its_budget_raises_a_timeout_and_leaves_the_registry(engine, monkeypatch):
    monkeypatch.setenv("DEBATE_RUN_TIMEOUT_SECONDS", "0.2")
    engine.stage_delay = 5

    with pytest.raises(DebateTimeout, match="did not finish"):
        await run("VCB")

    assert runner.progress("VCB")["running"] is False
    assert engine.finished == []


@pytest.mark.asyncio
async def test_a_failed_run_with_no_waiting_caller_logs_no_never_retrieved_warning(engine):
    problems: list[str] = []  # what the event loop's exception handler is told
    asyncio.get_running_loop().set_exception_handler(lambda loop, context: problems.append(context["message"]))
    engine.fail = RuntimeError("boom")
    caller = asyncio.create_task(run("VCB"))
    await asyncio.sleep(0)
    caller.cancel()  # nobody is left to retrieve the run's exception
    await drained("VCB")
    await asyncio.sleep(0)  # the done callbacks
    del caller
    gc.collect()  # a task that still held an unretrieved exception reports it when it is freed

    # (asyncio.shield itself reports "Exception in shielded future" when its caller left: expected.)
    assert [m for m in problems if "never retrieved" in m] == []


# ===========================================================================
# Progress
# ===========================================================================


@pytest.mark.asyncio
async def test_progress_reports_the_stage_and_elapsed_time_then_goes_idle(engine):
    engine.stage_delay = 0.0
    engine.gate = asyncio.Event()
    caller = asyncio.create_task(run("VCB"))
    await asyncio.sleep(0.05)

    state = runner.progress("VCB")
    assert state["running"] is True and state["stage"] == "round2" and state["elapsed_ms"] >= 40
    assert state["ticker"] == "VCB"
    engine.gate.set()
    await caller
    assert runner.progress("VCB") == {"ticker": "VCB", "running": False, "stage": None, "elapsed_ms": None}


def test_progress_for_an_unknown_ticker_is_idle_not_an_error():
    assert runner.progress("ZZZ") == {"ticker": "ZZZ", "running": False, "stage": None, "elapsed_ms": None}


# ===========================================================================
# The per-run log line
# ===========================================================================

LINE = re.compile(
    r"^Debate run ticker=VCB provider=openai model=stub-model status=(?P<status>\w+) "
    r"round1_ms=(?P<r1>\S+) round2_ms=(?P<r2>\S+) synthesis_ms=(?P<syn>\S+) total_ms=(?P<total>\d+) "
    r"joined=(?P<joined>\d+) hook_failures=(?P<failures>\d+)$"
)


def _run_lines(caplog) -> list[re.Match]:
    messages = [r.getMessage() for r in caplog.records if r.name == runner.logger.name and r.levelno == logging.INFO]
    return [LINE.match(m) for m in messages if m.startswith("Debate run")]


@pytest.mark.asyncio
async def test_a_successful_run_logs_one_line_with_the_stage_durations(engine, caplog):
    engine.stage_delay = 0.05
    with caplog.at_level(logging.INFO, logger=runner.logger.name):
        await asyncio.gather(run("VCB"), run("VCB"))

    (line,) = _run_lines(caplog)
    assert line is not None, "the line does not have the documented shape"
    assert line["status"] == "ok" and line["joined"] == "2" and line["failures"] == "0"
    stages = [int(line[k]) for k in ("r1", "r2", "syn")]
    assert all(ms >= 40 for ms in stages)
    assert int(line["total"]) >= sum(stages) - 5


@pytest.mark.asyncio
async def test_a_timed_out_run_logs_status_timeout_and_only_the_stages_that_finished(engine, monkeypatch, caplog):
    monkeypatch.setenv("DEBATE_RUN_TIMEOUT_SECONDS", "0.3")
    engine.stage_delay = 0.2  # round 1 ends at 0.2 s, round 2 is cut off at 0.3 s
    with caplog.at_level(logging.INFO, logger=runner.logger.name):
        with pytest.raises(DebateTimeout):
            await run("VCB")

    (line,) = _run_lines(caplog)
    assert line["status"] == "timeout"
    assert int(line["r1"]) >= 150 and line["r2"] == "n/a" and line["syn"] == "n/a"


@pytest.mark.asyncio
async def test_a_failed_run_logs_status_error(engine, caplog):
    engine.fail = RuntimeError("boom")
    with caplog.at_level(logging.INFO, logger=runner.logger.name):
        with pytest.raises(RuntimeError):
            await run("VCB")

    (line,) = _run_lines(caplog)
    assert line["status"] == "error"


def test_the_application_logs_info_from_its_own_loggers_so_the_run_line_reaches_the_backend_log():
    """uvicorn configures only its own loggers: without this the INFO line below is dropped and
    `.run/backend.log` (make up) would show warnings only."""
    import app.main  # noqa: F401  (importing it configures logging)

    assert logging.getLogger(runner.logger.name).isEnabledFor(logging.INFO)
    handlers = logging.getLogger("app").handlers
    assert any(isinstance(h, logging.StreamHandler) for h in handlers)  # stderr, which make up redirects


def test_the_backend_log_masks_key_shaped_text_even_in_a_traceback():
    """An SDK error body can quote a (masked) key; whatever is logged must not carry one."""
    import app.main  # noqa: F401

    handler = next(h for h in logging.getLogger("app").handlers if isinstance(h, logging.StreamHandler))
    secret = "sk-" + "proj-ABCDEF0123456789"
    try:
        raise RuntimeError(f"Incorrect API key provided: {secret}")
    except RuntimeError:
        record = logging.LogRecord("app.x", logging.WARNING, __file__, 1, "call failed: %s", (secret,), exc_info=__import__("sys").exc_info())
    text = handler.format(record)

    assert secret not in text and "ABCDEF0123456789" not in text
    assert "call failed:" in text and "Incorrect API key provided" in text  # the rest is kept


@pytest.mark.asyncio
async def test_the_run_line_carries_no_result_text(engine, caplog):
    with caplog.at_level(logging.INFO, logger=runner.logger.name):
        await run("VCB")

    assert SECRET_TEXT not in caplog.text


# ===========================================================================
# Post-run hooks
# ===========================================================================


@pytest.mark.asyncio
async def test_a_hook_is_called_once_for_three_joined_requests_with_the_count(engine):
    engine.stage_delay = 0.05
    seen: list[RunContext] = []
    runner.register_post_run_hook(seen.append)

    await asyncio.gather(run("VCB"), run("VCB"), run("VCB"))

    assert len(seen) == 1 and seen[0].joined == 3
    assert (seen[0].ticker, seen[0].provider, seen[0].model) == ("VCB", "openai", "stub-model")


@pytest.mark.asyncio
async def test_the_hook_sees_the_export_outcome_and_the_run_times(engine):
    seen: list[RunContext] = []
    runner.register_post_run_hook(seen.append)

    response = await run("VCB")

    (ctx,) = seen
    assert ctx.report_file == response["report_file"] == "2026-10-07_VCB.md"
    assert ctx.result.verdict == "BUY_SIGNAL"
    assert ctx.started_at.tzinfo is not None and ctx.finished_at >= ctx.started_at
    assert set(ctx.stage_ms) == {"round1", "round2", "synthesis", "total"}


@pytest.mark.asyncio
async def test_a_failed_export_reaches_the_hook_as_no_report_file(engine, monkeypatch):
    def export_fails(result):
        raise OSError("disk full")

    monkeypatch.setattr("app.services.debate.export.export_debate_report", export_fails)
    seen: list[RunContext] = []
    runner.register_post_run_hook(seen.append)

    response = await run("VCB")

    assert seen[0].report_file is None
    assert response["report_saved"] is False and response["report_file"] is None


@pytest.mark.asyncio
async def test_hooks_run_in_registration_order(engine):
    order: list[str] = []
    runner.register_post_run_hook(lambda ctx: order.append("first"))
    runner.register_post_run_hook(lambda ctx: order.append("second"))

    await run("VCB")

    assert order == ["first", "second"]


@pytest.mark.asyncio
async def test_a_hook_that_returns_an_awaitable_is_awaited_too(engine):
    class AsyncCallable:  # not a coroutine function, but calling it gives a coroutine
        async def __call__(self, ctx):
            return {"from_callable": ctx.ticker}

    runner.register_post_run_hook(AsyncCallable())

    assert (await run("VCB"))["from_callable"] == "VCB"


@pytest.mark.asyncio
async def test_a_hung_export_cannot_hold_the_slot_for_ever(engine, monkeypatch):
    import time

    monkeypatch.setattr(runner, "EXPORT_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setenv("DEBATE_MAX_CONCURRENT_RUNS", "1")
    monkeypatch.setattr("app.services.debate.export.export_debate_report", lambda r: time.sleep(1.0))

    response = await run("VCB")

    assert response["report_saved"] is False and response["report_file"] is None
    assert runner.progress("VCB")["running"] is False  # the slot is free again
    assert (await run("FPT"))["ticker"] == "FPT"


@pytest.mark.asyncio
async def test_shutdown_cancels_the_runs_in_flight_and_waits_for_them(engine):
    engine.stage_delay = 5
    caller = asyncio.create_task(run("VCB"))
    await asyncio.sleep(0.05)

    await runner.shutdown()

    assert runner.progress("VCB")["running"] is False
    with pytest.raises(asyncio.CancelledError):
        await caller


@pytest.mark.asyncio
async def test_a_sync_hook_runs_in_a_worker_thread_and_an_async_hook_is_awaited(engine):
    threads: list[int] = []
    awaited: list[str] = []

    def sync_hook(ctx):
        threads.append(threading.get_ident())

    async def async_hook(ctx):
        await asyncio.sleep(0)
        awaited.append(ctx.ticker)

    runner.register_post_run_hook(sync_hook)
    runner.register_post_run_hook(async_hook)

    await run("VCB")

    assert threads and threads[0] != threading.get_ident()
    assert awaited == ["VCB"]


@pytest.mark.asyncio
async def test_a_raising_hook_logs_an_error_later_hooks_run_and_the_response_is_unchanged(engine, caplog):
    later: list[str] = []

    def broken(ctx):
        raise RuntimeError("boom")

    runner.register_post_run_hook(broken)
    runner.register_post_run_hook(lambda ctx: later.append("ran"))

    with caplog.at_level(logging.INFO, logger=runner.logger.name):
        response = await run("VCB")

    assert later == ["ran"]
    assert response == {"ticker": "VCB", "verdict": "BUY_SIGNAL", "report_saved": True, "report_file": "2026-10-07_VCB.md"}
    (error,) = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert "broken" in error.getMessage() and "VCB" in error.getMessage() and error.exc_info is not None
    assert _run_lines(caplog)[0]["failures"] == "1"
    assert SECRET_TEXT not in caplog.text


@pytest.mark.asyncio
async def test_a_hooks_returned_fields_reach_every_joined_request_from_one_call(engine):
    engine.stage_delay = 0.05
    calls: list[str] = []

    def hook(ctx):
        calls.append(ctx.ticker)
        return {"debate_log_id": 42}

    runner.register_post_run_hook(hook)

    responses = await asyncio.gather(run("VCB"), run("VCB"), run("VCB"))

    assert calls == ["VCB"]
    assert all(r["debate_log_id"] == 42 for r in responses)


@pytest.mark.asyncio
async def test_a_colliding_key_is_refused_and_the_existing_value_kept(engine, caplog):
    runner.register_post_run_hook(lambda ctx: {"extra": 1})

    def greedy(ctx):
        return {"verdict": "X", "report_saved": False, "extra": 2, "debate_log_id": 7}

    runner.register_post_run_hook(greedy)

    response = await run("VCB")

    assert response["verdict"] == "BUY_SIGNAL" and response["report_saved"] is True
    assert response["extra"] == 1 and response["debate_log_id"] == 7
    refused = " ".join(r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)
    assert "greedy" in refused
    for key in ("verdict", "report_saved", "extra"):
        assert f"'{key}'" in refused


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [["a", "list"], "text", 7, {"nan": float("nan")}, {"set": {1, 2}}, {1: "int key"}])
async def test_a_non_dict_or_non_json_safe_return_is_ignored_with_an_error(engine, caplog, bad):
    runner.register_post_run_hook(lambda ctx: bad)

    response = await run("VCB")

    assert set(response) == {"ticker", "verdict", "report_saved", "report_file"}
    assert any(r.levelno == logging.ERROR for r in caplog.records)


@pytest.mark.asyncio
async def test_a_failed_or_timed_out_hook_adds_no_fields(engine, monkeypatch):
    monkeypatch.setenv("DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS", "0.1")

    async def slow(ctx):
        await asyncio.sleep(5)
        return {"late": True}

    def broken(ctx):
        raise RuntimeError("boom")

    runner.register_post_run_hook(slow)
    runner.register_post_run_hook(broken)

    response = await run("VCB")

    assert set(response) == {"ticker", "verdict", "report_saved", "report_file"}


@pytest.mark.asyncio
async def test_a_slow_hook_is_abandoned_logged_and_the_response_released(engine, monkeypatch, caplog):
    monkeypatch.setenv("DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS", "0.1")

    async def slow(ctx):
        await asyncio.sleep(5)

    runner.register_post_run_hook(slow)
    started = asyncio.get_running_loop().time()

    with caplog.at_level(logging.INFO, logger=runner.logger.name):
        response = await run("VCB")

    assert asyncio.get_running_loop().time() - started < 2
    assert response["verdict"] == "BUY_SIGNAL"
    assert any(r.levelno == logging.ERROR and "timed out" in r.getMessage() for r in caplog.records)
    assert _run_lines(caplog)[0]["failures"] == "1"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "error"])
async def test_no_hook_is_called_for_a_run_that_timed_out_or_raised(engine, monkeypatch, failure):
    called: list[str] = []
    runner.register_post_run_hook(lambda ctx: called.append(ctx.ticker))
    if failure == "timeout":
        monkeypatch.setenv("DEBATE_RUN_TIMEOUT_SECONDS", "0.1")
        engine.stage_delay = 5
    else:
        engine.fail = RuntimeError("boom")

    with pytest.raises((DebateTimeout, RuntimeError)):
        await run("VCB")

    assert called == []


@pytest.mark.asyncio
async def test_the_slot_is_held_until_the_hooks_finish(engine, monkeypatch):
    monkeypatch.setenv("DEBATE_MAX_CONCURRENT_RUNS", "1")
    release = asyncio.Event()

    async def waits(ctx):
        await release.wait()

    runner.register_post_run_hook(waits)
    first = asyncio.create_task(run("VCB"))
    await asyncio.sleep(0.05)  # the engine is done, the hook is waiting

    with pytest.raises(DebateBusy):
        await run("FPT")

    release.set()
    await first
    assert (await run("FPT"))["ticker"] == "FPT"
