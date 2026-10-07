"""
Score the debate outcome log and report how the verdicts and the band did
(`debate-outcome-log` change).

Run by hand, from the project root, after refreshing the logged tickers:
    python backend/scripts/score_debates.py [--dry-run] [--max-age-sessions N]

Reads `ohlcv` from `backend/data/app.db` READ-ONLY and reads and writes only
`backend/data/debate_log.db`. Offline: it never calls vnstock and imports nothing
from the modules `retire-direction-model` removes. Readiness is decided from
`ohlcv` content, never from the wall clock: a row is scored once its fifth market
session exists, and a scored row is never rewritten.

Every threshold below that Rules 1-6 do not cover is new and provisional.
"""

import argparse
import math
import sqlite3
import sys
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db.connection import DB_PATH as APP_DB_PATH  # noqa: E402
from app.db.connection import open_readonly  # noqa: E402
from app.db.debate_log import DEBATE_LOG_DB_PATH  # noqa: E402

HORIZON_SESSIONS = 5  # Rule 1: five trading sessions, not calendar days
MAX_AGE_SESSIONS_DEFAULT = 0  # provisional: the run happened on the as_of session
REVISION_TOLERANCE = 0.001  # provisional: log-close revision worth reporting (0.1%)
BLOCK_SESSIONS = 20  # provisional: as_of dates within 20 market sessions share a cluster
MIN_BLOCKS = 8  # provisional: fewer blocks and no clustered interval is printed
MIN_MARKET_TICKERS = 30  # provisional: fewer and the market baseline is unavailable
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 0
Z_95 = 1.96
HALF_WIDTH_TARGET = 0.05  # the planning line: effective n for +-5 points at p = 0.5
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"

BULL_VERDICTS = ("STRONG_BUY_SIGNAL", "BUY_SIGNAL")
BEAR_VERDICTS = ("CAUTION_SIGNAL", "STRONG_CAUTION_SIGNAL")

UPDATE_OUTCOME = (
    "UPDATE debate_log SET outcome_status = ?, scored_at = ?, date_t5 = ?, "
    "close_asof_at_scoring = ?, close_t5 = ?, r5 = ?, inside_band = ?, direction_hit = ? "
    "WHERE id = ? AND outcome_status IS NULL"  # a scored row is never rewritten
)


def open_app_db(path: Path = APP_DB_PATH) -> sqlite3.Connection:
    return open_readonly(path)


def open_log_db(path: Path = DEBATE_LOG_DB_PATH) -> sqlite3.Connection:
    return sqlite3.connect(path)


# ---------------------------------------------------------------------------
# Outcome definitions (fixed by the spec; tested)
# ---------------------------------------------------------------------------


def direction_hit(verdict: str, r5: float) -> int | None:
    """1 when a directional verdict's side was right; NULL otherwise. r5 == 0 is a miss."""
    if verdict in BULL_VERDICTS:
        return int(r5 > 0)
    if verdict in BEAR_VERDICTS:
        return int(r5 < 0)
    return None


def inside_band(r5: float, range_5s_pct: float | None) -> int | None:
    """r5 is a log return, the band a percentage: both in percent here."""
    if range_5s_pct is None:
        return None
    return int(abs(r5) * 100 <= range_5s_pct)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _close(app_conn: sqlite3.Connection, ticker: str, date: str) -> float | None:
    row = app_conn.execute(
        "SELECT close FROM ohlcv WHERE ticker = ? AND date = ?", (ticker, date)
    ).fetchone()
    return row[0] if row else None


def _has_later_bar(app_conn: sqlite3.Connection, ticker: str, date: str) -> bool:
    return app_conn.execute(
        "SELECT 1 FROM ohlcv WHERE ticker = ? AND date > ? LIMIT 1", (ticker, date)
    ).fetchone() is not None


