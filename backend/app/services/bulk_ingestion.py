"""Batch ingestion of the ticker universe (tasks.md group 6).

Operator-invoked, never scheduled (design Decision 6): this codebase has
never had a scheduled job, and "when does this run" is a decision deserving
its own change rather than being smuggled in here. The CLI that drives this
module is `backend/scripts/ingest_universe.py`.

Everything here goes through `load_ticker` — the single fetch path, with its
single-call contract (`count=5000`, `source="vci"`) and its quality gate
intact. There is deliberately no second fetch implementation (task 6.1), and
no full-universe feature recomputation: `load_ticker` recomputes the one
symbol it just fetched, so a run only ever touches what it actually loaded
(task 6.5, design Decision 7).

The run is resumable by construction (task 6.3). Resumability comes from
`ticker_universe.ingestion_state`, which ingestion itself writes, so a
re-run naturally skips completed symbols with no separate checkpoint file to
keep in sync.
"""

import json
import logging
import statistics
import time
from datetime import datetime
from pathlib import Path

from app.db.connection import get_connection
from app.services.ticker_ingestion import load_ticker
from app.services.ticker_universe import (
    INGESTION_STATE_FAILED,
    INGESTION_STATE_OK,
    PERMANENT_FAILURE_STATES,
    record_ingestion_result,
)

logger = logging.getLogger(__name__)

# A rate limit is a pause, not a failure (task 6.2). The wait is long enough
# to be worth making — vnstock's community tier throttles per minute — and
# capped so a persistently throttled run ends with a recorded outcome per
# symbol rather than sleeping forever.
RATE_LIMIT_WAIT_SECONDS = 60.0
MAX_RATE_LIMIT_WAITS = 5

# Measured by the first dry run, 2026-09-07: vnstock's guest tier allows 20
# requests per minute and `load_ticker` spends about two of them per symbol
# (the run stopped for a rate limit after its tenth symbol). Fetch wall time
# was 0.8-3.9s per symbol and feature recomputation 0.2s, so neither is what
# bounds a full run — the throttle is, by an order of magnitude. Used only to
# extrapolate a dry run's cost; the run itself reacts to real rate limits.
OBSERVED_REQUESTS_PER_MINUTE = 20
REQUESTS_PER_SYMBOL = 2

# Pacing the run below the limit is the primary defence, because hitting the
# limit is far more violent than a caught exception — see
# `_is_rate_limit_exit`. Kept under 20/2 = 10 symbols a minute for margin,
# since the request count per symbol is an estimate and vnai counts against a
# wall-clock minute rather than a rolling window.
DEFAULT_SYMBOLS_PER_MINUTE = 8

# vnai's rate limiter does not raise something catchable by ordinary means: it
# calls `sys.exit(f"Rate limit exceeded. ... Process terminated.")` from a
# context manager's `__exit__` (`vnai/beam/quota.py:313`). That is a
# `SystemExit`, a BaseException, so `except Exception` does not see it and the
# whole batch dies mid-run — which is exactly what happened on the first full
# attempt, at symbol 12 of 634. `load_ticker`'s own `RateLimitError` handler
# never fires on the guest tier for the same reason: vnai exits before
# vnstock's exception can surface.
RATE_LIMIT_EXIT_MARKER = "rate limit"

# Statuses `load_ticker` reports that mean no rows arrived. Distinct from a
# symbol that fetched fine but is later excluded by a filter — the
# `bulk-ticker-ingestion` requirement is that the summary keep these apart.
FETCH_FAILURE_STATUSES = frozenset({"rate_limited", "invalid_symbol", "no_data"})

RUN_SUMMARY_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ingest_runs"


