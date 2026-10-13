"""The share-count fetch (`add-announcement-tags-and-insider-sizing`, "Shares outstanding come from one vendor field,
cross-checked, cached and fetched only when needed"). A fake frame provider stands in for the vendor: no network.

The fixtures hold the column names measured on 2026-10-12 and synthetic values; no value from a real holding."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from tenacity import RetryError

from app.services import bulk_ingestion
from app.services.share_count import fetch
from app.services.share_count.fetch import (
    ShareCountReading, ShareCountsDisagree, ShareCountUnavailable, read_share_count,
)

BACKEND = Path(__file__).resolve().parent.parent
RATIO_COLUMNS = ("ticker", "year_report", "quarter", "year", "ratio_type", "number_of_shares_mkt_cap")


def ratio_frame(*rows) -> pd.DataFrame:
    """(year_report, quarter, ratio_type, count, year) rows; `year` is a string, as the vendor gives it."""
    return pd.DataFrame(
        [("AAA", yr, q, year if year is not None else str(yr), kind, count) for yr, q, kind, count, year in rows],
        columns=list(RATIO_COLUMNS),
    )


def overview_frame(*values, names=None) -> pd.DataFrame:
    """One row whose columns share a name, like the vendor's four `issue_share` columns."""
    return pd.DataFrame([list(values)], columns=list(names or ["issue_share"] * len(values)))


def frames(ratio, overview):
    def provider(ticker):
        provider.calls.append(ticker)
        return ratio, overview

    provider.calls = []
    return provider


AGREE = 1_000_000_000
SAB_LIKE = ratio_frame((2026, 1, "RATIO_TTM", 990_000_000, None), (2026, 2, "RATIO_TTM", AGREE, None))


def test_the_counts_agree_and_the_period_is_the_latest_ttm_row():
    got = read_share_count("AAA", frames=frames(SAB_LIKE, overview_frame(AGREE, AGREE, AGREE, AGREE)))

    assert got == ShareCountReading(AGREE, 2026, 2)


def test_the_counts_disagree_in_the_vpb_shape():
    ratio = ratio_frame((2026, 2, "RATIO_TTM", 10_000_000_000, None))

    with pytest.raises(ShareCountsDisagree):
        read_share_count("AAA", frames=frames(ratio, overview_frame(10_000_000_000, 7_933_923_601, 10_000_000_000, 7_933_923_601)))


def test_a_disagreement_is_also_an_unavailable_count():
    assert issubclass(ShareCountsDisagree, ShareCountUnavailable)


def test_an_annual_row_last_by_year_and_quarter_does_not_win():
    ratio = ratio_frame(
        (2026, 1, "RATIO_TTM", 900_000_000, None), (2026, 2, "RATIO_TTM", AGREE, None), (2026, 5, "RATIO_YEAR", 123_456_789, None),
    )

    got = read_share_count("AAA", frames=frames(ratio, overview_frame(AGREE, AGREE, AGREE, AGREE)))

    assert (got.count, got.year_report, got.quarter) == (AGREE, 2026, 2)


def test_the_string_year_column_is_never_used_to_choose_the_period():
    ratio = ratio_frame((2026, 2, "RATIO_TTM", AGREE, "1999"), (2026, 1, "RATIO_TTM", 900_000_000, "2030"))  # `year` sorts the other way

    got = read_share_count("AAA", frames=frames(ratio, overview_frame(AGREE, AGREE, AGREE, AGREE)))

    assert (got.year_report, got.quarter, got.count) == (2026, 2, AGREE)


def test_rows_are_chosen_by_integer_period_not_by_row_order():
    ratio = ratio_frame((2026, 2, "RATIO_TTM", AGREE, None), (2025, 4, "RATIO_TTM", 800_000_000, None), (2026, 1, "RATIO_TTM", 900_000_000, None))

    assert read_share_count("AAA", frames=frames(ratio, overview_frame(AGREE, AGREE, AGREE, AGREE))).quarter == 2