def classify(app_conn, calendar: list[str], ticker: str, as_of: str):
    """(status, close_asof, close_t5, date_t5).

    status: scored | void_gap | void_no_bar | pending_calendar (its fifth session is
    not in the market calendar yet) | pending_refresh (it is, but this ticker has
    no bar after it yet: none there, or only one that may still be provisional). Five sessions are counted on the market calendar, not
    as five of the ticker's own rows: a halted ticker has no five-session return.
    """
    i = bisect_left(calendar, as_of)
    on_calendar = i < len(calendar) and calendar[i] == as_of
    target = i + HORIZON_SESSIONS - (0 if on_calendar else 1)
    if target >= len(calendar):
        return "pending_calendar", None, None, None
    date_t5 = calendar[target]

    close_asof = _close(app_conn, ticker, as_of)
    if close_asof is None:
        # The writer logged a close from this bar, so it existed once: a rebuilt or not-yet-reloaded
        # app.db must not void an irreplaceable row. Void only if the ticker has later bars but
        # none here; otherwise wait for a refresh.
        has_bars = _has_later_bar(app_conn, ticker, as_of)
        return ("void_no_bar" if has_bars else "pending_refresh"), None, None, date_t5
    if close_asof <= 0:
        return "void_no_bar", None, None, date_t5
    close_t5 = _close(app_conn, ticker, date_t5)
    if close_t5 is None:
        status = "void_gap" if _has_later_bar(app_conn, ticker, date_t5) else "pending_refresh"
        return status, close_asof, None, date_t5
    if close_t5 <= 0:
        return "void_no_bar", close_asof, None, date_t5
    if not _has_later_bar(app_conn, ticker, date_t5):
        # A pull made during the fifth session stores a provisional bar there, and a scored row is
        # never rewritten. A bar after it means the ticker was refreshed once the session was over,
        # and that pull rewrote the fifth bar with its final values. Data only, not the clock.
        return "pending_refresh", close_asof, None, date_t5
    return "scored", close_asof, close_t5, date_t5


def score_pending(app_conn, log_conn, dry_run: bool = False) -> dict:
    """Score every pending row whose fifth session is in `ohlcv`; return the counts."""
    calendar = [r[0] for r in app_conn.execute("SELECT DISTINCT date FROM ohlcv ORDER BY date")]
    pending = log_conn.execute(
        "SELECT id, ticker, as_of, verdict, range_5s_pct FROM debate_log "
        "WHERE outcome_status IS NULL ORDER BY id"
    ).fetchall()
    counts = {"scored": 0, "void_gap": 0, "void_no_bar": 0, "pending": 0}
    refresh: set[str] = set()
    now = datetime.now(timezone.utc).isoformat()

    for row_id, ticker, as_of, verdict, range_5s_pct in pending:
        status, close_asof, close_t5, date_t5 = classify(app_conn, calendar, ticker, as_of)
        if status.startswith("pending"):
            counts["pending"] += 1
            if status == "pending_refresh":
                refresh.add(ticker)
            continue
        counts[status] += 1
        if dry_run:
            continue
        if status == "scored":
            r5 = math.log(close_t5 / close_asof)
            values = (status, now, date_t5, close_asof, close_t5, r5,
                      inside_band(r5, range_5s_pct), direction_hit(verdict, r5), row_id)
        else:
            values = (status, now, None, None, None, None, None, None, row_id)
        log_conn.execute(UPDATE_OUTCOME, values)
    if not dry_run:
        log_conn.commit()
    return {**counts, "refresh": sorted(refresh), "dry_run": dry_run}


def revision_counts(log_conn) -> dict:
    """Scored rows whose logged close differs from the close they were scored on."""
    revised = would_change = 0
    rows = log_conn.execute(
        "SELECT close_at_asof, close_asof_at_scoring, close_t5, range_5s_pct, inside_band "
        "FROM debate_log WHERE outcome_status = 'scored' AND close_at_asof > 0"
    ).fetchall()
    for logged, scored_on, close_t5, range_5s_pct, stored_inside in rows:
        if abs(math.log(logged / scored_on)) <= REVISION_TOLERANCE:
            continue
        revised += 1
        if inside_band(math.log(close_t5 / logged), range_5s_pct) != stored_inside:
            would_change += 1
    return {"revised": revised, "would_change_inside_band": would_change}


