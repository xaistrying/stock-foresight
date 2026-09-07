"""
Batch ingestion of the ticker universe (hose-universe-ingestion, task group 6
/ design Migration Plan step 5).

Operator-invoked, not scheduled (design Decision 6). All logic lives in
`app.services.bulk_ingestion`; this is the CLI around it, so the behaviour is
testable without a subprocess.

NETWORK-BOUND and WRITING. One rate-limited vnstock call per symbol, plus a
full per-ticker feature recomputation each. Expect hours for the full 634.
Resumable: re-running picks up where it stopped, because ingestion state
lives on each universe row rather than in a checkpoint file.

Run from the project root:

    # Dry run first (task 6.7) — 15 symbols, timing split, extrapolation
    python backend/scripts/ingest_universe.py --limit 15

    # A named subset, e.g. the short-history and delisted cases
    python backend/scripts/ingest_universe.py --symbols XDC,VSP,VKP

    # The full run, refreshing the 15 already-ingested tickers too (6.8/6.9)
    python backend/scripts/ingest_universe.py --include-ingested

    # Just the last-session spread check (task 6.10), no ingestion
    python backend/scripts/ingest_universe.py --spread-only

Every run writes a durable JSON summary under `backend/data/ingest_runs/`.

## Going faster than the guest tier

Pacing defaults to 8 symbols a minute because an unauthenticated environment
is vnstock's *guest* tier: 20 requests a minute, and a load spends about two
of them. Verified 2026-09-07 against `vnai.beam.auth.authenticator`, which
reports `guest — 20 requests/minute, 1200/hour`.

A **free** Community account triples that to 60/minute. No application code
is involved: `vnai` reads the key itself, from either the
`VNSTOCK_API_KEY` environment variable or `~/.vnstock/api_key.json` (written
by `vnai.beam.auth`'s `setup_api_key`). So the whole difference is one
variable:

    # register at https://vnstocks.com/login, then
    VNSTOCK_API_KEY=... python backend/scripts/ingest_universe.py \
        --include-ingested --symbols-per-minute 25

which takes a full 634-symbol run from ~80 minutes to ~25. Keep the key out
of shell history and out of the repo — pass it as an environment variable,
never as an argument. Paid Sponsor tiers reach 180-600/minute; the 8-year
history ceiling is a separate limit that a Community key does *not* lift.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.bulk_ingestion import (  # noqa: E402
    DEFAULT_SYMBOLS_PER_MINUTE,
    MAX_RATE_LIMIT_WAITS,
    RATE_LIMIT_WAIT_SECONDS,
    RUN_SUMMARY_DIR,
    run_batch,
    symbols_to_ingest,
    write_run_summary,
)
from app.services.ticker_universe import last_session_spread  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


def _print_progress(index: int, total: int, outcome: dict) -> None:
    detail = (
        f"{outcome['rows_loaded']:>5} rows"
        if outcome["status"] == "ok"
        else f"      {outcome['status']}"
    )
    flags = ""
    if outcome.get("hard_flag_count"):
        flags += f"  {outcome['hard_flag_count']} HARD"
    if outcome.get("fails_liquidity_filter"):
        flags += "  FAILS LIQUIDITY"
    if outcome.get("features_computed") is False:
        flags += "  FEATURES FAILED"
    print(
        f"[{index + 1:>4}/{total}] {outcome['symbol']:<8}{detail}"
        f"  {outcome['elapsed_seconds']:>6.1f}s{flags}",
        flush=True,
    )


def _print_spread(spread: dict) -> None:
    print("\nLast-session spread across the listed, ingested universe (6.10):")
    if not spread["symbols"]:
        print("  no ingested listed symbols yet")
        return
    print(f"  symbols:              {spread['symbols']}")
    print(f"  latest session:       {spread['latest_session']}"
          f"  ({spread['symbols_at_latest']} symbols)")
    print(f"  earliest session:     {spread['earliest_session']}")
    print(f"  spread:               {spread['spread_days']} days across "
          f"{spread['distinct_sessions']} distinct last sessions")
    print(f"  behind latest:        {spread['symbols_behind_latest']}")
    if spread["symbols_behind_latest"]:
        print("  NOTE: a ragged edge is not safe for cross-sectional ranking "
              "on a shared as-of date.")


def _print_summary(summary: dict) -> None:
    timing = summary["timing"]
    print("\n--- run summary ---")
    print(f"attempted:              {summary['attempted']}")
    print(f"succeeded:              {summary['succeeded']}")
    print(f"rows loaded:            {summary['rows_loaded']}")
    print(f"fetch failures:         {summary['fetch_failures']['total']}")
    for status, symbols in summary["fetch_failures"]["by_status"].items():
        print(f"  {status:<20} {len(symbols)}: {', '.join(symbols[:12])}"
              + (" ..." if len(symbols) > 12 else ""))
    if summary["feature_failures"]:
        print(f"feature failures:       {len(summary['feature_failures'])}: "
              f"{', '.join(summary['feature_failures'][:12])}")
    gate = summary["quality_gate"]
    print(f"hard flags:             {gate['hard_flags']} across "
          f"{len(gate['symbols_with_hard_flags'])} symbol(s)")
    print(f"soft flags:             {gate['soft_flags']}")
    if gate["gate_not_measured"]:
        print(f"gate not measured:      {len(gate['gate_not_measured'])}")
    print(f"liquidity exclusions:   {len(summary['liquidity_exclusions'])}")
    dist = summary["session_count_distribution"]
    if dist["count"]:
        print(f"session counts:         min {dist['min']}, p10 {dist['p10']}, "
              f"median {dist['median']}, max {dist['max']}"
              "   (task 7.1 picks the minimum-history threshold from this)")
    print(f"rate-limit waits:       {summary['rate_limit_waits']}")
    print(f"elapsed:                {timing['elapsed_seconds']:.1f}s "
          f"(fetch {timing['fetch_seconds']:.1f}s, "
          f"features {timing['features_seconds']:.1f}s)")
    if timing.get("mean_seconds_per_symbol"):
        print(f"mean per symbol:        {timing['mean_seconds_per_symbol']:.1f}s")
    if timing.get("extrapolated_full_run_seconds"):
        measured = timing["extrapolated_from"]
        print(f"extrapolated full run:  "
              f"{timing['extrapolated_full_run_seconds'] / 3600:.1f}h for "
              f"{measured['universe_size']} symbols, bound by "
              f"{measured['bound_by']}, from {measured['measured_symbols']} "
              f"measured")
        print(f"  processing-bound:     "
              f"{timing['extrapolated_processing_seconds'] / 3600:.1f}h")
        print(f"  rate-limit-bound:     "
              f"{timing['extrapolated_throttled_seconds'] / 3600:.1f}h "
              f"(at {measured['requests_per_minute']} req/min, "
              f"{measured['requests_per_symbol']} req/symbol)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int,
        help="ingest at most N symbols — use for the task 6.7 dry run",
    )
    parser.add_argument(
        "--symbols",
        help="comma-separated symbols to ingest instead of selecting from the "
             "universe (still recorded against their universe rows)",
    )
    parser.add_argument(
        "--include-ingested", action="store_true",
        help="re-attempt symbols already marked ok, rather than resuming "
             "(tasks 6.3/6.9 — the first full run wants this so the original "
             "15 do not stay behind the other 619)",
    )
    parser.add_argument(
        "--listing-status", choices=["listed", "delisted"],
        help="restrict to listed or delisted symbols",
    )
    parser.add_argument(
        "--symbols-per-minute", type=float, default=DEFAULT_SYMBOLS_PER_MINUTE,
        help="pace the run to this many symbols a minute (default "
             f"{DEFAULT_SYMBOLS_PER_MINUTE:g}). vnstock's guest tier allows 20 "
             "requests a minute and a load spends about two, so staying under "
             "10 keeps the run below the limit. Hitting the limit is not a "
             "caught exception — vnai calls sys.exit and takes the process "
             "with it — so pacing matters more than the retry does",
    )
    parser.add_argument(
        "--pause", type=float,
        help="seconds to wait between symbols, overriding "
             "--symbols-per-minute",
    )
    parser.add_argument(
        "--rate-limit-wait", type=float, default=RATE_LIMIT_WAIT_SECONDS,
        help=f"seconds to wait out a rate limit (default {RATE_LIMIT_WAIT_SECONDS:.0f})",
    )
    parser.add_argument(
        "--max-rate-limit-waits", type=int, default=MAX_RATE_LIMIT_WAITS,
        help=f"give up on a symbol after this many waits (default {MAX_RATE_LIMIT_WAITS})",
    )
    parser.add_argument(
        "--retry-permanent-failures", action="store_true",
        help="also retry symbols recorded as no_data or invalid_symbol, which "
             "a resume skips by default (task 6.3)",
    )
    parser.add_argument(
        "--spread-only", action="store_true",
        help="report the last-session spread (task 6.10) and exit without "
             "ingesting anything",
    )
    parser.add_argument(
        "--list-only", action="store_true",
        help="print the symbols this run would attempt, then exit",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"FAIL: no database at {DB_PATH}")
        return 1

    if args.spread_only:
        _print_spread(last_session_spread())
        return 0

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = symbols_to_ingest(
            include_ingested=args.include_ingested,
            retry_permanent_failures=args.retry_permanent_failures,
            listing_status=args.listing_status,
            limit=args.limit,
        )

    if not symbols:
        print("Nothing to ingest — every selected symbol is already marked ok. "
              "Use --include-ingested to refresh them.")
        return 0

    # Extrapolation target: what a full run over everything still pending
    # would cost, which is the number a dry run exists to produce (6.7).
    universe_size = len(
        symbols_to_ingest(include_ingested=args.include_ingested,
                          retry_permanent_failures=args.retry_permanent_failures,
                          listing_status=args.listing_status)
    )

    if args.list_only:
        print(f"{len(symbols)} symbol(s) selected of {universe_size} eligible:")
        print(", ".join(symbols))
        return 0

    # Written line by line as the run proceeds, so a run killed outright
    # (timeout, SIGTERM) still leaves its per-symbol record and timings.
    journal_path = RUN_SUMMARY_DIR / (
        f"ingest_journal_{datetime.now().strftime('%Y%m%dT%H%M%S')}.jsonl"
    )
    pause = (
        args.pause
        if args.pause is not None
        else (60.0 / args.symbols_per_minute if args.symbols_per_minute > 0 else 0.0)
    )
    estimate_minutes = len(symbols) * pause / 60.0
    print(f"Ingesting {len(symbols)} of {universe_size} eligible symbol(s).")
    print(f"Pacing: {pause:.1f}s between symbols "
          f"(~{estimate_minutes:.0f} min for this run).")
    print("Resumable: interrupt with Ctrl-C and re-run to continue.")
    print(f"Journal: {journal_path}\n")

    # An interrupt is handled inside `run_batch`, which returns what it
    # completed — so the summary below is written either way, and an
    # interrupted run still leaves its own record behind.
    summary, outcomes = run_batch(
        symbols,
        rate_limit_wait=args.rate_limit_wait,
        max_rate_limit_waits=args.max_rate_limit_waits,
        pause_seconds=pause,
        universe_size=universe_size,
        on_outcome=_print_progress,
        journal_path=journal_path,
    )

    if summary["interrupted"]:
        print("\nInterrupted. Symbols completed so far are recorded; re-run "
              "to continue where this stopped.")
    _print_summary(summary)
    _print_spread(last_session_spread())
    print(f"\nSummary written to {write_run_summary(summary, outcomes)}")
    return 130 if summary["interrupted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
