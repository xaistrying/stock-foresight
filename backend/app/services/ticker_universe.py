"""Construction and querying of the ticker universe.

The universe is what the system *knows about*, which is deliberately not the
same set as `tickers` (what has been loaded) or `TRAINING_TICKERS` (what the
retired direction model was trained on). Design rationale:
`openspec/changes/hose-universe-ingestion/design.md` Decisions 1 and 2.
"""

import logging
from datetime import date, datetime

import pandas as pd

from app.vnstock_guard import install as _install_vnstock_guard

_install_vnstock_guard()  # must precede any vnstock import (docs/KNOWN_ISSUES.md)

from vnstock.explorer.vci.listing import Listing  # noqa: E402

from app.db.connection import get_connection  # noqa: E402

logger = logging.getLogger(__name__)

# The listing shares one response across every instrument the exchanges trade.
# Only ordinary stocks are tickers for this system's purposes; covered
# warrants, ETFs, bonds, futures, unit trusts, and debentures are not.
STOCK_INSTRUMENT_TYPE = "STOCK"
NON_STOCK_INSTRUMENT_TYPES = frozenset(
    {"CW", "ETF", "BOND", "FU", "UNIT_TRUST", "DEBENTURE"}
)

# vnstock's own labels in the listing's `exchange` column. `HSX` is HOSE.
HOSE_EXCHANGE = "HSX"
DELISTED_EXCHANGE = "DELISTED"

LISTING_STATUS_LISTED = "listed"
LISTING_STATUS_DELISTED = "delisted"

INGESTION_STATE_PENDING = "pending"
INGESTION_STATE_OK = "ok"
# A load whose fetch succeeded but whose feature recomputation raised. Not
# `ok`: `ingestion_state` doubles as the batch runner's resume point, and a
# symbol with no features is not done (`docs/DATA_DICTIONARY.md`).
INGESTION_STATE_FEATURES_FAILED = "features_failed"
# An unexpected exception, as opposed to a fetch outcome `load_ticker` itself
# classifies (`rate_limited`, `no_data`, `invalid_symbol`), which the batch
# runner records verbatim so a resume can tell a transient failure from a
# permanent one (task 6.4).
INGESTION_STATE_FAILED = "failed"

# States a resumed run should not retry by default: the symbol will keep
# returning the same answer, and a rate-limited call spent rediscovering it is
# a call not spent on a symbol that might succeed (task 6.3).
PERMANENT_FAILURE_STATES = frozenset({"no_data", "invalid_symbol"})

# Columns sourced from the listing. A re-run of universe construction refreshes
# only these; observed session ranges, quality measurements, filter flags, and
# ingestion state are owned by ingestion and must survive reconstruction.
_UPSERT_UNIVERSE_FROM_LISTING = """
INSERT INTO ticker_universe (
    symbol, exchange, exchange_is_unverified_fallback, icb_code2,
    listing_status, ingestion_state, updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(symbol) DO UPDATE SET
    exchange = excluded.exchange,
    exchange_is_unverified_fallback = excluded.exchange_is_unverified_fallback,
    icb_code2 = excluded.icb_code2,
    listing_status = excluded.listing_status,
    updated_at = excluded.updated_at
"""


class UniverseConstructionError(RuntimeError):
    """Raised when a listing response is not plausible enough to persist.

    Persisting a bad listing would silently shrink or corrupt the universe,
    and the universe is what every later step reads. Failing loudly and
    leaving the previous universe in place is the safer outcome.
    """


def fetch_listing(lang: str = "vi") -> pd.DataFrame:
    """Fetch the raw exchange listing. Isolated so tests can substitute a
    fixture without touching the network."""
    return Listing().symbols_by_exchange(lang=lang)


def stock_rows(listing: pd.DataFrame) -> pd.DataFrame:
    """Retain only ordinary-stock rows.

    Filtering positively on `type == STOCK` rather than negatively on the
    known non-stock types means an instrument type vnstock adds later is
    excluded by default rather than silently treated as a ticker.
    """
    if "type" not in listing.columns:
        raise UniverseConstructionError(
            "listing response has no `type` column; cannot separate stocks "
            f"from other instruments (columns: {list(listing.columns)})"
        )
    return listing[listing["type"] == STOCK_INSTRUMENT_TYPE]