def test_the_overview_columns_are_read_by_position_not_by_label():
    overview = overview_frame(AGREE, 5, AGREE, AGREE, AGREE, names=["issue_share", "other", "issue_share", "issue_share", "issue_share"])

    got = read_share_count("AAA", frames=frames(SAB_LIKE, overview))

    assert got.count == AGREE  # the one value under another name is not among the four


def test_the_duplicate_named_columns_all_have_to_be_there():
    with pytest.raises(ShareCountUnavailable):
        read_share_count("AAA", frames=frames(SAB_LIKE, overview_frame(AGREE, AGREE)))


def test_a_missing_overview_field_makes_the_count_unavailable():
    with pytest.raises(ShareCountUnavailable):
        read_share_count("AAA", frames=frames(SAB_LIKE, overview_frame(AGREE, AGREE, AGREE, AGREE, names=["a", "b", "c", "d"])))


@pytest.mark.parametrize("bad", [0, np.nan, 1_000_000_000.5, -5, None])
def test_a_zero_nan_fraction_negative_or_missing_count_is_unavailable(bad):
    ratio = ratio_frame((2026, 2, "RATIO_TTM", bad, None))

    with pytest.raises(ShareCountUnavailable):
        read_share_count("AAA", frames=frames(ratio, overview_frame(AGREE, AGREE, AGREE, AGREE)))


def test_a_bad_overview_value_is_unavailable_not_a_disagreement():
    with pytest.raises(ShareCountUnavailable) as caught:
        read_share_count("AAA", frames=frames(SAB_LIKE, overview_frame(AGREE, np.nan, AGREE, AGREE)))

    assert not isinstance(caught.value, ShareCountsDisagree)


def test_no_ttm_row_is_unavailable():
    with pytest.raises(ShareCountUnavailable):
        read_share_count("AAA", frames=frames(ratio_frame((2026, 5, "RATIO_YEAR", AGREE, None)), overview_frame(AGREE, AGREE, AGREE, AGREE)))


def test_a_ratio_frame_without_a_needed_column_is_unavailable():
    with pytest.raises(ShareCountUnavailable):
        read_share_count("AAA", frames=frames(pd.DataFrame({"x": [1]}), overview_frame(AGREE, AGREE, AGREE, AGREE)))


def test_a_reply_that_is_not_a_frame_is_unavailable():
    with pytest.raises(ShareCountUnavailable):
        read_share_count("AAA", frames=frames(None, None))


def test_the_limiter_exit_becomes_an_ordinary_exception():
    def limiter(ticker):
        raise SystemExit(f"Rate limit exceeded: {bulk_ingestion.RATE_LIMIT_EXIT_MARKER} promotional text")

    with pytest.raises(ShareCountUnavailable) as caught:
        read_share_count("AAA", frames=limiter)

    assert "promotional" not in str(caught.value)


@pytest.mark.parametrize("code", [3, 0, None, "library says goodbye", "Rate limit exceeded"])
def test_any_exit_raised_inside_the_call_is_unavailable_so_nothing_ends_the_brief_before_it_is_written(code):
    def exits(ticker):
        raise SystemExit(code)

    with pytest.raises(ShareCountUnavailable) as caught:
        read_share_count("AAA", frames=exits)

    assert "goodbye" not in str(caught.value)  # nothing the library said is carried


def test_a_keyboard_interrupt_is_not_an_exit_and_passes_through():
    def interrupted(ticker):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        read_share_count("AAA", frames=interrupted)


def test_a_huge_integer_count_is_unavailable_not_an_overflow_error():
    ratio = ratio_frame((2026, 2, "RATIO_TTM", 1, None))
    ratio["number_of_shares_mkt_cap"] = pd.Series([10**400], dtype=object)  # pandas would refuse to build it as a number

    with pytest.raises(ShareCountUnavailable):
        read_share_count("AAA", frames=frames(ratio, overview_frame(AGREE, AGREE, AGREE, AGREE)))


def test_a_huge_integer_in_the_overview_is_unavailable_too():
    overview = overview_frame(AGREE, AGREE, AGREE, AGREE).astype(object)
    overview.iat[0, 1] = 10**400

    with pytest.raises(ShareCountUnavailable):
        read_share_count("AAA", frames=frames(SAB_LIKE, overview))