# ---------------------------------------------------------------------------
# The analysed population
# ---------------------------------------------------------------------------


def load_log_rows(log_conn) -> list[dict]:
    cursor = log_conn.execute("SELECT * FROM debate_log ORDER BY id")
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def population(rows: list[dict], max_age: int) -> tuple[list[dict], dict]:
    """The rows the headline statistics use, and a funnel that adds up.

    Scored, eligible, healthy, known age <= max_age, then the lowest id per
    (ticker, as_of): re-running until the answer looks right is not rewarded, and
    degraded or ineligible runs are infrastructure outcomes, not opinions.
    """
    funnel = dict.fromkeys(
        ("ineligible", "degraded", "void", "pending", "age_excluded", "repeats_dropped"), 0
    )
    candidates = []
    for r in rows:
        if not r["eligible"]:
            funnel["ineligible"] += 1
        elif r["agents_degraded"] != "[]":
            funnel["degraded"] += 1
        elif r["outcome_status"] is None:
            funnel["pending"] += 1
        elif r["outcome_status"] != "scored":
            funnel["void"] += 1
        elif r["data_age_sessions"] is None or r["data_age_sessions"] > max_age:
            funnel["age_excluded"] += 1
        else:
            candidates.append(r)
    seen, analysed = set(), []
    for r in candidates:  # ascending id
        key = (r["ticker"], r["as_of"])
        if key in seen:
            funnel["repeats_dropped"] += 1
        else:
            seen.add(key)
            analysed.append(r)

    runs: dict[tuple, set] = {}
    for r in rows:
        runs.setdefault((r["ticker"], r["as_of"]), []).append(r["verdict"])
    repeated = [v for v in runs.values() if len(v) > 1]
    funnel.update(
        logged=len(rows), analysed=len(analysed), scored_all=sum(r["outcome_status"] == "scored" for r in rows),
        pairs_repeated=len(repeated), pairs_disagreed=sum(len(set(v)) > 1 for v in repeated),
    )
    return analysed, funnel


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def wilson(k: int, n: int) -> tuple[float, float]:
    """Naive 95% interval: ignores overlap within a ticker and clustering across tickers."""
    p, z2 = k / n, Z_95 ** 2
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = Z_95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return centre - half, centre + half


def block_bootstrap(
    hits: list[int], blocks: list[int], min_blocks: int = MIN_BLOCKS
) -> tuple[float, float] | None:
    """(half-width, implied effective n) from resampling whole blocks of as_of dates.

    None below `min_blocks` (default MIN_BLOCKS) or when the rate has no variance to resample. A floor on
    the uncertainty: block edges and multi-month regimes still leak.
    """
    ids = sorted(set(blocks))
    if len(ids) < min_blocks:
        return None
    k = np.array([sum(h for h, b in zip(hits, blocks) if b == i) for i in ids], dtype=float)
    n = np.array([sum(1 for b in blocks if b == i) for i in ids], dtype=float)
    draws = np.random.default_rng(BOOTSTRAP_SEED).integers(0, len(ids), size=(BOOTSTRAP_RESAMPLES, len(ids)))
    se = float(np.std(k[draws].sum(axis=1) / n[draws].sum(axis=1), ddof=1))
    p = sum(hits) / len(hits)
    if se == 0 or not 0 < p < 1:
        return None
    return Z_95 * se, p * (1 - p) / se ** 2


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def rate_line(label: str, hits: list[int], blocks: list[int], base: float | None = None) -> str:
    """One rate, never without its n, its naive interval and its clustered interval (or why not)."""
    n, k = len(hits), sum(hits)
    low, high = wilson(k, n)
    text = f"{label}: {pct(k / n)} (n={n}); Wilson 95% {pct(low)} to {pct(high)}, ignores overlap and clustering"
    boot = block_bootstrap(hits, blocks)
    if boot:
        text += f"; clustered 95% +-{boot[0] * 100:.1f} points, effective n about {boot[1]:.0f}"
    elif len(set(blocks)) >= MIN_BLOCKS:
        text += "; clustered interval not estimable: no variance across resampled blocks"
    else:
        text += f"; clustered interval not estimable: {len(set(blocks))} blocks (need {MIN_BLOCKS})"
    if base is not None:
        text += f"; base {pct(base)}, edge {(k / n - base) * 100:+.1f} points"
    return text