def _row_value(row: pd.Series, column: str) -> str | None:
    """Read a listing cell as a stripped string, or None when absent or NaN.

    `icb_code2` is missing for some symbols; task 2.4 requires storing null
    and continuing rather than skipping the symbol.
    """
    if column not in row.index:
        return None
    value = row[column]
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def build_universe_entries(listing: pd.DataFrame) -> list[dict]:
    """Turn a listing response into universe entries for HOSE and delisted
    stocks. Pure — no network, no database."""
    stocks = stock_rows(listing)
    total_stock_rows = len(stocks)

    hose = stocks[stocks["exchange"] == HOSE_EXCHANGE]
    delisted = stocks[stocks["exchange"] == DELISTED_EXCHANGE]

    if len(hose) == 0:
        raise UniverseConstructionError(
            "listing returned zero HOSE stock rows; refusing to persist an "
            "empty universe"
        )
    # The spec also asks that a count exceeding the listing's own stock rows
    # be treated as a construction failure. As written that can never fire —
    # `hose` and `delisted` are disjoint masked subsets of `stocks`, so their
    # sum is bounded by construction. What *can* go wrong and produce the
    # same symptom is a listing that repeats a symbol, which would inflate
    # the universe with duplicates, so that is what is actually checked.
    selected = pd.concat([hose, delisted])
    duplicates = selected["symbol"].duplicated().sum()
    if duplicates:
        raise UniverseConstructionError(
            f"listing contains {duplicates} duplicate symbol row(s) among "
            f"{len(selected)} selected of {total_stock_rows} stock rows; "
            "refusing to persist a universe built from a repeated listing"
        )

    entries: list[dict] = []
    for frame, status, keep_exchange in (
        (hose, LISTING_STATUS_LISTED, True),
        (delisted, LISTING_STATUS_DELISTED, False),
    ):
        for _, row in frame.iterrows():
            symbol = _row_value(row, "symbol")
            if symbol is None:
                logger.warning("Skipping listing row with no symbol: %s", dict(row))
                continue
            entries.append(
                {
                    "symbol": symbol,
                    # Delisted rows carry no exchange field — `DELISTED` is a
                    # status, not a venue — so exchange stays null rather than
                    # asserting one (design Decision 2, open question 2).
                    "exchange": HOSE_EXCHANGE if keep_exchange else None,
                    # Always a fallback for now: the listing gives current
                    # state only, and symbols migrate between exchanges.
                    "exchange_is_unverified_fallback": 1,
                    "icb_code2": _row_value(row, "icb_code2"),
                    "listing_status": status,
                }
            )
    return entries


def construct_universe(listing: pd.DataFrame | None = None) -> dict:
    """Build the universe from the listing and persist it.

    Fetches OHLCV for nothing — this step is verifiable on its own (design
    Migration Plan step 2). Returns a summary of what was persisted.
    """
    if listing is None:
        listing = fetch_listing()
    entries = build_universe_entries(listing)
    now = datetime.now().isoformat()
    rows = [
        (
            entry["symbol"],
            entry["exchange"],
            entry["exchange_is_unverified_fallback"],
            entry["icb_code2"],
            entry["listing_status"],
            INGESTION_STATE_PENDING,
            now,
        )
        for entry in entries
    ]
    conn = get_connection()
    try:
        conn.executemany(_UPSERT_UNIVERSE_FROM_LISTING, rows)
        conn.commit()
    finally:
        conn.close()

    listed = sum(1 for e in entries if e["listing_status"] == LISTING_STATUS_LISTED)
    summary = {
        "total": len(entries),
        "listed": listed,
        "delisted": len(entries) - listed,
        "missing_icb_code2": sum(1 for e in entries if e["icb_code2"] is None),
    }
    logger.info("Universe constructed: %s", summary)
    return summary


def universe_as_of(as_of: date | str) -> list[str]:
    """Symbols in the universe as of `as_of`, survivorship-bias-free.

    Membership is decided by observed session range, not by any historical
    index-membership record — the listing API cannot supply one (design
    Decision 2). A symbol whose first observed session is on or before
    `as_of` is in the universe, including one delisted afterwards; a symbol
    first observed after `as_of` did not exist then and is excluded.

    Symbols never loaded have no observed range and so cannot be placed in
    time; they are excluded rather than assumed to have existed.
    """
    as_of_iso = as_of.isoformat() if isinstance(as_of, date) else as_of
    conn = get_connection()
    try:
        return [
            row[0]
            for row in conn.execute(
                """
                SELECT symbol FROM ticker_universe
                WHERE first_observed_session IS NOT NULL
                  AND first_observed_session <= ?
                ORDER BY symbol
                """,
                (as_of_iso,),
            )
        ]
    finally:
        conn.close()


