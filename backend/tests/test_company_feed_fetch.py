"""The vendor fetch (`company-feed`: VCI news and events through the Unified UI, one guarded importer).

The wrapper is stubbed at the `fetch` module boundary (`fetch.Reference`): no vendor call is made.
"""

from __future__ import annotations

from concurrent.futures import Future
from importlib import metadata

import pandas as pd
import pytest
from tenacity import RetryError
from vnstock.core.exceptions import RateLimitError

from app.services.company_feed import fetch
from app.services.company_feed.normalise import UnexpectedFrame

from .company_feed_helpers import events_frame, news_frame

RATE_LIMIT_MESSAGE = "Rate limit exceeded. Upgrade for more requests. Process terminated."


class _Company:
    def __init__(self, calls, frames, raises):
        self._calls, self._frames, self._raises = calls, frames, raises

    def _answer(self, kind, source):
        self._calls.append((kind, source))
        if self._raises is not None:
            raise self._raises
        return self._frames[kind]

    def news(self, source=None):
        return self._answer("news", source)

    def events(self, source=None):
        return self._answer("events", source)


class _FakeReference:
    """Stands in for `vnstock.ui.Reference`: records `company(symbol)` and every `source` passed."""

    def __init__(self, calls, frames=None, raises=None):
        self.calls, self._frames, self._raises = calls, frames or {"news": news_frame(), "events": events_frame()}, raises

    def company(self, symbol):
        self.calls.append(("company", symbol))
        return _Company(self.calls, self._frames, self._raises)


@pytest.fixture
def calls(monkeypatch):
    recorded: list[tuple] = []
    monkeypatch.setattr(fetch, "Reference", lambda: _FakeReference(recorded))
    return recorded


def _stub(monkeypatch, *, frames=None, raises=None):
    recorded: list[tuple] = []
    monkeypatch.setattr(fetch, "Reference", lambda: _FakeReference(recorded, frames, raises))
    return recorded


def _retry_error(exception: BaseException) -> RetryError:
    future: Future = Future()
    future.set_exception(exception)
    return RetryError(future)


def test_both_kinds_pass_source_vci_explicitly(calls):
    """Scenario: Source is set explicitly; Scenario: Both kinds are fetched."""
    fetch.fetch_company_frame("SAB", "news")
    fetch.fetch_company_frame("SAB", "events")

    assert calls == [("company", "SAB"), ("news", "vci"), ("company", "SAB"), ("events", "vci")]
    assert fetch.VENDOR_SOURCE == "vci"


def test_the_frame_is_returned_as_the_vendor_gave_it(monkeypatch):
    frame = news_frame()
    _stub(monkeypatch, frames={"news": frame})

    assert fetch.fetch_company_frame("SAB", "news") is frame


def test_an_empty_frame_is_not_an_error_even_without_columns(monkeypatch):
    _stub(monkeypatch, frames={"events": pd.DataFrame()})

    assert fetch.fetch_company_frame("SAB", "events").empty


def test_a_frame_without_a_required_column_is_an_unexpected_frame(monkeypatch):
    """Scenario: A changed frame is an error."""
    _stub(monkeypatch, frames={"news": news_frame().drop(columns=["news_title"])})

    with pytest.raises(UnexpectedFrame, match="news_title"):
        fetch.fetch_company_frame("SAB", "news")


def test_something_that_is_not_a_frame_is_an_unexpected_frame(monkeypatch):
    _stub(monkeypatch, frames={"news": None})

    with pytest.raises(UnexpectedFrame):
        fetch.fetch_company_frame("SAB", "news")


def test_a_retry_error_is_unwrapped_to_its_last_exception(monkeypatch):
    """Scenario: Wrapped errors are classified."""
    _stub(monkeypatch, raises=_retry_error(ValueError("bad symbol")))

    with pytest.raises(ValueError, match="bad symbol") as caught:
        fetch.fetch_company_frame("SAB", "news")

    assert type(caught.value) is ValueError


def test_a_retry_error_wrapping_a_rate_limit_is_a_rate_limit(monkeypatch):
    _stub(monkeypatch, raises=_retry_error(RateLimitError("vci")))

    with pytest.raises(fetch.RateLimited):
        fetch.fetch_company_frame("SAB", "news")


def test_vnstocks_rate_limit_error_is_reported_as_a_rate_limit(monkeypatch):
    _stub(monkeypatch, raises=RateLimitError("vci", retry_after=30))

    with pytest.raises(fetch.RateLimited) as caught:
        fetch.fetch_company_frame("SAB", "events")

    assert type(caught.value.__cause__) is RateLimitError


def test_vnais_rate_limit_exit_is_reported_as_a_rate_limit_not_an_exit(monkeypatch):
    """Scenario: A rate-limit exit is waited out (the classification half)."""
    _stub(monkeypatch, raises=SystemExit(RATE_LIMIT_MESSAGE))

    with pytest.raises(fetch.RateLimited) as caught:
        fetch.fetch_company_frame("SAB", "news")

    assert isinstance(caught.value, Exception)
    assert RATE_LIMIT_MESSAGE not in str(caught.value)  # the promotional text is not carried along
    assert caught.value.__cause__ is None and caught.value.__suppress_context__  # nor chained into a logged traceback


def test_any_other_exit_is_reraised(monkeypatch):
    """Scenario: A genuine exit is honoured."""
    _stub(monkeypatch, raises=SystemExit("shutting down"))

    with pytest.raises(SystemExit, match="shutting down"):
        fetch.fetch_company_frame("SAB", "news")


def test_an_exit_without_a_message_is_reraised(monkeypatch):
    _stub(monkeypatch, raises=SystemExit())

    with pytest.raises(SystemExit):
        fetch.fetch_company_frame("SAB", "news")


def test_other_errors_propagate_unchanged(monkeypatch):
    _stub(monkeypatch, raises=ConnectionError("down"))

    with pytest.raises(ConnectionError):
        fetch.fetch_company_frame("SAB", "news")


@pytest.mark.parametrize("symbol", ["", "sab", "SAB&x=1", "SAB/../x", "SAB ", "A" * 13, "SАB"])
def test_a_symbol_that_is_not_a_plain_ticker_is_refused_before_any_call(calls, symbol):
    with pytest.raises(ValueError, match="ticker"):
        fetch.fetch_company_frame(symbol, "news")

    assert calls == []


def test_an_unknown_kind_is_refused_before_any_call(calls):
    with pytest.raises(ValueError, match="kind"):
        fetch.fetch_company_frame("SAB", "filings")

    assert calls == []


def test_the_installed_vnstock_version_is_reported_for_the_fetch_row():
    assert fetch.installed_vnstock_version() == metadata.version("vnstock")


def test_the_version_is_none_when_the_distribution_is_not_found(monkeypatch):
    def missing(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(fetch.metadata, "version", missing)

    assert fetch.installed_vnstock_version() is None
