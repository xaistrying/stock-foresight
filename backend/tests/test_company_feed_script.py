"""The manual script and the inputs it starts from (`company-feed`: "The snapshot runs only by hand";
"No API key is used, stored or required"; "Nothing to fetch").

The script is loaded by path (`backend/scripts/` is not a package), and `run_snapshot` is stubbed
wherever a test is about the command line, so no request is made.
"""

from __future__ import annotations

import builtins
import importlib.util
import logging
import sqlite3
from pathlib import Path

import pytest

from app.db import company_feed_log, debate_log
from app.services.company_feed import fetch, inputs, snapshot, store
from app.services.company_feed.store import FetchRow
from app.services.company_feed.summary import EXIT_FAILED, EXIT_OK, EXIT_USAGE, RunSummary

BACKEND = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("snapshot_company_feed", BACKEND / "scripts" / "snapshot_company_feed.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

SECRET = "vnstock-key-placeholder-0123456789"


class _Runs(list):
    """Records `(tickers, options)` of every `run_snapshot` call; `summary` is what the stub returns."""

    summary = RunSummary(reports=())


@pytest.fixture
def runs(monkeypatch):
    recorded = _Runs()

    def fake(tickers, options=None, tools=None):
        recorded.append((tickers, options))
        return recorded.summary

    monkeypatch.setattr(snapshot, "run_snapshot", fake)
    return recorded


@pytest.fixture(autouse=True)
def _no_key_anywhere(monkeypatch, tmp_path):
    monkeypatch.delenv(inputs.API_KEY_ENV_VAR, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))


def _write_debate_log(tickers: list[str]) -> None:
    conn = sqlite3.connect(debate_log.DEBATE_LOG_DB_PATH)
    try:
        debate_log.init_debate_log_db(conn)
        for ticker in tickers:
            conn.execute(
                "INSERT INTO debate_log (ticker, as_of, run_at, eligible, verdict) VALUES (?, '2026-10-08', 'x', 1, 'NEUTRAL')",
                (ticker,),
            )
        conn.commit()
    finally:
        conn.close()


# --- the command line --------------------------------------------------------------------------


def test_neither_ticker_option_is_a_usage_error_with_no_request_and_no_file(runs, capsys):
    """Scenario: Nothing to fetch."""
    assert script.main([]) == EXIT_USAGE == 2
    assert script.main(["--no-rss", "--dry-run"]) == 2

    assert runs == []
    assert not company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists()
    assert "--tickers" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["--tickers", "SAB&x=1"], ["--tickers", "SA B"], ["--tickers", "SAB,../etc"],
    ["--tickers", "SAB", "--tickers-per-minute", "0"], ["--tickers", "SAB", "--tickers-per-minute", "-3"],
    ["--tickers", "SAB", "--tickers-per-minute", "fast"], ["--tickers", "SAB", "--unknown"],
])
def test_bad_arguments_are_a_usage_error(runs, argv):
    assert script.main(argv) == EXIT_USAGE
    assert runs == []


def test_explicit_tickers_are_upper_cased_and_deduplicated_and_the_options_follow_the_flags(runs):
    code = script.main(["--tickers", "sab, vpb,SAB", "--tickers-per-minute", "4", "--no-rss", "--dry-run"])

    tickers, options = runs[0]
    assert code == EXIT_OK and tickers == ("SAB", "VPB")
    assert (options.tickers_per_minute, options.include_rss, options.dry_run) == (4.0, False, True)


def test_the_defaults_are_eight_a_minute_with_rss_and_a_real_write(runs):
    script.main(["--tickers", "SAB"])

    options = runs[0][1]
    assert (options.tickers_per_minute, options.include_rss, options.dry_run) == (8, True, False)


def test_from_debate_log_adds_the_logged_tickers_read_only(runs):
    _write_debate_log(["VPB", "SAB", "VPB"])
    before = debate_log.DEBATE_LOG_DB_PATH.read_bytes()

    script.main(["--tickers", "HPG", "--from-debate-log"])

    assert runs[0][0] == ("HPG", "SAB", "VPB")
    assert debate_log.DEBATE_LOG_DB_PATH.read_bytes() == before


def test_from_debate_log_with_no_log_file_is_an_empty_list_not_an_error(runs, capsys):
    assert not debate_log.DEBATE_LOG_DB_PATH.exists()

    code = script.main(["--from-debate-log"])

    assert code == EXIT_OK and runs[0][0] == ()
    assert not debate_log.DEBATE_LOG_DB_PATH.exists()
    assert "No tickers to fetch" in capsys.readouterr().out


