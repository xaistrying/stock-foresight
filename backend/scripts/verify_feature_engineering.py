"""
Verification script for M2 (feature engineering).

Cross-checks the `features` table against an INDEPENDENT recomputation from
raw `ohlcv`, rather than trusting hand-written fixtures (which risk being
wrong in the same way an implementation is wrong, if both came from the same
misunderstanding of a formula). Also runs structural checks that don't need
a reference implementation at all.

REQUIRES ADJUSTMENT: the COLS dict below assumes column names. Update it to
match your actual `features` schema before running — this script has no way
to know what task 1.1 actually named things.

CONVENTION CAVEATS — read before treating a mismatch as a bug:
- RSI and ATR here use Wilder's smoothing (ewm with alpha=1/period). This is
  the traditional convention, but a simple rolling-mean version is also
  common. If RSI/ATR mismatch consistently while everything else matches
  cleanly, check docs/DATA_DICTIONARY.md for which smoothing convention was
  actually implemented before assuming a bug.
- Bollinger Bands here use pandas' default sample std (ddof=1). Some TA
  libraries use population std (ddof=0) instead — another possible
  convention difference, not necessarily a bug.
- Ichimoku Senkou A/B here use the "as-charted" forward-shift convention
  (Decision 6): the value stored at row D is computed from data as of D-26.
  chikou_signal(D) = close(D) - close(D-26), the leakage-safe replacement
  for the literal Chikou Span (see design.md Decision 6) — NOT the same
  formula as a standard TA library's Chikou.

Run: python scripts/verify_feature_engineering.py
"""

import sqlite3
import pandas as pd
import numpy as np

DB_PATH = "backend/data/app.db"
TICKER = "TCB"          # known ground truth: real HOSE listing date 2018-06-04
TOLERANCE = 1e-6

# --- Matches actual `features` schema ---
COLS = {
    "date": "date",
    "tenkan": "tenkan_sen",
    "kijun": "kijun_sen",
    "senkou_a": "senkou_span_a",
    "senkou_b": "senkou_span_b",
    "chikou_signal": "chikou_signal",
    "rsi": "rsi",
    "macd_line": "macd_line",
    "macd_signal": "macd_signal",
    "macd_hist": "macd_histogram",
    "bb_upper": "bb_upper",
    "bb_mid": "bb_middle",
    "bb_lower": "bb_lower",
    "atr": "atr",
    "obv": "obv",
    "target": "target",
    "near_gap": "near_gap",
}


# ---------- Independent reference implementations ----------

def ref_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def ref_macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, macd_signal, macd_line - macd_signal


def ref_bollinger(close, period=20, num_std=2):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()  # sample std, ddof=1 (pandas default)
    return mid + num_std * std, mid, mid - num_std * std


def ref_atr(high, low, close, period=14):
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()  # Wilder smoothing


def ref_obv(close, volume):
    direction = np.sign(close.diff().fillna(0))
    return (direction * volume).cumsum()


def ref_ichimoku(high, low, close, tenkan_p=9, kijun_p=26, senkou_b_p=52, shift=26):
    tenkan = (high.rolling(tenkan_p).max() + low.rolling(tenkan_p).min()) / 2
    kijun = (high.rolling(kijun_p).max() + low.rolling(kijun_p).min()) / 2
    senkou_a_raw = (tenkan + kijun) / 2
    senkou_b_raw = (high.rolling(senkou_b_p).max() + low.rolling(senkou_b_p).min()) / 2
    # "as charted" at row D: value computed from data as of D-26 (Decision 6)
    senkou_a = senkou_a_raw.shift(shift)
    senkou_b = senkou_b_raw.shift(shift)
    chikou_signal = close - close.shift(shift)  # leakage-safe, per Decision 6
    return tenkan, kijun, senkou_a, senkou_b, chikou_signal


def ref_target(close, horizon=5):
    return np.log(close.shift(-horizon) / close)


# ---------- Comparison helper ----------

