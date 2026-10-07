"""
Measures the runtime behaviour `harden-debate-runtime` changes, with stubs only
(design.md Decision 13): no LLM, no network, no vnstock, no database.

Drives `DebateEngine().run(ticker)` with
- a stubbed `LLMClient.chat` that sleeps `--call-seconds` and records start, end
  and a stage tag per call (tagged by its system prompt);
- stubbed headline and market fetches;
- stubs for the SQLite reads and the volatility call that BLOCK for
  `--block-seconds` (time.sleep), standing in for the real blocking work;
- a background probe that sleeps 10 ms in a loop and keeps the largest gap it
  saw, i.e. how long the event loop was stalled.

Prints one JSON object: LLM call count, per-stage wall time against the sum of
its calls (the synthesis stage is the interesting one: sum of two calls before
the change, about one after), the largest event-loop gap, and the installed
openai / anthropic SDK default timeout and retry count.

The engine part runs on the unchanged tree and after the change: the before / after
comparison in tasks 1.2 and 8.2. When `app.services.debate.runner` exists it also
measures run control: N concurrent requests for one ticker (expect one run's 8 calls
and one shared result) and M distinct tickers over the cap (expect the surplus
rejected with no LLM call); on the unchanged tree that part is `null`. The README's
41 s run and the post-pivot review's 2.8 s cold model load are NOT reproduced by stubs.

Writes nothing (the report export is stubbed). Run from the project root:
    backend/.venv/bin/python backend/scripts/measure_debate_runtime.py
        [--call-seconds 0.3] [--block-seconds 0.5] [--ticker VCB] [--requests 5] [--tickers 4]
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.debate import macro, news, technical  # noqa: E402
from app.services.debate.engine import DebateEngine  # noqa: E402
from app.services.debate.llm_client import LLMClient  # noqa: E402

PROBE_INTERVAL_SECONDS = 0.01
ELIGIBILITY = {"eligible": True, "reasons": [], "as_of": "2026-10-07", "age_sessions": 0}
REPLY = "bull\n- A stubbed reasoning bullet that is long enough to count as usable text."
FEATURE_ROW = {"date": "2026-10-07", "rsi": 60.0, "macd_histogram": 0.05,
               "tenkan_sen": 20.0, "kijun_sen": 18.0, "near_gap": 0}


def stage_of(system_prompt: str) -> str:
    """Round 1 / Round 2 / synthesis, from the agents' own system prompts."""
    if "synthesiser" in system_prompt:
        return "synthesis"
    if "strict technical analyst" in system_prompt or "disciplined" in system_prompt:
        return "round2"
    return "round1"


def install_stubs(call_seconds: float, block_seconds: float, calls: list[dict]) -> None:
    async def chat(self, messages):
        start = time.monotonic()
        await asyncio.sleep(call_seconds)
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        calls.append({"stage": stage_of(system), "start": start, "end": time.monotonic()})
        return REPLY

    def blocking(value):
        def read(*_args, **_kwargs):
            time.sleep(block_seconds)  # a sync SQLite read / model call
            return value
        return read

    async def fetch_headlines(ticker, sector):
        return [f"[ticker] 2026-10-0{n} {ticker} headline {n}" for n in range(1, 4)]

    async def bounded(fetch, *_args):  # macro's market-data fetches, already off the loop
        return {
            "_get_vnindex_closes": pd.Series(
                [100.0 + i for i in range(27)], index=[f"D{i:02d}" for i in range(27)]
            ),
            "_get_usd_vnd_change": 0.1,
            "_get_market_foreign_flow": (1e9, 1e10),
        }[fetch.__name__]

    LLMClient.chat = chat
    news.fetch_headlines = fetch_headlines
    news._get_sector_for_ticker = blocking("Banking")
    technical._get_features_row = blocking(FEATURE_ROW)
    technical.compute_range = blocking(None)  # the volatility call; None = "unavailable"
    macro._bounded = bounded
    macro._load_ohlcv_closes = blocking(
        pd.Series([100.0 + i for i in range(22)], index=[f"D{i:02d}" for i in range(22)])
    )
    import app.services.data_eligibility as eligibility

    eligibility.assess_eligibility = lambda ticker: ELIGIBILITY