def symbols_to_ingest(
    *,
    include_ingested: bool = False,
    retry_permanent_failures: bool = False,
    listing_status: str | None = None,
    limit: int | None = None,
    conn=None,
) -> list[str]:
    """Symbols this run should attempt, in a deterministic order.

    By default symbols already marked `ok`, and symbols whose recorded
    failure will not change on a retry (`no_data`, `invalid_symbol`), are
    both skipped — which is what makes an interrupted run resumable without
    spending rate-limited calls rediscovering known-permanent failures
    (task 6.3). A symbol that failed transiently (`rate_limited`, `failed`,
    `features_failed`) is retried.

    `include_ingested` re-attempts everything, which is how the first full
    run refreshes the 15 already-loaded tickers instead of leaving them
    behind the other 619 (task 6.9).

    Ordering is by symbol rather than by insertion so a resumed run is
    predictable, and `limit` takes the first N of that order so a dry run
    over a subset is reproducible (task 6.7).
    """
    clauses: list[str] = []
    params: list = []
    if not include_ingested:
        clauses.append("ingestion_state != ?")
        params.append(INGESTION_STATE_OK)
    if not retry_permanent_failures:
        placeholders = ", ".join("?" for _ in PERMANENT_FAILURE_STATES)
        clauses.append(f"ingestion_state NOT IN ({placeholders})")
        params.extend(sorted(PERMANENT_FAILURE_STATES))
    if listing_status is not None:
        clauses.append("listing_status = ?")
        params.append(listing_status)

    sql = "SELECT symbol FROM ticker_universe"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY symbol"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        return [row[0] for row in conn.execute(sql, tuple(params))]
    finally:
        if owns_connection:
            conn.close()


def _is_rate_limit_exit(exit_request: SystemExit) -> bool:
    """Whether a `SystemExit` is vnai's rate limiter rather than a real exit.

    Matched on the message, because the only thing distinguishing the two is
    the string vnai passes to `sys.exit`. A genuine interpreter exit must
    still be honoured — swallowing every `SystemExit` would make the batch
    unkillable.
    """
    return RATE_LIMIT_EXIT_MARKER in str(exit_request.code or "").lower()


def ingest_symbol(
    symbol: str,
    *,
    rate_limit_wait: float = RATE_LIMIT_WAIT_SECONDS,
    max_rate_limit_waits: int = MAX_RATE_LIMIT_WAITS,
    sleep=time.sleep,
) -> dict:
    """Ingest one symbol. Never raises.

    Two failure modes are handled differently. A rate limit is transient, so
    this waits and retries the same symbol (task 6.2) — `load_ticker` catches
    `RateLimitError` itself and reports `status: "rate_limited"` rather than
    propagating it, so retrying is the only way not to silently lose the
    symbol. Anything else is recorded against the symbol and swallowed (task
    6.4): one malformed response must not end a 634-symbol run hours in.

    `load_ticker` records `ingestion_state` itself on a successful load, but
    returns early on a fetch failure without touching the universe row — so
    the failure states are written here, which is also what lets a resumed
    run pick the symbol up again.
    """
    waits = 0
    started = time.perf_counter()
    while True:
        timings: dict = {}
        try:
            result = load_ticker(symbol, timings=timings)
        except SystemExit as exit_request:
            # vnai's limiter calling it quits on us. Treat it exactly like the
            # `rate_limited` status: wait it out and retry the same symbol.
            # Anything else asking the process to exit is honoured.
            if not _is_rate_limit_exit(exit_request):
                raise
            if waits >= max_rate_limit_waits:
                logger.error(
                    "Giving up on %s after %d rate-limit waits", symbol, waits
                )
                record_ingestion_result(
                    symbol,
                    first_observed_session=None,
                    last_observed_session=None,
                    observed_session_count=None,
                    ingestion_state="rate_limited",
                    ingestion_last_error="rate_limited",
                )
                return {
                    "symbol": symbol,
                    "status": "rate_limited",
                    "error": "rate_limited",
                    "rows_loaded": 0,
                    "rate_limit_waits": waits,
                    "elapsed_seconds": time.perf_counter() - started,
                }
            waits += 1
            logger.warning(
                "Rate-limit exit on %s; waiting %.0fs (wait %d of %d)",
                symbol, rate_limit_wait, waits, max_rate_limit_waits,
            )
            sleep(rate_limit_wait)
            continue
        except Exception as exc:  # noqa: BLE001 — deliberate: see docstring
            logger.exception("Ingestion raised for %s", symbol)
            error = f"{type(exc).__name__}: {exc}"[:500]
            record_ingestion_result(
                symbol,
                first_observed_session=None,
                last_observed_session=None,
                observed_session_count=None,
                ingestion_state=INGESTION_STATE_FAILED,
                ingestion_last_error=error,
            )
            return {
                "symbol": symbol,
                "status": "error",
                "error": error,
                "rows_loaded": 0,
                "rate_limit_waits": waits,
                "elapsed_seconds": time.perf_counter() - started,
            }

        if result["status"] == "rate_limited" and waits < max_rate_limit_waits:
            waits += 1
            logger.warning(
                "Rate limited on %s; waiting %.0fs (wait %d of %d)",
                symbol, rate_limit_wait, waits, max_rate_limit_waits,
            )
            sleep(rate_limit_wait)
            continue
        break

    outcome = {
        "symbol": symbol,
        "status": result["status"],
        "error": None if result["status"] == "ok" else result["status"],
        "rows_loaded": result["rows_loaded"],
        "features_computed": result["features_computed"],
        "hard_flag_count": result.get("hard_flag_count"),
        "soft_flag_count": result.get("soft_flag_count"),
        "stale_close_fraction": result.get("stale_close_fraction"),
        "fails_liquidity_filter": result.get("fails_liquidity_filter"),
        "first_observed_session": result.get("available_since"),
        "rate_limit_waits": waits,
        "fetch_seconds": timings.get("fetch_seconds"),
        "features_seconds": timings.get("features_seconds"),
        "elapsed_seconds": time.perf_counter() - started,
    }

    if result["status"] != "ok":
        # The status itself becomes the state, as `docs/DATA_DICTIONARY.md`
        # documents the column: a resumed run needs to tell `no_data` (do not
        # bother again) from `rate_limited` (try again), which a single
        # `failed` state cannot express.
        record_ingestion_result(
            symbol,
            first_observed_session=None,
            last_observed_session=None,
            observed_session_count=None,
            ingestion_state=result["status"],
            ingestion_last_error=result["status"],
        )
    return outcome


