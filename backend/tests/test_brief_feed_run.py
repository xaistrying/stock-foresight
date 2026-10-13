"""A whole run with and without a feed log: nothing is fetched, started or written
(`weekly-holdings-brief`: "The brief reads the company feed through one adapter and never starts a snapshot")."""

from __future__ import annotations

import os
import socket
import subprocess

import pytest

from app.db import company_feed_log

from .brief_event_rows import div_row, load_feed
from .test_brief_run import _log, _run, world  # noqa: F401
from .test_brief_support import brief_env, brief_isolation  # noqa: F401


@pytest.fixture
def no_processes_or_network(monkeypatch):
    calls: list[str] = []

    def refuse(name):
        def blocked(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"{name} was called")

        return blocked

    monkeypatch.setattr(subprocess, "Popen", refuse("subprocess.Popen"))
    monkeypatch.setattr(subprocess, "run", refuse("subprocess.run"))
    monkeypatch.setattr(os, "system", refuse("os.system"))
    monkeypatch.setattr(socket, "socket", refuse("socket.socket"))
    monkeypatch.setattr(socket, "create_connection", refuse("socket.create_connection"))
    return calls


def test_a_missing_feed_log_reads_as_never_fetched_prints_the_command_and_starts_nothing(world, no_processes_or_network):
    assert not company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists()

    result = _run(world)

    text = "\n".join(result.brief)
    assert result.exit_code == 0 and no_processes_or_network == []
    for ticker in ("AAA", "BBB", "CCC"):
        assert f"No dividend or share issue can be listed or checked for {ticker}: its events have never been fetched" in text
        assert f"python backend/scripts/snapshot_company_feed.py --tickers {ticker}" in text
    assert "none found" not in text.replace("not the same as none found", "")
    assert not company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists()  # the run created no log


def test_a_run_with_a_feed_reads_it_without_writing_it(world, no_processes_or_network):
    load_feed({"AAA": [div_row("AAA", 0, published="2025-12-20", ex="2026-01-12", vnd=500.0)]})
    path = company_feed_log.COMPANY_FEED_LOG_DB_PATH
    before = path.stat().st_mtime_ns, path.read_bytes()

    result = _run(world)

    text = "\n".join(result.brief)
    assert result.exit_code == 0 and no_processes_or_network == []
    assert "ex-dates since your purchase date (company-announcement source, which covers from 2025-12-20)" in text
    assert "500 VND (ex 2026-01-12)" in text
    assert (path.stat().st_mtime_ns, path.read_bytes()) == before
    assert "its events have never been fetched" in text  # BBB and CCC were never passed to the snapshot


def test_the_recomputed_week_1_range_is_never_written_to_the_issued_log(world):
    load_feed({"AAA": [div_row("AAA", 0, published="2025-12-20", ex="2026-01-12", vnd=500.0)]})

    result = _run(world)

    assert "Recomputed today from prices up to" in "\n".join(result.brief)
    log_text = (world.config / "holdings_issued.jsonl").read_text()
    assert "ecomputed" not in log_text and len(_log(world).entries) == 3
    assert all("band_pct" in line for line in log_text.splitlines())


def test_a_redacted_run_keeps_the_market_dividend_lines_and_drops_the_log_and_purchase_lines(world):
    load_feed({"AAA": [div_row("AAA", 0, published="2025-12-20", ex="2026-01-12", vnd=500.0)]})

    result = _run(world, redact=True)

    text = "\n".join(result.brief)
    assert "DIVIDENDS (company-announcement source; events last fetched" in text and "Scheduled (company-announcement source" in text
    for fragment in ("since your purchase date", "Recomputed", "first brief", "2025-06-1", "4321"):
        assert fragment not in text, fragment