def test_a_vendor_error_is_unavailable_and_carries_no_vendor_text():
    def broken(ticker):
        raise RuntimeError("secret vendor detail")

    with pytest.raises(ShareCountUnavailable) as caught:
        read_share_count("AAA", frames=broken)

    assert "secret vendor detail" not in str(caught.value) and "RuntimeError" in str(caught.value)


def test_a_retry_error_is_unwrapped():
    class _Attempt:
        def exception(self):
            return ValueError("x")

    def retried(ticker):
        raise RetryError(_Attempt())

    with pytest.raises(ShareCountUnavailable) as caught:
        read_share_count("AAA", frames=retried)

    assert "ValueError" in str(caught.value)


@pytest.mark.parametrize("bad", ["aaa", "AAA/..", "", "TOOLONGTICKER1", "AA A"])
def test_a_ticker_that_is_not_plain_upper_case_is_refused_before_any_call(bad):
    provider = frames(SAB_LIKE, overview_frame(AGREE, AGREE, AGREE, AGREE))

    with pytest.raises(ValueError):
        read_share_count(bad, frames=provider)

    assert provider.calls == []


def test_the_default_provider_asks_the_vci_source_for_both_frames(monkeypatch):
    made = []

    class FakeCompany:
        def __init__(self, source, symbol):
            made.append((source, symbol))

        def ratio_summary(self):
            return SAB_LIKE

        def overview(self):
            return overview_frame(AGREE, AGREE, AGREE, AGREE)

    monkeypatch.setattr(fetch, "Company", FakeCompany)

    assert read_share_count("AAA").count == AGREE and made == [("vci", "AAA")]


# --- the module's place in the repository ---------------------------------------------------------------

def test_the_fetch_module_installs_the_guard_before_importing_the_vendor_library():
    source = (BACKEND / "app" / "services" / "share_count" / "fetch.py").read_text(encoding="utf-8")

    guard = re.search(r"^from app\.vnstock_guard import", source, re.M)
    vendor = re.search(r"^\s*(from vnstock[\w.]*\s+import|import vnstock)", source, re.M)
    assert guard and vendor and guard.start() < vendor.start()
    imported = {getattr(n, "module", None) or a.name for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    assert not any(name.split(".")[0] in ("requests", "httpx", "urllib") for name in imported)


def test_the_share_count_package_never_names_the_feed_package():
    package = BACKEND / "app" / "services" / "share_count"

    assert [p.name for p in package.glob("*.py") if "company" + "_feed" in p.read_text(encoding="utf-8")] == []


def test_no_brief_module_imports_the_vendor_library_or_the_share_count_package():
    for path in (BACKEND / "app" / "services" / "brief").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from vnstock|import vnstock)", source, re.M), path.name
        assert "services.share_count" not in source, path.name


def test_only_the_disagreement_error_carries_the_flag_the_brief_reads():
    assert ShareCountsDisagree.disagree is True and ShareCountUnavailable.disagree is False


@pytest.mark.parametrize(("year", "quarter"), [(1800, 2), (2026, 0), (2026, 5), (2101, 1)])
def test_an_implausible_period_is_unavailable_so_a_value_the_cache_would_drop_is_never_shown(year, quarter):
    ratio = ratio_frame((year, quarter, "RATIO_TTM", AGREE, None))

    with pytest.raises(ShareCountUnavailable):
        read_share_count("AAA", frames=frames(ratio, overview_frame(AGREE, AGREE, AGREE, AGREE)))


def test_a_frame_with_a_duplicated_type_column_is_unavailable_not_a_stray_value_error():
    ratio = pd.DataFrame([("AAA", 2026, 2, "2026", "RATIO_TTM", "RATIO_TTM", AGREE)], columns=[*RATIO_COLUMNS[:5], "ratio_type", RATIO_COLUMNS[5]])

    with pytest.raises(ShareCountUnavailable):
        read_share_count("AAA", frames=frames(ratio, overview_frame(AGREE, AGREE, AGREE, AGREE)))