def compare(label, actual: pd.Series, expected: pd.Series, tol=TOLERANCE):
    both_present = actual.notna() & expected.notna()
    n = both_present.sum()
    if n == 0:
        print(f"  ??   {label}: 0 comparable rows — INCONCLUSIVE, not a pass. "
              f"No overlapping non-null data to check.")
        return
    diff = actual[both_present] - expected[both_present]
    abs_diff = diff.abs()
    mismatches = abs_diff[abs_diff > tol]
    if len(mismatches) == 0:
        print(f"  OK   {label}: {n} comparable rows, all within tolerance")
    else:
        print(f"  !!   {label}: {len(mismatches)}/{n} rows mismatch (tol={tol})")
        idx = mismatches.index
        print(f"       first mismatch at index {idx[0]}: "
              f"actual={actual[idx[0]]}, expected={expected[idx[0]]}")
        print(f"       mismatch row-index range: {idx.min()} to {idx.max()} out of {n} — "
              + ("clustered near series start (likely a warm-up/seeding convention "
                 "difference, not a bug — see convention caveats at top of file)"
                 if idx.max() < n * 0.15 else
                 "SPREAD BEYOND the first ~15% of the series — less likely to be pure "
                 "warm-up decay, worth checking as a real difference"))
        offset_std = diff[both_present].std()
        offset_mean = diff[both_present].mean()
        print(f"       (actual - expected): mean={offset_mean:.4f}, std={offset_std:.6f} — "
              + ("looks like a roughly CONSTANT offset (likely an initialization/seed "
                 "value convention difference, not an accumulation bug)"
                 if offset_std < max(abs(offset_mean) * 0.05, tol * 100) else
                 "VARIES across rows (likely a real logic difference, not just a "
                 "constant convention offset)"))


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)

    # ---------- Structural checks (no reference implementation needed) ----------
    print(f"--- Structural checks: {TICKER} ---")

    ohlcv_n = conn.execute(
        "SELECT COUNT(*) FROM ohlcv WHERE ticker=?", (TICKER,)
    ).fetchone()[0]
    features_n = conn.execute(
        "SELECT COUNT(*) FROM features WHERE ticker=?", (TICKER,)
    ).fetchone()[0]
    print(f"  ohlcv rows: {ohlcv_n} | features rows: {features_n}"
          + ("  OK (parity)" if ohlcv_n == features_n and ohlcv_n > 0
             else "  !! MISMATCH or empty — Decision 2 requires no dropped rows"))

    if ohlcv_n == 0:
        print(f"  No ohlcv data for {TICKER} — load it first, then rerun.")
        conn.close()
        raise SystemExit(0)

    if features_n == 0:
        print(f"  No features data for {TICKER} — feature computation has not run "
              f"for this ticker. Stopping here: every downstream check would compare "
              f"0 rows and look like a false pass, not a real one.")
        conn.close()
        raise SystemExit(0)

    tail = pd.read_sql(
        f"SELECT {COLS['date']} as date, {COLS['target']} as target "
        f"FROM features WHERE ticker=? ORDER BY date DESC LIMIT 6",
        conn, params=(TICKER,),
    )
    last5_null = tail.iloc[:5]["target"].isna().all()
    sixth_has_value = tail.iloc[5:6]["target"].notna().all() if len(tail) == 6 else None
    print(f"  Last 5 rows target NULL: {last5_null}"
          + ("  OK" if last5_null else "  !! expected all NULL (task 3.2)"))
    if sixth_has_value is not None:
        print(f"  6th-from-last has value: {sixth_has_value}"
              + ("  OK" if sixth_has_value else "  !! expected a real value"))

    head = pd.read_sql(
        f"SELECT {COLS['date']} as date, {COLS['near_gap']} as near_gap "
        f"FROM features WHERE ticker=? ORDER BY date ASC LIMIT 55",
        conn, params=(TICKER,),
    )
    if not head.empty:
        first_flagged = head["near_gap"].iloc[:52].astype(bool).all()
        later_clear = head["near_gap"].iloc[52:].astype(bool).any() == False if len(head) > 52 else None
        print(f"  First ~52 rows all near_gap=1 (series-start case): {first_flagged}"
              + ("  OK" if first_flagged else "  !! check task 4.2's 'precedes first stored session' case"))

    # ---------- Independent recomputation vs. stored features ----------
    print(f"\n--- Recomputation cross-check: {TICKER} ---")

    ohlcv = pd.read_sql(
        "SELECT date, open, high, low, close, volume FROM ohlcv "
        "WHERE ticker=? ORDER BY date ASC",
        conn, params=(TICKER,),
    )
    features = pd.read_sql(
        f"SELECT * FROM features WHERE ticker=? ORDER BY {COLS['date']} ASC",
        conn, params=(TICKER,),
    )
    merged = ohlcv.merge(
        features, left_on="date", right_on=COLS["date"], suffixes=("", "_feat")
    )

    close, high, low, volume = merged["close"], merged["high"], merged["low"], merged["volume"]

    compare("RSI(14)", merged[COLS["rsi"]], ref_rsi(close))

    macd_line, macd_signal, macd_hist = ref_macd(close)
    compare("MACD line", merged[COLS["macd_line"]], macd_line)
    compare("MACD signal", merged[COLS["macd_signal"]], macd_signal)
    compare("MACD hist", merged[COLS["macd_hist"]], macd_hist)

    bb_u, bb_m, bb_l = ref_bollinger(close)
    compare("Bollinger upper", merged[COLS["bb_upper"]], bb_u)
    compare("Bollinger mid", merged[COLS["bb_mid"]], bb_m)
    compare("Bollinger lower", merged[COLS["bb_lower"]], bb_l)

    compare("ATR(14)", merged[COLS["atr"]], ref_atr(high, low, close))
    compare("OBV", merged[COLS["obv"]], ref_obv(close, volume))

    tenkan, kijun, senkou_a, senkou_b, chikou = ref_ichimoku(high, low, close)
    compare("Tenkan", merged[COLS["tenkan"]], tenkan)
    compare("Kijun", merged[COLS["kijun"]], kijun)
    compare("Senkou A (shifted, Decision 6)", merged[COLS["senkou_a"]], senkou_a)
    compare("Senkou B (shifted, Decision 6)", merged[COLS["senkou_b"]], senkou_b)
    compare("chikou_signal (Decision 6, leakage-safe)", merged[COLS["chikou_signal"]], chikou)

    compare("target (Rule 1, 5-session log return)", merged[COLS["target"]], ref_target(close))

    conn.close()
