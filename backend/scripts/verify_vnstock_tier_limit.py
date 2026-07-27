"""
Verification script for vnstock (kbs/vci) OHLCV tier-limit and count behavior.

NETWORK-DEPENDENT — hits the live vnstock/VCI/KBS API. Run manually, not in CI.
Community-tier limits and count semantics may change without notice; treat this
as a smoke test / regression check against known behavior, not a permanent
guarantee of vendor behavior.

Findings this script reproduces (established via manual testing, 2026-07,
see docs/DATA_DICTIONARY.md for the full writeup):

1. `count` truncates from `end` backward, not from `start` forward.
2. Community tier caps daily OHLCV at floor = max(end - 8y, ticker_real_start).
   Confirmed on both `kbs` and `vci` sources.
3. TCB's real HOSE listing date is 2018-06-04 (Techcombank's own listing
   announcement, press release dated 2018-05-23, confirmed first trading day
   2018-06-04). This is what lets finding #2 be distinguished from a simpler
   "always exactly 8 years back from end" theory, which does NOT fit TCB's
   historical-`end` test results.
4. `start="2000-01-01"` (fixed) and `start=today-8y` (computed) are behaviorally
   equivalent — confirmed identical floor/row count/warning on VIB, kbs.
5. KNOWN UNRESOLVED ISSUE: a multi-hop "walk end backward past the tier limit"
   loop produced an unexplained ValueError on its second iteration, for VNM/kbs.
   NOT reproduced or fixed here — documented as a known failure mode only.
   Do not build production logic on repeated walk-back fetching without
   root-causing this first.

Run: python verify_vnstock_tier_limit.py
Expected: each check prints its result; a line starting with "!!" means a
result no longer matches what was observed in 2026-07 — vendor behavior may
have changed, and the design decisions in docs/DATA_DICTIONARY.md and the
data-ingestion-vnstock proposal should be re-checked before trusting them.
"""

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from vnstock.ui import Market

mkt = Market()

# Pinned to the date these findings were established. Re-run with today's real
# date (remove the pin) to check whether the tier boundary has moved/changed.
TODAY = date(2026, 7, 25)


def check(label, ticker, start, end, count, source, expect_floor=None, expect_rows=None):
    df = mkt.equity(ticker).ohlcv(start=start, end=end, count=count, source=source)
    floor = str(df["time"].min())[:10]
    rows = len(df)
    print(f"[{label}] floor={floor} rows={rows}")
    if expect_floor is not None and floor != expect_floor:
        print(f"  !! expected floor {expect_floor}, got {floor}")
    if expect_rows is not None and rows != expect_rows:
        print(f"  !! expected {expect_rows} rows, got {rows}")
    return df


if __name__ == "__main__":
    print("--- Finding #2: tier limit binds at end=today ---")
    check("VIB tier-bound, kbs", "VIB", "2000-01-01", TODAY.isoformat(), 5000, "vci",
          expect_floor="2018-07-26", expect_rows=1990)
    check("TCB tier-bound, vci", "TCB", "2000-01-01", TODAY.isoformat(), 8000, "vci",
          expect_floor="2018-07-26", expect_rows=1997)

    print("\n--- Finding #2/#3: real listing date binds when end is historical ---")
    # 2026-07-27 rerun observed 39 rows here (vs. 40 originally, 2026-07). Floor
    # unchanged. Treated as expected vendor-side data jitter, consistent with
    # the VN30 1990-1997 spread finding elsewhere in this project — NOT a bug,
    # NOT updated as the new expected value, so future drift stays visible.
    check("TCB listing-bound #1, vci", "TCB", "2000-01-01", "2018-07-26", 1997, "vci",
          expect_floor="2018-06-04", expect_rows=40)
    check("TCB listing-bound #2, vci", "TCB", "2000-01-01", "2022-01-01", 8000, "vci",
          expect_floor="2018-06-04", expect_rows=901)

    print("\n--- Finding #4: start=fixed vs start=computed(today-8y) equivalence ---")
    # NOTE: must use relativedelta(years=8), not timedelta(days=365*8) — the
    # latter ignores leap years and drifts 1-2 days off the true 8-year mark,
    # which can itself become the binding constraint and produce a false
    # mismatch here. (This was a real bug, caught 2026-07-27 — see git history.)
    computed_start = (TODAY - relativedelta(years=8)).isoformat()
    df_a = check("VIB start=fixed('2000-01-01'), vci", "VIB", "2000-01-01",
                 TODAY.isoformat(), 5000, "vci")
    df_b = check("VIB start=computed(today-8y), vci", "VIB", computed_start,
                 TODAY.isoformat(), 5000, "vci")
    if str(df_a["time"].min()) != str(df_b["time"].min()) or len(df_a) != len(df_b):
        print("  !! start=fixed and start=computed no longer equivalent — re-check design")

    print("\n--- Finding #5: KNOWN UNRESOLVED — walk-back loop crash (VNM, vci) ---")
    print("Uncommented below only on purpose — this reproduces a real crash.")
    print("Left in so the failure is visible/re-testable, not silently dropped.")
    end = TODAY
    prev_floor = None
    try:
        for i in range(3):
            df = mkt.equity("VNM").ohlcv(start="2000-01-01", end=end.isoformat(),
                                          count=8000, source="vci")
            if df.empty:
                print(f"  iter {i}: empty result, stopping")
                break
            floor = df["time"].min()
            print(f"  iter {i}: end={end} floor={floor} rows={len(df)}")
            if floor == prev_floor:
                print("  floor stopped moving, stopping")
                break
            prev_floor = floor
            end = floor.date() - timedelta(days=1)
    except Exception as e:
        print(f"  !! reproduced known crash: {type(e).__name__}: {e}")
        print("  This is the unresolved ValueError from finding #5 — expected, not a regression,")
        print("  unless the error type/message differs from prior observations.")
