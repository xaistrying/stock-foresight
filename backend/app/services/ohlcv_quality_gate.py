"""Quality gate applied to fetched OHLCV before it enters modelling.

Two tiers (design Decision 3):

- **Hard gate** — a session-over-session move beyond the widest limit any
  Vietnamese exchange allows. Nothing legitimate can produce one, so these
  rows are excluded from modelling inputs.
- **Soft flag** — a move beyond the limit of the exchange the symbol trades
  on *now*. Recorded for review but not excluding, because dated exchange
  membership is not obtainable from the listing API and symbols migrate
  between exchanges (design Decision 2), so a soft flag on a pre-migration
  row is expected rather than suspicious.

**None of the thresholds here implement any of CLAUDE.md's non-negotiable
domain rules 1-6.** They are new to this change, and the design says so
explicitly. The exchange limits themselves are market facts, not project
choices; the tolerance and the choice of the widest limit as the hard gate
are project choices, justified from measured data below.
"""

import logging
import math
from datetime import date, datetime

import numpy as np
import pandas as pd

from app.db.connection import get_connection

logger = logging.getLogger(__name__)

# Daily price limits each exchange enforces, as a fraction of the reference
# price. Market facts, not project choices. Keys are vnstock's own labels for
# the exchanges (`HSX` is HOSE).
DAILY_PRICE_LIMITS = {
    "HSX": 0.07,
    "HNX": 0.10,
    "UPCOM": 0.15,
}

# The hard gate uses the widest limit in the table, so it is correct without
# needing to know which exchange a row belonged to on its date — which is
# precisely what cannot be reconstructed (design Decision 2). That is why the
# hard tier is the one that actually gates data.
HARD_GATE_LIMIT = max(DAILY_PRICE_LIMITS.values())

# Realized moves land a hair beyond a clean limit hit because the limit
# applies to a tick-rounded reference price. Measured over the 30,051 stored
# sessions of the original 15 tickers, the largest such overshoot is 0.00059
# in log-return space; 0.002 clears it with ~3.4x headroom while still
# reproducing the design's known-answer counts exactly (see task 3.7).
#
# New threshold — implements no domain rule 1-6.
PRICE_LIMIT_TOLERANCE = 0.002

FLAG_TIER_HARD = "hard"
FLAG_TIER_SOFT = "soft"

# Why a row is flagged, which task 9.1 must count separately rather than
# lumping into one number: the three causes need different responses.
FLAG_REASON_PRICE_LIMIT = "price_limit"
FLAG_REASON_INVALID_CLOSE = "invalid_close"
FLAG_REASON_POST_HALT_RESUMPTION = "post_halt_resumption"

# A daily price limit applies session-over-session, so an ordinary market
# closure — weekends, and Tet's ~10 days — leaves it fully in force: the first
# session back is still limited against the last close before the holiday.
# A months-long trading halt is different. The reference price is reset when
# trading resumes, so a large move across the halt is neither a limit breach
# nor corrupt data, and treating it as one would neutralise a real return and
# black out 78 sessions of valid history. Set well above the widest holiday so
# only a genuine halt qualifies.
#
# New threshold — implements no domain rule 1-6.
HALT_GAP_DAYS = 30

# Promoted from a printed warning in backend/scripts/screen_ticker_volatility.py
# to an enforced filter (design Decision 5). New threshold — implements no
# domain rule 1-6. The measured fraction is stored per symbol so this can be
# re-tuned later without re-ingesting.
#
# **Re-examined against the real universe and kept at 0.15 (task 7.2).**
# Measured over the first 197 ingested symbols: mean stale-close fraction
# 0.34, max 0.999, and this cutoff excludes 56% of them. Looser cuts do not
# rescue much — 0.25 excludes 41%, 0.40 excludes 30%, and even 0.60, a stock
# whose close is unchanged three sessions in five, still excludes 24%. Much of
# HOSE below the large caps genuinely is that thin, so the fraction excluded
# is not evidence the threshold is wrong.
#
# Known weakness, deliberately accepted for now: this measure conflates
# illiquidity with coarse-grid pricing. A symbol at 0.3 on a 0.1 price grid
# *cannot* post a small move — one grid step is 33% (see `effective_limit`) —
# so it sits at unchanged closes for mechanical reasons, and a fixed threshold
# penalises low-priced symbols twice, once here and once at the gate. A
# measure that does not interact with the grid (the fraction of zero-volume
# sessions, say) would be better, and is follow-up work rather than something
# to invent at close-out: this threshold excludes from the *default* modelling
# universe while retaining every measurement, so revising it later costs a
# re-filter, not a re-ingest.
STALE_CLOSE_FRACTION_THRESHOLD = 0.15

