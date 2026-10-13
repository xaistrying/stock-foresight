"""Shared helpers and the isolation fixture for the weekly brief tests (`add-weekly-holdings-brief`).

Every other `test_brief_*.py` imports `brief_isolation` and `brief_env` from here. Hypothetical data
only: no real position, price list or holdings file is read or written anywhere in these tests.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.db import connection as db_connection
from app.db.schema import CREATE_OHLCV_TABLE
from app.ml import volatility as vol_mod
from app.services import bulk_ingestion, ticker_ingestion
from app.services import range as range_service
from app.services.brief.facts import MarketFacts
from app.services.brief.holdings import Holding, Level
from app.services.brief.issued_log import IssuedEntry, LogRead
from app.services.brief.week import WeekFacts

BACKEND = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND.parent
ICT = timezone(timedelta(hours=7))

ARTIFACT = {
    "schema_version": 1,
    "model_version": "har-rv-test-0001",
    "trained_at": "2026-10-07T00:00:00+00:00",
    "data_through": "2026-09-15",
    "features": ["rv5", "rv20", "rv60"],
    "intercept": -4.94,
    "coef": {"rv5": 9.28, "rv20": 13.77, "rv60": 14.18},
    "target": "ln(std of next 5 daily log returns)",
    "range_k": 1.2,
    "range_coverage": 0.68,
    "universe": {"criteria": "test", "n_tickers": 3, "symbols": ["AAA", "BBB", "CCC"]},
    "n_rows": 1000,
    "validation": {},
}


def make_closes(n: int, *, noise: float = 0.012, seed: int = 1, start: float = 20.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return start * np.exp(np.cumsum(rng.normal(0, noise, n)))


def sessions_ending(last: str, n: int) -> list[str]:
    """`n` weekday dates, the newest being `last` (which must itself be a weekday)."""
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(end=last, periods=n)]


def ict(text: str) -> datetime:
    """An aware datetime from 'YYYY-MM-DD HH:MM' read as Vietnam time."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=ICT)


def write_artifact(path: Path, **overrides) -> Path:
    path.write_text(json.dumps({**ARTIFACT, **overrides}))
    return path


@dataclass
class BriefEnv:
    db_path: Path
    model_path: Path
    eligibility: dict[str, list[str]] = field(default_factory=dict)

    def add_ticker(self, ticker: str, closes, dates: list[str] | None = None) -> list[str]:
        closes = list(closes)
        dates = dates or sessions_ending("2026-10-09", len(closes))
        conn = sqlite3.connect(self.db_path)
        conn.execute(CREATE_OHLCV_TABLE)
        conn.executemany(
            "INSERT OR REPLACE INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, 1)",
            [(ticker, d, c, c, c, c) for d, c in zip(dates, closes)],
        )
        conn.commit()
        conn.close()
        return dates


@pytest.fixture(autouse=True)
def brief_isolation(tmp_path, monkeypatch):
    """The real database, the real model and the vendor are out of reach (spec: "Tests never touch...").

    `DB_PATH` points at a temporary file, the model path at a file that does not exist, and
    `load_ticker` fails the test if anything calls it without injecting a loader.
    """
    monkeypatch.setattr(db_connection, "DB_PATH", tmp_path / "isolated" / "app.db")
    monkeypatch.setattr(vol_mod, "MODEL_PATH", tmp_path / "isolated" / "no_model.json")

    def forbidden_loader(ticker, *args, **kwargs):
        pytest.fail(f"load_ticker({ticker!r}) was called without an injected loader")

    monkeypatch.setattr(ticker_ingestion, "load_ticker", forbidden_loader)
    monkeypatch.setattr(bulk_ingestion, "load_ticker", forbidden_loader)


@pytest.fixture
def brief_env(tmp_path, monkeypatch) -> BriefEnv:
    """A temporary OHLCV database and model artifact behind the real `compute_range`."""
    db_path = tmp_path / "brief_app.db"
    model_path = write_artifact(tmp_path / "brief_model.json")
    monkeypatch.setattr(db_connection, "DB_PATH", db_path)
    monkeypatch.setattr(vol_mod, "MODEL_PATH", model_path)
    env = BriefEnv(db_path, model_path)
    env.add_ticker("PLACEHOLDER", [])  # creates the empty ohlcv table

    def fake_assess(ticker):
        reasons = list(env.eligibility.get(ticker, []))
        return {"eligible": not reasons, "reasons": reasons, "as_of": "2026-10-09", "age_sessions": 0}

    monkeypatch.setattr(range_service, "assess_eligibility", fake_assess)
    return env