def test_the_exit_code_is_the_runs(runs):
    runs.summary = RunSummary(reports=(), write_failures=1)

    assert script.main(["--tickers", "SAB"]) == EXIT_FAILED


def test_the_summary_is_printed(runs, capsys):
    script.main(["--tickers", "SAB"])

    assert "Company feed snapshot" in capsys.readouterr().out


# --- inputs ------------------------------------------------------------------------------------


def test_the_ticker_rule_here_and_in_fetch_is_the_same():
    assert inputs._TICKER.pattern == fetch._TICKER.pattern


def test_a_missing_debate_log_or_one_without_the_table_has_no_tickers(tmp_path):
    assert inputs.tickers_from_debate_log(tmp_path / "missing.db") == ()
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert inputs.tickers_from_debate_log(empty) == ()


def test_a_non_ticker_value_in_the_debate_log_is_skipped(caplog):
    _write_debate_log(["SAB", "sab&x=1"])

    with caplog.at_level(logging.WARNING):
        assert inputs.tickers_from_debate_log() == ("SAB",)

    assert "sab&x=1" not in caplog.text


# --- no API key --------------------------------------------------------------------------------


def test_no_key_means_no_warning(tmp_path):
    assert inputs.api_key_warnings(env={}, home=tmp_path) == ()


def test_a_key_in_the_environment_is_warned_about_by_name_never_by_value(runs, capsys, caplog, monkeypatch):
    """Scenario: A key is present."""
    monkeypatch.setenv(inputs.API_KEY_ENV_VAR, SECRET)

    with caplog.at_level(logging.WARNING):
        code = script.main(["--tickers", "SAB"])

    output = capsys.readouterr()
    assert code == EXIT_OK and len(runs) == 1  # warned, and still ran
    assert inputs.API_KEY_ENV_VAR in output.out
    assert SECRET not in output.out + output.err + caplog.text
    assert any(r.levelno == logging.WARNING and inputs.API_KEY_ENV_VAR in r.getMessage() for r in caplog.records)


def test_the_key_file_is_noticed_by_existence_and_never_opened(tmp_path, monkeypatch):
    key_file = tmp_path / inputs.API_KEY_FILE
    key_file.parent.mkdir()
    key_file.write_text(f'{{"key": "{SECRET}"}}', encoding="utf-8")
    real_open = builtins.open

    def guarded_open(file, *args, **kwargs):
        if str(file) == str(key_file):
            raise AssertionError("the key file was opened")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: pytest.fail("read_text on a path"))
    monkeypatch.setattr(Path, "open", lambda self, *a, **k: pytest.fail("Path.open on a path"))

    warnings = inputs.api_key_warnings(env={}, home=tmp_path)

    assert len(warnings) == 1 and "key file" in warnings[0] and SECRET not in warnings[0]


def test_no_credential_is_stored_in_the_log(monkeypatch):
    """Scenario: No credential in the log file."""
    monkeypatch.setenv(inputs.API_KEY_ENV_VAR, SECRET)

    store.record_fetch(FetchRow(ticker="SAB", source="vci", kind="news", status="empty", items_returned=0, vnstock_version="4.0.5"), ())

    assert SECRET.encode() not in company_feed_log.COMPANY_FEED_LOG_DB_PATH.read_bytes()


# --- the script's own text ---------------------------------------------------------------------


def test_the_docstring_states_how_and_why_to_run_it():
    doc = script.__doc__

    for phrase in (
        "from the project root", "Personal use only", "Guest tier, no API key", "daily run after the market close",
        "cron", "does NOT install", "company_feed_log.db", "docs/KNOWN_ISSUES.md", "--dry-run", "Exit code",
    ):
        assert phrase in doc, phrase


def test_neither_the_script_nor_the_package_mentions_a_model_client():
    texts = [(BACKEND / "scripts" / "snapshot_company_feed.py").read_text(encoding="utf-8")]
    texts += [path.read_text(encoding="utf-8") for path in (BACKEND / "app" / "services" / "company_feed").glob("*.py")]

    for text in texts:
        assert "LLMClient" not in text and "llm_client" not in text
        assert "import openai" not in text and "import anthropic" not in text