_DELETE_FLAGS_FOR_TICKER = "DELETE FROM ohlcv_quality_flags WHERE ticker = ?"

_INSERT_FLAG = """
INSERT INTO ohlcv_quality_flags (
    ticker, date, flag_tier, flag_reason, log_return, limit_exchange,
    limit_is_unverified_fallback, flagged_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(ticker, date) DO UPDATE SET
    flag_tier = excluded.flag_tier,
    flag_reason = excluded.flag_reason,
    log_return = excluded.log_return,
    limit_exchange = excluded.limit_exchange,
    limit_is_unverified_fallback = excluded.limit_is_unverified_fallback,
    flagged_at = excluded.flagged_at
"""


def log_return_bounds(limit: float, tolerance: float = PRICE_LIMIT_TOLERANCE):
    """The (lower, upper) log-return bounds a `limit` price move implies.

    A price limit is defined on the simple return — `|close / ref - 1| <=
    limit` — so its image in log-return space is asymmetric:
    `ln(1 - limit) <= log_return <= ln(1 + limit)`. Converting each side
    exactly, rather than comparing `|log_return|` against `limit` directly,
    matters because the asymmetry grows with the limit: a legitimate UPCOM
    limit-down session is `ln(0.85) = -0.1625`, which a flat `|log| > 0.15`
    comparison would flag as corrupt — a false positive on the very exchange
    whose limit defines the hard gate.
    """
    return math.log(1.0 - limit) - tolerance, math.log(1.0 + limit) + tolerance


def soft_limit_for_exchange(exchange: str | None) -> float | None:
    """The daily price limit for `exchange`, or None if it is unknown.

    An unknown or absent exchange means no soft evaluation is possible — a
    delisted symbol carries no exchange field at all. The hard gate still
    applies, since it does not depend on exchange.
    """
    if exchange is None:
        return None
    return DAILY_PRICE_LIMITS.get(exchange)


def log_returns(closes: pd.Series) -> pd.Series:
    """Session-over-session log returns, NaN at the first row.

    A close of zero — `VKP` has one, found by the first batch dry run — makes
    the ratio zero or infinite, so the log is ±inf rather than a number.
    Those values are deliberately kept (and the numpy warning suppressed
    rather than the value discarded): ±inf is the true measured ratio, and
    `evaluate_price_limits` needs to see it to flag the row. Coercing it to
    NaN here would hide the single most corrupt row shape in the data.
    """
    closes = pd.to_numeric(closes, errors="coerce")
    with np.errstate(divide="ignore", invalid="ignore"):
        return pd.Series(np.log(closes / closes.shift(1)), index=closes.index)


def _gap_days(previous_date, current_date) -> int:
    """Calendar days between two session dates, 0 if either is unparseable.

    Unparseable means the halt test cannot be made, and the safe answer there
    is to fall through to the ordinary price-limit evaluation rather than to
    excuse a move as a resumption.
    """
    try:
        return (
            date.fromisoformat(str(current_date)) - date.fromisoformat(str(previous_date))
        ).days
    except ValueError:
        return 0


def _storable_log_return(value) -> float:
    """`value` as something the sidecar's NOT NULL REAL column can hold.

    ±inf stores and reads back faithfully; NaN does not — sqlite3 turns it
    into NULL, which the column rejects. NaN only reaches here on a row
    flagged for an invalid close with no computable return at all (the first
    stored session, or one following another invalid close), so it becomes
    `0.0` — and for those rows `flag_reason = 'invalid_close'` is what
    carries the meaning. A `0.0` there means "no return could be computed",
    not "the price did not move" (docs/DATA_DICTIONARY.md).
    """
    number = float(value)
    return 0.0 if np.isnan(number) else number


# A grid is something that recurs; a single large move is not one. Below this
# many observed steps the estimate would be inferred from the very anomaly the
# gate exists to catch — a two-row series moving 100 -> 50 would "establish" a
# grid of 50 and excuse itself — so no widening happens at all.
MIN_GRID_STEP_OBSERVATIONS = 20