def stage_summary(calls: list[dict]) -> dict:
    stages = {}
    for name in ("round1", "round2", "synthesis"):
        mine = [c for c in calls if c["stage"] == name]
        if not mine:
            continue
        lengths = [c["end"] - c["start"] for c in mine]
        stages[name] = {
            "calls": len(mine),
            "wall_s": round(max(c["end"] for c in mine) - min(c["start"] for c in mine), 3),
            "sum_of_calls_s": round(sum(lengths), 3),
            "max_call_s": round(max(lengths), 3),
        }
    return stages


def sdk_defaults() -> dict:
    out = {}
    for name in ("openai", "anthropic"):
        try:
            sdk = __import__(name)
            out[name] = {
                "version": sdk.__version__,
                "read_timeout_s": sdk.DEFAULT_TIMEOUT.read,
                "max_retries": sdk.DEFAULT_MAX_RETRIES,
            }
        except ImportError:
            out[name] = None
    return out


async def measure_runner(calls: list[dict], requests: int, tickers: int) -> dict | None:
    """Run control (needs the runner): same-ticker joining and the concurrent-run cap."""
    try:
        from app.services.debate import export, runner
        from app.services.debate.llm_client import max_concurrent_runs
    except ImportError:
        return None  # the unchanged tree has no runner
    export.export_debate_report = lambda result: None  # no report file from a measurement

    def serialise(result, report_file):
        return {"ticker": result.ticker, "verdict": result.verdict}

    calls.clear()
    same = await asyncio.gather(*(runner.run_debate("VCB", ELIGIBILITY, serialise) for _ in range(requests)))
    one_ticker = {
        "requests": requests,
        "llm_calls": len(calls),  # one run's worth
        "distinct_results": len({id(result) for result in same}),  # 1: they share one
    }

    calls.clear()
    names = [f"T{index}" for index in range(tickers)]
    outcomes = await asyncio.gather(
        *(runner.run_debate(name, ELIGIBILITY, serialise) for name in names), return_exceptions=True
    )
    rejected = [outcome for outcome in outcomes if isinstance(outcome, runner.DebateBusy)]
    distinct = {
        "tickers": tickers,
        "cap": max_concurrent_runs(),
        "rejected": len(rejected),
        "llm_calls": len(calls),  # 8 per run that was allowed, none for a rejected one
    }
    return {"same_ticker": one_ticker, "distinct_tickers": distinct}


async def measure(ticker: str, call_seconds: float, block_seconds: float, requests: int, tickers: int) -> dict:
    calls: list[dict] = []
    install_stubs(call_seconds, block_seconds, calls)
    max_gap = 0.0

    async def probe() -> None:
        nonlocal max_gap
        while True:
            before = time.monotonic()
            await asyncio.sleep(PROBE_INTERVAL_SECONDS)
            max_gap = max(max_gap, time.monotonic() - before - PROBE_INTERVAL_SECONDS)

    watcher = asyncio.create_task(probe())
    started = time.monotonic()
    result = await DebateEngine().run(ticker)
    total = time.monotonic() - started
    watcher.cancel()

    stages = stage_summary(calls)
    engine_calls = len(calls)  # before the runner scenarios add their own to the same list
    run_control = await measure_runner(calls, requests, tickers)
    return {
        "ticker": ticker,
        "call_seconds": call_seconds,
        "block_seconds": block_seconds,
        "verdict": result.verdict,
        "llm_calls": engine_calls,
        "sequential_stages": len(stages),
        "stages": stages,
        "total_s": round(total, 3),
        "max_event_loop_gap_s": round(max_gap, 3),
        "run_control": run_control,
        "sdk_defaults": sdk_defaults(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ticker", default="VCB")
    parser.add_argument("--call-seconds", type=float, default=0.3)
    parser.add_argument("--block-seconds", type=float, default=0.5)
    parser.add_argument("--requests", type=int, default=5)
    parser.add_argument("--tickers", type=int, default=4)
    args = parser.parse_args()
    report = asyncio.run(measure(args.ticker, args.call_seconds, args.block_seconds, args.requests, args.tickers))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