def fake_loader_factory(outcomes: dict | None = None, *, default: str = "ok"):
    """A loader that records its calls and returns `{"status": ...}` or raises what `outcomes` says.

    An outcome that is an exception instance is raised; a string is the returned status.
    """
    calls: list[str] = []
    outcomes = outcomes or {}

    def loader(ticker: str, timings=None):
        calls.append(ticker)
        outcome = outcomes.get(ticker, default)
        if isinstance(outcome, BaseException):
            raise outcome
        return {"status": outcome, "rows_loaded": 100}

    loader.calls = calls
    return loader


def make_level(comparator="below", price=41.60, entered=date(2026, 10, 2), text="Trim 300 shares if the close is below 41.60"):
    return Level(comparator=comparator, price=price, entered=entered, text=text)


def make_holding(
    ticker="AAA", shares=1234, cost=41.80, purchase_date=date(2025, 6, 10), shares_as_of=None, levels=(),
) -> Holding:
    """A hypothetical holding with distinctive numbers (1,234 shares, cost 41.80)."""
    return Holding(
        ticker=ticker, shares=shares, cost=cost, purchase_date=purchase_date,
        shares_as_of=shares_as_of, levels=tuple(levels),
    )


def make_issued_entry(ticker="AAA", as_of="2026-10-02", **fields) -> IssuedEntry:
    """A hypothetical earlier log line: close 41.00, band 2.7 (41.00 x exp(-0.027) to x exp(0.027))."""
    base = dict(
        issued_at="2026-10-02T10:00:00+00:00", ticker=ticker, as_of=as_of, close=41.00, provisional=False,
        status="ok", band_pct=2.7, band_lo=39.91, band_hi=42.12, calibrated=True, model_version="m-1",
        refreshed=True,
    )
    base.update(fields)
    return IssuedEntry(**base)


def make_log(*entries: IssuedEntry) -> LogRead:
    return LogRead(tuple(entries), 0)


def make_week(**fields) -> WeekFacts:
    """A hypothetical week: 41.00 -> 42.00 (+2.4%), inside last week's range of +-2.7%."""
    base = dict(
        first_date="2026-10-05", last_date="2026-10-09", base_date="2026-10-02", base_close=41.00, last_close=42.00,
        move_pct=(42.0 / 41.0 - 1) * 100, kind="band", band_pct=2.7, band_lo=39.91, band_hi=42.12, inside=True,
    )
    base.update(fields)
    return WeekFacts(**base)


def make_facts(ticker="AAA", **fields) -> MarketFacts:
    """Hypothetical market facts for an `ok` ticker: close 42.90, band 2.7, calibrated at 0.68."""
    base = dict(
        ticker=ticker, refresh="ok", refresh_detail="ok", last_bar="2026-10-09", close=42.90, provisional=False,
        status="ok", reasons=(), band_pct=2.7, band_lo=42.90 * math.exp(-0.027), band_hi=42.90 * math.exp(0.027),
        range_coverage=0.68, calibrated=True, model_version="m-1", week=make_week(), readjusted=None,
        error_class=None,
    )
    base.update(fields)
    return MarketFacts(**base)


def write_holdings_toml(path: Path, body: str, *, mode: int = 0o600) -> Path:
    path.write_text(body)
    path.chmod(mode)
    return path


VALID_TOML = """
[[holdings]]
ticker = "AAA"
shares = 1000
cost = 41.80
purchase_date = 2025-06-10

  [[holdings.levels]]
  comparator = "below"
  price = 41.60
  entered = 2026-10-02
  text = "Trim 300 shares if the close is below 41.60"
"""


# --- tests of the helpers themselves -------------------------------------------------------------

def test_the_isolation_fixture_points_the_database_at_a_temporary_file(tmp_path):
    assert db_connection.DB_PATH.is_relative_to(tmp_path)
    assert not db_connection.DB_PATH.is_relative_to(BACKEND / "data")


def test_an_uninjected_loader_fails_the_test():
    with pytest.raises(pytest.fail.Exception):
        ticker_ingestion.load_ticker("AAA")


def test_an_uninjected_bulk_loader_fails_the_test():
    with pytest.raises(pytest.fail.Exception):
        bulk_ingestion.load_ticker("AAA")


def test_the_default_model_path_is_absent(tmp_path):
    assert vol_mod.load_model() is None


def test_brief_env_serves_a_range_from_the_temporary_files(brief_env):
    dates = brief_env.add_ticker("AAA", make_closes(120))

    result = range_service.compute_range("AAA")

    assert result.status == "ok" and result.as_of == dates[-1]
    assert db_connection.DB_PATH == brief_env.db_path


def test_the_fake_loader_records_and_raises():
    loader = fake_loader_factory({"BBB": RuntimeError("boom"), "CCC": "no_data"})

    assert loader("AAA")["status"] == "ok"
    assert loader("CCC")["status"] == "no_data"
    with pytest.raises(RuntimeError):
        loader("BBB")
    assert loader.calls == ["AAA", "CCC", "BBB"]