def coverage_stats(rows: list[dict]) -> dict:
    banded = [r for r in rows if r["range_5s_pct"]]
    with_k = [r for r in banded if r["range_k"]]
    nominal = [r["range_coverage"] for r in rows if r["range_coverage"] is not None]
    return {
        "n": len(banded),
        "inside": sum(r["inside_band"] for r in banded),
        "inside_without_k": sum(
            abs(r["r5"]) * 100 <= r["range_5s_pct"] / r["range_k"] for r in with_k
        ),
        "n_without_k": len(with_k),
        "mean_nominal": sum(nominal) / len(nominal) if nominal else None,
        "median_ratio": float(np.median([abs(r["r5"]) * 100 / r["range_5s_pct"] for r in banded]))
        if banded else None,
    }


def verdict_lean(row: dict) -> str | None:
    return "bull" if row["verdict"] in BULL_VERDICTS else "bear" if row["verdict"] in BEAR_VERDICTS else None


def stance_lean(column: str):
    return lambda row: row[column] if row[column] in ("bull", "bear") else None  # neutral has no direction


def _side_hit(side: str, value: float) -> int:
    return int(value > 0) if side == "bull" else int(value < 0)  # zero is a miss


def directional_stats(rows: list[dict], lean_of, demean: bool = False) -> dict:
    """{side: {hits, blocks, base}}: hits of the rows leaning that way, and the share of ALL
    pooled rows that moved that way. `demean` scores r5 minus the market's, on rows that have one."""
    pool = [r for r in rows if not demean or r["market_r5"] is not None]
    value = lambda r: r["r5"] - (r["market_r5"] if demean else 0.0)  # noqa: E731
    out = {}
    for side in ("bull", "bear"):
        leaning = [r for r in pool if lean_of(r) == side]
        if leaning:
            out[side] = {
                "hits": [_side_hit(side, value(r)) for r in leaning],
                "blocks": [r["block"] for r in leaning],
                "base": sum(_side_hit(side, value(r)) for r in pool) / len(pool),
            }
    return out


def verdict_vs_technical(rows: list[dict]) -> dict | None:
    """Verdict hit-rate minus the technical vote's, on rows where both are directional."""
    both = [r for r in rows if verdict_lean(r) and stance_lean("r1_technical")(r)]
    if not both:
        return None
    verdict = sum(_side_hit(verdict_lean(r), r["r5"]) for r in both) / len(both)
    technical = sum(_side_hit(r["r1_technical"], r["r5"]) for r in both) / len(both)
    return {"n": len(both), "verdict": verdict, "technical": technical, "difference": verdict - technical}


def market_r5(app_conn, as_of: str, date_t5: str) -> float | None:
    """Equal-weight mean log return as_of -> date_t5 over the modelling universe (the same
    filters as `ticker_universe.modelling_universe`, in raw SQL: importing that module imports
    vnstock). None below MIN_MARKET_TICKERS: most tickers are stale, so it is often unavailable."""
    rows = app_conn.execute(
        "SELECT a.close, b.close FROM ohlcv a JOIN ohlcv b ON b.ticker = a.ticker AND b.date = ? "
        "JOIN ticker_universe u ON u.symbol = a.ticker "
        "WHERE a.date = ? AND a.close > 0 AND b.close > 0 AND u.ingestion_state = 'ok' "
        "AND COALESCE(u.fails_liquidity_filter, 0) = 0 AND COALESCE(u.below_minimum_history, 0) = 0",
        (date_t5, as_of),
    ).fetchall()
    if len(rows) < MIN_MARKET_TICKERS:
        return None
    return sum(math.log(close_t5 / close_asof) for close_asof, close_t5 in rows) / len(rows)