def price_grid_step(closes: pd.Series, percentile: float = 25.0) -> float | None:
    """The symbol's own smallest habitual price increment, or None.

    Not read from an exchange tick table. Those describe listed HOSE stocks
    in VND bands (10/50/100), and the symbols this matters for are delisted
    names whose data does not follow them: `VKP` has five distinct closes in
    2,001 sessions — 0.3, 0.4, 0.5 — so its observed grid is 0.1, ten times
    the 0.01 a tick table would predict for that price band.

    Estimated as a low percentile of the non-zero absolute close-to-close
    changes rather than the outright minimum, so one odd print (`VKP` has a
    single 0.49 among them) cannot collapse the estimate. Returns None when
    there is too little history to call anything a grid.
    """
    numbers = pd.to_numeric(closes, errors="coerce").to_numpy(dtype=float)
    numbers = numbers[np.isfinite(numbers) & (numbers > 0)]
    if len(numbers) < 2:
        return None
    steps = np.abs(np.diff(numbers))
    steps = steps[steps > 0]
    if len(steps) < MIN_GRID_STEP_OBSERVATIONS:
        return None
    return float(np.percentile(steps, percentile))


def effective_limit(limit: float, reference_close: float, grid_step: float | None) -> float:
    """`limit` widened so that a single price-grid step is never a violation.

    A daily limit is a percentage, but prices move on a grid. When one grid
    step is worth more than the limit allows, the stock cannot trade at all
    without "breaching" it: `VKP` at 0.4 moving one 0.1 step is 25% against a
    15% limit, and the gate flagged 43 such sessions — voiding a whole
    history for doing the only thing that price level permits.

    So the limit becomes `max(limit, one grid step)` in fractional terms.
    High-priced names are untouched, because their limit is worth many grid
    steps: `VHM` at 60.30 allows 4.2 against a grid of ~0.1, and its
    2018-08-14 step of 30.07 stays hard-flagged. Two grid steps in one
    session stays flagged everywhere, which is what a genuine anomaly on a
    coarse-grid symbol looks like.
    """
    if grid_step is None or reference_close <= 0:
        return limit
    return max(limit, grid_step / reference_close)