# Owned by ingestion, not by construction: a re-run of `construct_universe`
# must not clear these (see `_UPSERT_UNIVERSE_FROM_LISTING`, which touches only
# the listing-sourced columns).
_UPDATE_UNIVERSE_FROM_INGESTION = """
UPDATE ticker_universe
   SET first_observed_session = ?,
       last_observed_session = ?,
       observed_session_count = ?,
       ingestion_state = ?,
       ingestion_last_error = ?,
       ingestion_attempted_at = ?,
       updated_at = ?
 WHERE symbol = ?
"""


def universe_entry(symbol: str, conn=None) -> dict | None:
    """The universe row for `symbol`, or None if it is not in the universe.

    Ingestion reads this for the exchange to evaluate price limits against.
    A symbol with no universe row is not an error — the originally-loaded 15
    predate the universe table, and task 5.1's backfill exists to resolve
    that — so callers must handle None rather than assume membership.

    Pass `conn` to read through the caller's own connection; a caller that
    already holds one should always do so, or this opens a second connection
    to `DB_PATH` and would read the real database even where the caller has
    been pointed at another one.
    """
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM ticker_universe WHERE symbol = ?", (symbol,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip([c[0] for c in cursor.description], row))
    finally:
        if owns_connection:
            conn.close()


def record_ingestion_result(
    symbol: str,
    *,
    first_observed_session: str | None,
    last_observed_session: str | None,
    observed_session_count: int | None,
    ingestion_state: str,
    ingestion_last_error: str | None = None,
    conn=None,
) -> bool:
    """Record what a load observed for `symbol`. Returns whether a row matched.

    The observed range is the only thing point-in-time reconstruction has to
    work from (design Decision 2), and `observed_session_count` is what the
    minimum-history threshold is later picked against (task 7.1) — neither is
    populated by universe construction, so ingestion has to write them.

    A False return means the symbol is not in the universe. Deliberately not
    an error: the load itself succeeded and its data is persisted, and
    inserting a universe row here would fabricate listing status and exchange
    that only the listing can supply.
    """
    attempted_at = datetime.now().isoformat()
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        updated = conn.execute(
            _UPDATE_UNIVERSE_FROM_INGESTION,
            (
                first_observed_session,
                last_observed_session,
                observed_session_count,
                ingestion_state,
                ingestion_last_error,
                attempted_at,
                attempted_at,
                symbol,
            ),
        ).rowcount
        if owns_connection:
            # See `persist_quality_gate_result`: committing a supplied
            # connection would commit the caller's pending work too.
            conn.commit()
    finally:
        if owns_connection:
            conn.close()
    if updated == 0:
        logger.warning(
            "No ticker_universe row for %s; observed range and ingestion "
            "state not recorded",
            symbol,
        )
    return updated > 0


# Chosen 2026-09-07 from what the pipeline needs, not from the shape of the
# distribution (task 7.1). The distribution is no help here: it is bimodal —
# most symbols sit at the ~2,000-session tier ceiling and a small tail is very
# short — so there is no natural gap to cut at. What is defensible is the
# arithmetic of the pipeline itself: 78 sessions vanish to the indicator
# warm-up (`HARD_FLAG_BLACKOUT_SESSIONS` / Senkou Span B) and the HAR-RV
# volatility model needs 65 sessions of closes plus 78 of warm-up. 250 sessions
# — about one trading year — leaves ~170 usable rows after warm-up, enough for
# both with room to spare.
#
# New threshold — implements no domain rule 1-6. Symbols below it are flagged,
# never deleted, so this is re-tunable without re-ingesting.
MINIMUM_HISTORY_SESSIONS = 250