def summarise(outcomes: list[dict], *, universe_size: int | None = None) -> dict:
    """Aggregate per-symbol outcomes into a run summary (task 6.6).

    Fetch failures and filter exclusions are reported separately, as the
    `bulk-ticker-ingestion` requirement demands: a symbol that never
    returned data is an operational problem to retry, while a symbol that
    fetched cleanly and then failed the liquidity filter is a modelling
    decision working as intended.

    Minimum-history exclusions are reported as the *distribution* of session
    counts rather than a count of exclusions, because the threshold does not
    exist yet — task 7.1 picks it from exactly this distribution, and a
    summary that invented one now would prejudge it.
    """
    succeeded = [o for o in outcomes if o["status"] == "ok"]
    fetch_failures: dict[str, list[str]] = {}
    for outcome in outcomes:
        if outcome["status"] == "ok":
            continue
        fetch_failures.setdefault(outcome["status"], []).append(outcome["symbol"])

    session_counts = sorted(o["rows_loaded"] for o in succeeded)
    fetch_times = [o["fetch_seconds"] for o in succeeded if o["fetch_seconds"]]
    feature_times = [o["features_seconds"] for o in succeeded if o["features_seconds"]]
    elapsed_total = sum(o["elapsed_seconds"] for o in outcomes)

    summary = {
        "generated_at": datetime.now().isoformat(),
        "attempted": len(outcomes),
        "succeeded": len(succeeded),
        "rows_loaded": sum(o["rows_loaded"] for o in succeeded),
        "fetch_failures": {
            "total": sum(len(symbols) for symbols in fetch_failures.values()),
            "by_status": {
                status: sorted(symbols) for status, symbols in sorted(fetch_failures.items())
            },
        },
        "feature_failures": sorted(
            o["symbol"] for o in succeeded if o["features_computed"] is False
        ),
        "quality_gate": {
            "hard_flags": sum(o["hard_flag_count"] or 0 for o in succeeded),
            "soft_flags": sum(o["soft_flag_count"] or 0 for o in succeeded),
            "symbols_with_hard_flags": sorted(
                o["symbol"] for o in succeeded if o["hard_flag_count"]
            ),
            "gate_not_measured": sorted(
                o["symbol"] for o in succeeded if o["hard_flag_count"] is None
            ),
        },
        "liquidity_exclusions": sorted(
            o["symbol"] for o in succeeded if o["fails_liquidity_filter"]
        ),
        "session_count_distribution": _distribution(session_counts),
        "timing": {
            "elapsed_seconds": elapsed_total,
            "fetch_seconds": sum(fetch_times),
            "features_seconds": sum(feature_times),
            "mean_seconds_per_symbol": (
                elapsed_total / len(outcomes) if outcomes else None
            ),
        },
        "rate_limit_waits": sum(o["rate_limit_waits"] for o in outcomes),
    }

    # The one cost in this change nobody had a number for (task 6.7): what a
    # dry run over N symbols implies for the whole universe.
    #
    # Scaling the measured wall time alone understates it badly. A dry run
    # short enough to stay inside the rate limit never pays for the throttle,
    # which is what actually bounds a 610-symbol run — the first dry run took
    # 1.7s per symbol unthrottled but stopped for a rate limit after ten
    # symbols. So both are reported and the larger governs.
    if universe_size and outcomes:
        processing = (elapsed_total / len(outcomes)) * universe_size
        throttled = (
            universe_size * REQUESTS_PER_SYMBOL / OBSERVED_REQUESTS_PER_MINUTE
        ) * 60.0
        summary["timing"]["extrapolated_processing_seconds"] = processing
        summary["timing"]["extrapolated_throttled_seconds"] = throttled
        summary["timing"]["extrapolated_full_run_seconds"] = max(processing, throttled)
        summary["timing"]["extrapolated_from"] = {
            "measured_symbols": len(outcomes),
            "universe_size": universe_size,
            "bound_by": "rate_limit" if throttled >= processing else "processing",
            "requests_per_minute": OBSERVED_REQUESTS_PER_MINUTE,
            "requests_per_symbol": REQUESTS_PER_SYMBOL,
        }
    return summary