def is_valid_close(value) -> bool:
    """Whether `value` is usable as a price: a positive, finite number.

    Zero and negative closes are not prices any exchange can produce, so a
    row carrying one is corrupt regardless of what the surrounding rows do.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return np.isfinite(number) and number > 0.0


def stale_close_fraction(closes: pd.Series) -> float:
    """Fraction of sessions whose close exactly equals the previous close.

    Definition carried over unchanged from
    `backend/scripts/screen_ticker_volatility.py` — exact float equality, and
    the first row compares against NaN and so counts as not-stale. Unlike
    that script, which uses its trailing 250-session window, this is computed
    over the symbol's full stored history as the `ohlcv-quality-gate`
    requirement specifies. See docs/DATA_DICTIONARY.md.
    """
    closes = pd.to_numeric(closes, errors="coerce")
    if len(closes) == 0:
        return 0.0
    return float((closes == closes.shift(1)).mean())


def evaluate_price_limits(
    dates: pd.Series,
    closes: pd.Series,
    exchange: str | None,
    exchange_is_unverified_fallback: bool = True,
) -> list[dict]:
    """Flag rows whose session-over-session move breaches a price limit.

    Returns one entry per flagged row, carrying the highest tier it reached.
    The hard threshold is strictly wider than every soft threshold, so a
    hard-flagged row necessarily breaches its soft threshold too;
    `flag_tier = 'hard'` implies both (see docs/DATA_DICTIONARY.md).
    """
    returns = log_returns(closes).to_numpy()
    dates = list(dates)
    close_values = list(closes)

    soft_limit = soft_limit_for_exchange(exchange)
    # Estimated once per symbol from its whole stored series, so a symbol
    # whose price grid is coarser than its limit is not flagged for every
    # move it is able to make (see `effective_limit`).
    grid_step = price_grid_step(closes)

    flags: list[dict] = []
    for index, value in enumerate(returns):
        reason = FLAG_REASON_PRICE_LIMIT
        reference = (
            float(close_values[index - 1])
            if index > 0 and is_valid_close(close_values[index - 1])
            else 0.0
        )
        hard_lower, hard_upper = log_return_bounds(
            effective_limit(HARD_GATE_LIMIT, reference, grid_step)
        )
        soft_bounds = (
            log_return_bounds(effective_limit(soft_limit, reference, grid_step))
            if soft_limit is not None
            else None
        )

        if not is_valid_close(close_values[index]):
            # The row's own price is not a price. Hard, whatever the return
            # says: this is the one row shape the gate used to skip entirely,
            # because ±inf failed its finiteness check.
            tier, limit_exchange = FLAG_TIER_HARD, None
            reason = FLAG_REASON_INVALID_CLOSE
        elif index == 0 or not is_valid_close(close_values[index - 1]):
            # No usable reference price, so no return to evaluate. The first
            # row has no predecessor; a row after an invalid close is already
            # covered by that close's own flag.
            continue
        elif _gap_days(dates[index - 1], dates[index]) > HALT_GAP_DAYS:
            # Trading resumed after a halt, so the price limit does not apply
            # across the gap (see HALT_GAP_DAYS). Recorded, never excluding:
            # the move is real, and neutralising it would delete a genuine
            # return and 78 sessions of valid indicators.
            if not np.isfinite(value) or hard_lower <= value <= hard_upper:
                continue
            tier, limit_exchange = FLAG_TIER_SOFT, exchange
            reason = FLAG_REASON_POST_HALT_RESUMPTION
        elif not np.isfinite(value):
            # Both closes are valid positive numbers, so a non-finite return
            # is not reachable — but flag rather than skip if it ever is,
            # since skipping is how the zero-close hole stayed open.
            tier, limit_exchange = FLAG_TIER_HARD, None
            reason = FLAG_REASON_INVALID_CLOSE
        elif value < hard_lower or value > hard_upper:
            tier, limit_exchange = FLAG_TIER_HARD, None
        elif soft_bounds is not None and (
            value < soft_bounds[0] or value > soft_bounds[1]
        ):
            tier, limit_exchange = FLAG_TIER_SOFT, exchange
        else:
            continue

        flags.append(
            {
                "date": dates[index],
                "flag_tier": tier,
                "flag_reason": reason,
                "log_return": _storable_log_return(value),
                # The hard tier uses the widest limit and so needs no
                # exchange; recording one would imply a dated membership
                # claim the data cannot support.
                "limit_exchange": limit_exchange,
                "limit_is_unverified_fallback": int(
                    tier == FLAG_TIER_SOFT and exchange_is_unverified_fallback
                ),
            }
        )
    return flags


def run_quality_gate(
    ticker: str,
    ohlcv: pd.DataFrame,
    exchange: str | None,
    exchange_is_unverified_fallback: bool = True,
    date_column: str = "date",
) -> dict:
    """Evaluate every check for one ticker's OHLCV. Pure — no database.

    `ohlcv` must be a single ticker's rows sorted by date ascending.
    """
    if ohlcv.empty:
        return {
            "ticker": ticker,
            "flags": [],
            "hard_flag_count": 0,
            "soft_flag_count": 0,
            "flag_counts_by_reason": {},
            "stale_close_fraction": 0.0,
            "fails_liquidity_filter": False,
        }

    flags = evaluate_price_limits(
        ohlcv[date_column],
        ohlcv["close"],
        exchange,
        exchange_is_unverified_fallback,
    )
    fraction = stale_close_fraction(ohlcv["close"])
    by_reason: dict[str, int] = {}
    for flag in flags:
        key = f"{flag['flag_tier']}:{flag['flag_reason']}"
        by_reason[key] = by_reason.get(key, 0) + 1
    return {
        "ticker": ticker,
        "flags": flags,
        "hard_flag_count": sum(1 for f in flags if f["flag_tier"] == FLAG_TIER_HARD),
        "soft_flag_count": sum(1 for f in flags if f["flag_tier"] == FLAG_TIER_SOFT),
        # Task 9.1 needs the three causes counted apart, not one total: a
        # missed split, an invalid price, and a post-halt resumption call for
        # different responses, and conflating them would skew Decision 9's
        # reopening trigger.
        "flag_counts_by_reason": by_reason,
        "stale_close_fraction": fraction,
        "fails_liquidity_filter": fraction > STALE_CLOSE_FRACTION_THRESHOLD,
    }


def persist_quality_gate_result(result: dict, conn=None) -> None:
    """Write flags to the sidecar and the liquidity measurement to the
    universe entry.

    The ticker's existing flags are deleted first: the gate is recomputed over
    the whole history on every load, so a row that no longer breaches a limit
    (because the vendor corrected it) must lose its flag rather than linger.

    Pass `conn` to write through the caller's own connection, exactly as
    `hard_flagged_dates` allows. Callers that already hold one should always
    do so — otherwise this opens a second connection to `DB_PATH`, which
    would write to the real database even where the caller has been pointed
    at another one.
    """
    ticker = result["ticker"]
    now = datetime.now().isoformat()
    rows = [
        (
            ticker,
            flag["date"],
            flag["flag_tier"],
            flag["flag_reason"],
            flag["log_return"],
            flag["limit_exchange"],
            flag["limit_is_unverified_fallback"],
            now,
        )
        for flag in result["flags"]
    ]
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        conn.execute(_DELETE_FLAGS_FOR_TICKER, (ticker,))
        if rows:
            conn.executemany(_INSERT_FLAG, rows)
        updated = conn.execute(
            """
            UPDATE ticker_universe
               SET stale_close_fraction = ?,
                   fails_liquidity_filter = ?,
                   updated_at = ?
             WHERE symbol = ?
            """,
            (
                result["stale_close_fraction"],
                int(result["fails_liquidity_filter"]),
                now,
                ticker,
            ),
        ).rowcount
        if owns_connection:
            # Only commit a connection we opened. Committing a caller's
            # connection would also commit whatever else it had pending,
            # turning "persist these flags" into "commit my caller's
            # transaction".
            conn.commit()
    finally:
        if owns_connection:
            conn.close()
    if updated == 0:
        # Not fatal: the flags are still persisted and inspectable. It means
        # this ticker is not in the universe, which task 5.1's backfill exists
        # to resolve for the originally-loaded tickers.
        logger.warning(
            "No ticker_universe row for %s; stale-close fraction not recorded",
            ticker,
        )


def level_shift_dates(ticker: str, conn=None) -> set[str]:
    """Hard-flagged dates that represent a *persistent level shift*.

    Narrower than `hard_flagged_dates`, and the distinction matters because
    the two consequences of a hard flag are not the same thing:

    - Neutralising the session's return, and nulling the targets whose
      lookahead spans it, is right for **every** hard flag — an ±inf return
      out of a zero close would wreck a volatility window as thoroughly as a
      missed split would.
    - The 78-session indicator blackout and the segmentation of the
      recursive indicators (design Decisions 9 and 11) are corrections for a
      *change of price scale*. An invalid close is not a change of scale, it
      is absent data — and it arrives in long runs (`DBH` has 197 such rows,
      `AUM` 120 consecutive), so treating each as a scale change would shred
      the series into hundreds of one-row segments and black out 78 sessions
      apiece.

    Non-price rows are dropped from the modelled series instead
    (`recompute_features_for_ticker`), which turns the run into the calendar
    gap it actually is and lets `near_gap` handle it through machinery that
    already exists.
    """
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT date FROM ohlcv_quality_flags "
                "WHERE ticker = ? AND flag_tier = ? AND flag_reason = ?",
                (ticker, FLAG_TIER_HARD, FLAG_REASON_PRICE_LIMIT),
            )
        }
    finally:
        if owns_connection:
            conn.close()


def hard_flagged_dates(ticker: str, conn=None) -> set[str]:
    """Dates whose session-over-session return is hard-flagged for `ticker`.

    Consumers use this to keep one spurious return out of every window
    containing it (`ohlcv-quality-gate`: flagged rows must not silently enter
    volatility or feature computation).

    Pass `conn` to read through the caller's own connection. Callers that
    already hold one should always do so — otherwise this opens a second
    connection to `DB_PATH`, which would read the real database even where
    the caller has been pointed at another one.
    """
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT date FROM ohlcv_quality_flags "
                "WHERE ticker = ? AND flag_tier = ?",
                (ticker, FLAG_TIER_HARD),
            )
        }
    finally:
        if owns_connection:
            conn.close()


def neutralise_hard_flagged_returns(
    dates, returns: pd.Series, flagged: set[str]
) -> pd.Series:
    """`returns` with the entries at hard-flagged dates replaced by NaN.

    Neutralising the return rather than repairing the price is deliberate.
    The one genuine bad row measured in this data — `VHM` 2018-08-14, a
    60.30 -> 30.23 step across all four OHLC fields — is a missed 2:1 split
    adjustment, not a bad print: the levels on each side are internally
    consistent and only the return across the boundary is spurious.
    Interpolating a close would corrupt both sides; dropping the single
    return is exactly the defect.
    """
    if not flagged:
        return returns
    mask = pd.Series([str(d) in flagged for d in dates], index=returns.index)
    return returns.mask(mask)
