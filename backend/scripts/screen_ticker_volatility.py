"""
Realized-volatility screening tool for candidate M3 training tickers.

Computes trailing realized volatility (rolling std of daily log returns,
default 250-session / ~1-year window) directly from your own `ohlcv` data,
so ticker selection is based on what your data actually shows right now,
not on either of our possibly-stale assumptions about which VN stocks are
"volatile" or "stable."

For any candidate not already in `ohlcv`, this calls the existing M1
`load_ticker()` to fetch it — meaning this WILL hit the live vnstock API
for missing tickers (network-dependent; respects the RateLimitError
handling already in ticker_ingestion.py). Already-loaded tickers are read
straight from SQLite, no network call.

Also flags a specific risk raised in this project's own design discussion:
a ticker with a high fraction of sessions where close == previous close
exactly often reflects illiquidity (no trades that day, price just carried
over), not genuine price stability. A "stable" ticker combined with a high
stale-price fraction is the case worth distrusting most — it may look like
a calm, easy-to-predict series while actually just being thinly traded.

NOTE ON LOCATION: this script lives in backend/scripts/, matching how
verify_feature_engineering.py has actually been run in this project — not
the top-level scripts/ path CLAUDE.md/openspec-project-context.yaml
currently document. Worth reconciling that doc/practice drift at some
point; not fixed here.

Run from the project root: python backend/scripts/screen_ticker_volatility.py
"""

import sys
import sqlite3
import pandas as pd
import numpy as np

sys.path.insert(0, "backend")  # so `from app...` resolves; run from project root
from app.services.ticker_ingestion import load_ticker  # noqa: E402

DB_PATH = "backend/data/app.db"

# Edit this list. VNM/HPG are safe, well-known, high-confidence non-bank
# VN30 large-caps, included so the baseline isn't all-financial (TCB/VIB).
# Deliberately NOT pre-filled with speculative mid/small-cap names — their
# current listing/liquidity status isn't something to trust from memory.
# Add your own candidates below; this script tells you empirically whether
# they're actually more volatile than the baseline.
CANDIDATES = [
    "TCB",  # already loaded — bank, baseline
    "VIB",  # already loaded — bank, baseline
    "VNM",  # consumer staples, large-cap, non-bank
    "HPG",  # industrials/steel, large-cap, non-bank
    "SAB",  # beverage; low free float (ThaiBev majority stake) — good test
            # of the stale-price flag specifically
    "MWG",  # retail / consumer discretionary
    "VND",  # securities/brokerage — expected to be more volatile than the
            # above (revenue tied to market trading activity), unconfirmed
    "MSN",  # consumer conglomerate
    "VHM",  # real estate (Vinhomes) — picked ONE Vingroup-family ticker
            # only; VIC/VHM/VRE/VPL are treated as one correlated group
            # under HOSE's own VN30 group-weight-cap rule, so adding more
            # than one wouldn't add real diversity
]

VOL_WINDOW = 250  # trading sessions, ~1 year
STALE_PRICE_WARN_THRESHOLD = 0.15  # flag if >15% of sessions have close == prev close


def ensure_loaded(conn, ticker):
    n = conn.execute("SELECT COUNT(*) FROM ohlcv WHERE ticker=?", (ticker,)).fetchone()[0]
    if n > 0:
        print(f"  {ticker}: already loaded ({n} rows)")
        return
    print(f"  {ticker}: not in ohlcv yet, loading via live API...")
    try:
        result = load_ticker(ticker)
        print(f"  {ticker}: loaded {result.get('rows_loaded', 0)} rows")
    except Exception as e:
        print(f"  {ticker}: !! load failed ({type(e).__name__}: {e}) — skipping")


def screen(conn, ticker):
    df = pd.read_sql(
        "SELECT date, close FROM ohlcv WHERE ticker=? ORDER BY date ASC",
        conn, params=(ticker,),
    )
    if len(df) < 30:
        return {"ticker": ticker, "error": "too few rows to screen"}

    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    recent = df.tail(VOL_WINDOW)

    daily_vol = recent["log_return"].std()
    annualized_vol_pct = daily_vol * np.sqrt(252) * 100
    stale_frac = (recent["close"] == recent["close"].shift(1)).mean()

    return {
        "ticker": ticker,
        "rows": len(df),
        "window_used": len(recent),
        "annualized_vol_pct": round(annualized_vol_pct, 2),
        "stale_price_frac": round(stale_frac, 3),
        "stale_warning": stale_frac > STALE_PRICE_WARN_THRESHOLD,
    }


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)

    print("--- Ensuring candidates are loaded ---")
    for t in CANDIDATES:
        ensure_loaded(conn, t)

    print(f"\n--- Realized volatility, last {VOL_WINDOW} sessions ---")
    results = [screen(conn, t) for t in CANDIDATES]
    errors = [r for r in results if "error" in r]
    results = [r for r in results if "error" not in r]
    results.sort(key=lambda r: r["annualized_vol_pct"], reverse=True)

    print(f"{'Ticker':<8}{'Rows':<8}{'Ann. Vol %':<14}{'Stale-price frac':<18}{'Flag'}")
    for r in results:
        flag = ""
        if r["stale_warning"] and r["annualized_vol_pct"] == min(x["annualized_vol_pct"] for x in results):
            flag = "  !! low vol + high stale-price frac — check for illiquidity, not real stability"
        elif r["stale_warning"]:
            flag = "  !! high stale-price fraction — check for illiquidity"
        print(f"{r['ticker']:<8}{r['rows']:<8}{r['annualized_vol_pct']:<14}{r['stale_price_frac']:<18}{flag}")

    for e in errors:
        print(f"  {e['ticker']}: {e['error']}")

    conn.close()