# ---------------------------------------------------------------------------
# Cross-checks and the report
# ---------------------------------------------------------------------------


def possible_failed_writes(log_conn, reports_dir: Path) -> list[str]:
    """Report files written after the first logged run that have no row: a write may have failed.
    Older files predate the log and are ignored (never imported: nothing is backfilled)."""
    first = log_conn.execute("SELECT MIN(run_at) FROM debate_log").fetchone()[0]
    if first is None or not reports_dir.is_dir():
        return []
    started = datetime.fromisoformat(first).timestamp()
    logged = set(log_conn.execute("SELECT as_of, ticker FROM debate_log").fetchall())
    return sorted(
        p.name for p in reports_dir.glob("????-??-??_*.md")
        if p.stat().st_mtime > started and tuple(p.stem.split("_", 1)) not in logged
    )


def _directional_section(title: str, table: dict) -> list[str]:
    lines = []
    for side in ("bull", "bear"):
        if side in table:
            t = table[side]
            lines.append(f"  {title}, {side}-lean: " + rate_line("hit", t["hits"], t["blocks"], t["base"]))
    return lines or [f"  {title}: no directional calls in the analysed rows"]


def build_report(app_conn, log_conn, summary: dict, max_age: int, reports_dir: Path | None = None) -> str:
    rows = load_log_rows(log_conn)
    analysed, funnel = population(rows, max_age)
    calendar = [r[0] for r in app_conn.execute("SELECT DISTINCT date FROM ohlcv ORDER BY date")]
    market_cache: dict[tuple, float | None] = {}
    for r in analysed:
        r["block"] = bisect_left(calendar, r["as_of"]) // BLOCK_SESSIONS
        key = (r["as_of"], r["date_t5"])
        if key not in market_cache:
            market_cache[key] = market_r5(app_conn, *key)
        r["market_r5"] = market_cache[key]

    out = ["", "=== Debate outcome report ===",
           f"Funnel: {funnel['logged']} rows logged = {funnel['ineligible']} ineligible + "
           f"{funnel['degraded']} degraded + {funnel['void']} void + {funnel['pending']} pending + "
           f"{funnel['age_excluded']} excluded for age (> {max_age} sessions, or unknown) + "
           f"{funnel['repeats_dropped']} repeat runs + {funnel['analysed']} analysed "
           f"({funnel['scored_all']} scored in all)",
           f"Repeated (ticker, as_of) pairs: {funnel['pairs_repeated']}, of which "
           f"{funnel['pairs_disagreed']} disagreed on the verdict."]
    if not analysed:
        out.append("No analysed rows yet: nothing to report beyond the funnel.")
    else:
        blocks = [r["block"] for r in analysed]
        c = coverage_stats(analysed)
        out += ["", "Range coverage (the displayed band):"]
        if c["n"]:
            out.append("  " + rate_line("inside the stated band", [r["inside_band"] for r in analysed if r["range_5s_pct"]],
                                        [r["block"] for r in analysed if r["range_5s_pct"]])
                       + (f"; mean nominal coverage {pct(c['mean_nominal'])}" if c["mean_nominal"] is not None else ""))
            out.append(f"  with range_k divided out: {c['inside_without_k']} of {c['n_without_k']} inside (n={c['n_without_k']})")
            out.append(f"  median of |move| / band: {c['median_ratio']:.2f} (n={c['n']})")
        else:
            out.append("  no analysed row has a band (n=0)")

        out += ["", "Directional hit-rates (a zero move is a miss; base = share of all analysed rows that moved that way):"]
        out += _directional_section("verdict", directional_stats(analysed, verdict_lean))
        if any(r["market_r5"] is not None for r in analysed):
            out += _directional_section("verdict vs market-demeaned", directional_stats(analysed, verdict_lean, demean=True))
        else:
            out.append(f"  market-demeaned: unavailable (fewer than {MIN_MARKET_TICKERS} market tickers)")
        vt = verdict_vs_technical(analysed)
        if vt:
            out.append(
                f"  verdict minus technical-only, same rows: {(vt['difference']) * 100:+.1f} points "
                f"(verdict {pct(vt['verdict'])}, technical {pct(vt['technical'])}, n={vt['n']})"
            )

        out += ["", "Per agent (neutral stances are not scored):"]
        has_market = any(r["market_r5"] is not None for r in analysed)
        for agent in ("technical", "news", "macro"):
            for n in (1, 2):
                lean = stance_lean(f"r{n}_{agent}")
                out += _directional_section(f"{agent} round {n}", directional_stats(analysed, lean))
                if has_market:
                    out += _directional_section(f"{agent} round {n} market-demeaned",
                                                directional_stats(analysed, lean, demean=True))

        out += ["", "Sample size:",
                f"  {len(analysed)} rows, {len({r['ticker'] for r in analysed})} tickers, "
                f"{len({r['as_of'] for r in analysed})} as_of dates, {len(set(blocks))} block"
                f"{'' if len(set(blocks)) == 1 else 's'} of {BLOCK_SESSIONS} sessions",
                f"  effective n: {'estimated beside each rate above' if len(set(blocks)) >= MIN_BLOCKS else 'not estimable (fewer than ' + str(MIN_BLOCKS) + ' blocks)'};"
                f" the row count is not a sample size: rows on one date share the market move and rows of one ticker overlap",
                f"  needed for +-{HALF_WIDTH_TARGET * 100:.0f} points at p = 0.5: about "
                f"{Z_95 ** 2 * 0.25 / HALF_WIDTH_TARGET ** 2:.0f} effective observations",
                "  These rows come from tickers the owner chose to analyse; nothing corrects for that selection.",
                "  Every interval here is a floor on the uncertainty."]

    rev = revision_counts(log_conn)
    out += ["", f"Close revisions: {rev['revised']} scored rows had a logged close more than "
            f"{REVISION_TOLERANCE * 100:.1f} percent from the close they were scored on; "
            f"{rev['would_change_inside_band']} of them would change inside-band under the logged close."]
    failed = possible_failed_writes(log_conn, reports_dir or REPORTS_DIR)
    out.append("Possible failed log writes (report files with no row): " + (", ".join(failed) or "none"))
    out.append("Tickers to refresh (refresh after the session following their fifth has closed): "
               + (", ".join(summary["refresh"]) or "none"))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def print_scoring_summary(summary: dict) -> None:
    verb = "would score" if summary["dry_run"] else "newly scored"
    print(
        f"Scoring: {summary['scored']} {verb}, {summary['void_gap']} void_gap, "
        f"{summary['void_no_bar']} void_no_bar, {summary['pending']} still pending."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    parser.add_argument("--max-age-sessions", type=int, default=MAX_AGE_SESSIONS_DEFAULT)
    parser.add_argument("--app-db", type=Path, default=APP_DB_PATH)
    parser.add_argument("--log-db", type=Path, default=DEBATE_LOG_DB_PATH)
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args(argv)

    if not args.log_db.exists():  # sqlite would silently create an empty file
        print(f"No debate log at {args.log_db}: nothing to score.")
        return 1
    app_conn, log_conn = open_app_db(args.app_db), open_log_db(args.log_db)
    try:
        summary = score_pending(app_conn, log_conn, dry_run=args.dry_run)
        print_scoring_summary(summary)
        print(build_report(app_conn, log_conn, summary, args.max_age_sessions, args.reports_dir))
    finally:
        app_conn.close()
        log_conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