def _distribution(values: list[int]) -> dict:
    """Min/median/max plus the low decile, which is what a minimum-history
    threshold is actually chosen against (task 7.1)."""
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": values[0],
        "p10": values[max(0, int(len(values) * 0.10) - 1)],
        "median": int(statistics.median(values)),
        "max": values[-1],
    }


def run_batch(
    symbols: list[str],
    *,
    rate_limit_wait: float = RATE_LIMIT_WAIT_SECONDS,
    max_rate_limit_waits: int = MAX_RATE_LIMIT_WAITS,
    pause_seconds: float = 0.0,
    universe_size: int | None = None,
    sleep=time.sleep,
    on_outcome=None,
    journal_path: Path | None = None,
) -> tuple[dict, list[dict]]:
    """Ingest `symbols` in order, returning `(summary, outcomes)`.

    `on_outcome(index, total, outcome)` is called after each symbol so a CLI
    can report progress live — an hours-long run that prints nothing until it
    finishes is indistinguishable from a hung one.

    `journal_path` appends each outcome as a JSON line the moment it happens.
    The end-of-run summary is written by `write_run_summary`, which a run
    killed outright — a timeout, a SIGTERM, a closed laptop — never reaches;
    the journal is what survives that, and it is the only record of the
    timing measurements a rerun cannot reproduce.
    """
    outcomes: list[dict] = []
    interrupted = False
    for index, symbol in enumerate(symbols):
        try:
            outcome = ingest_symbol(
                symbol,
                rate_limit_wait=rate_limit_wait,
                max_rate_limit_waits=max_rate_limit_waits,
                sleep=sleep,
            )
        except KeyboardInterrupt:
            # An hours-long run is going to be interrupted sometimes. Every
            # completed symbol is already committed, so return what happened
            # rather than discarding the run's own record of itself.
            logger.warning("Interrupted while ingesting %s", symbol)
            interrupted = True
            break
        outcomes.append(outcome)
        if journal_path is not None:
            _append_journal(journal_path, outcome)
        if on_outcome is not None:
            on_outcome(index, len(symbols), outcome)
        if pause_seconds and index + 1 < len(symbols):
            sleep(pause_seconds)

    summary = summarise(outcomes, universe_size=universe_size)
    summary["interrupted"] = interrupted
    summary["selected"] = len(symbols)
    return summary, outcomes


def _append_journal(path: Path, outcome: dict) -> None:
    """Append one outcome as a JSON line, flushed immediately.

    Best-effort: a journal that cannot be written must not end the run it
    exists to record.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(outcome, default=str) + "\n")
    except OSError:
        logger.exception("Could not append to run journal %s", path)


def write_run_summary(
    summary: dict, outcomes: list[dict], *, directory: Path | None = None
) -> Path:
    """Persist a run's summary and per-symbol outcomes to a JSON file.

    The `bulk-ticker-ingestion` requirement is that a summary outlive the
    process that produced it. A file under `backend/data/` rather than a
    table: it is an operational record of one run, not modelling state, and
    nothing reads it programmatically.
    """
    directory = directory or RUN_SUMMARY_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = directory / f"ingest_run_{stamp}.json"
    path.write_text(
        json.dumps({"summary": summary, "outcomes": outcomes}, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Run summary written to %s", path)
    return path