def apply_minimum_history_filter(
    minimum_sessions: int = MINIMUM_HISTORY_SESSIONS, conn=None
) -> dict:
    """Flag ingested symbols with fewer than `minimum_sessions` stored rows.

    Flags, never deletes (task 7.4): the exclusion stays visible and
    reversible, and the measured `observed_session_count` remains so the
    threshold can be re-tuned without re-ingesting — the same posture the
    liquidity filter takes.

    Only symbols that have actually been ingested are touched. A symbol with
    no observed count has not been measured, and marking it below-threshold
    would confuse "too short" with "not looked at yet".
    """
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE ticker_universe
               SET below_minimum_history = CASE
                       WHEN observed_session_count < ? THEN 1 ELSE 0 END,
                   updated_at = ?
             WHERE observed_session_count IS NOT NULL
            """,
            (minimum_sessions, datetime.now().isoformat()),
        )
        measured = cursor.rowcount
        below = conn.execute(
            "SELECT COUNT(*) FROM ticker_universe WHERE below_minimum_history = 1"
        ).fetchone()[0]
        if owns_connection:
            conn.commit()
    finally:
        if owns_connection:
            conn.close()
    summary = {
        "minimum_sessions": minimum_sessions,
        "measured": measured,
        "below_minimum": below,
    }
    logger.info("Minimum-history filter applied: %s", summary)
    return summary


def modelling_universe(
    *,
    as_of: date | str | None = None,
    include_delisted: bool = True,
    conn=None,
) -> list[str]:
    """Symbols that pass the universe's default filters (task 7.3).

    This is the enforced boundary the `ohlcv-quality-gate` requirement asks
    for: symbols failing the liquidity filter or the minimum-history filter
    are excluded from the default modelling universe, while their data and
    their measurements stay in place.

    `as_of` applies **stricter** point-in-time membership than
    `universe_as_of`: the symbol must have been *trading* at that date, so
    its observed range has to span it on both sides. `universe_as_of`
    implements the `ticker-universe` spec's "includes or precedes `D`",
    which by design keeps a symbol delisted long before `D` in the set —
    right for asking "what could this history have been built from", wrong
    for cross-sectional ranking on a shared as-of date, where a company
    dead for a decade cannot be ranked. Pick deliberately.

    Delisted symbols are included by default, since excluding them is
    exactly the survivorship bias this change exists to remove; pass
    `include_delisted=False` for a tradeable-today list.
    """
    clauses = [
        "ingestion_state = ?",
        "COALESCE(fails_liquidity_filter, 0) = 0",
        "COALESCE(below_minimum_history, 0) = 0",
    ]
    params: list = [INGESTION_STATE_OK]
    if not include_delisted:
        clauses.append("listing_status = ?")
        params.append(LISTING_STATUS_LISTED)
    if as_of is not None:
        as_of_iso = as_of.isoformat() if isinstance(as_of, date) else as_of
        clauses.append("first_observed_session <= ?")
        clauses.append("last_observed_session >= ?")
        params.extend([as_of_iso, as_of_iso])

    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        return [
            row[0]
            for row in conn.execute(
                "SELECT symbol FROM ticker_universe WHERE "
                + " AND ".join(clauses)
                + " ORDER BY symbol",
                tuple(params),
            )
        ]
    finally:
        if owns_connection:
            conn.close()


def last_session_spread(
    listing_status: str = LISTING_STATUS_LISTED, conn=None
) -> dict:
    """Distribution of `last_observed_session` across the modelling universe.

    Kept permanently rather than run once for the first batch (task 6.10):
    the same drift reappears on every incremental ingest, whenever a subset
    of symbols is refreshed and the rest are not.

    A ragged last-session edge is survivable for per-ticker volatility work
    but not for cross-sectional ranking, where it means comparing a stale
    ticker against a fresh universe on the same as-of date — a misalignment
    that manufactures apparent signal.

    Restricted to listed symbols by default: a delisted symbol's last session
    is years old *correctly*, so including them would swamp the measurement
    with expected staleness and hide the real thing.
    """
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT last_observed_session, COUNT(*)
              FROM ticker_universe
             WHERE last_observed_session IS NOT NULL
               AND ingestion_state = ?
               AND listing_status = ?
             GROUP BY last_observed_session
             ORDER BY last_observed_session DESC
            """,
            (INGESTION_STATE_OK, listing_status),
        ).fetchall()
    finally:
        if owns_connection:
            conn.close()

    if not rows:
        return {"symbols": 0, "by_session": []}

    by_session = [{"session": row[0], "symbols": row[1]} for row in rows]
    latest, earliest = rows[0][0], rows[-1][0]
    total = sum(row[1] for row in rows)
    return {
        "symbols": total,
        "latest_session": latest,
        "earliest_session": earliest,
        "spread_days": (date.fromisoformat(latest) - date.fromisoformat(earliest)).days,
        "distinct_sessions": len(rows),
        "symbols_at_latest": rows[0][1],
        "symbols_behind_latest": total - rows[0][1],
        "by_session": by_session,
    }
