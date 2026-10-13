"""The read-only query tool the brief-auditor agent uses instead of a raw `sqlite3` shell.

A raw `sqlite3` CLI can read any file on the machine (`readfile()`, dot-commands); this tool opens one of three
fixed databases with `mode=ro` and lets one SELECT through.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "brief_audit_query.py"


def _load():
    spec = importlib.util.spec_from_file_location("brief_audit_query", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["brief_audit_query"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tool(tmp_path, monkeypatch):
    module = _load()
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("create table ohlcv (ticker text, date text, close real)")
    conn.executemany("insert into ohlcv values (?, ?, ?)", [("AAA", f"2026-10-{d:02d}", 40.0 + d) for d in range(1, 29)])
    conn.commit()
    conn.close()
    monkeypatch.setitem(module.DATABASES, "app", db)
    return module, db


def _run(module, alias, sql):
    return module.run_query(alias, sql)


def test_a_select_returns_a_header_and_tab_separated_rows(tool):
    module, _ = tool

    out = _run(module, "app", "select ticker, close from ohlcv where date = '2026-10-05'")

    assert out.splitlines() == ["ticker\tclose", "AAA\t45.0"]


def test_a_trailing_semicolon_and_a_with_query_are_allowed(tool):
    module, _ = tool

    assert _run(module, "app", "with x as (select 1 as n) select n from x;").splitlines() == ["n", "1"]


def test_the_row_count_is_capped_and_says_so(tool, monkeypatch):
    module, _ = tool
    monkeypatch.setattr(module, "MAX_ROWS", 5)

    out = _run(module, "app", "select date from ohlcv").splitlines()

    assert len(out) == 5 + 2  # header, 5 rows, a truncation line
    assert "truncated at 5 rows" in out[-1]


@pytest.mark.parametrize("sql", [
    "insert into ohlcv values ('X','2026-01-01',1)",
    "delete from ohlcv",
    "drop table ohlcv",
    "update ohlcv set close = 0",
    "attach database '/etc/hostname' as h",
    "pragma writable_schema = on",
    "select 1; select 2",
    "select 1; drop table ohlcv",
    "",
    "   ",
])
def test_anything_but_one_select_is_refused(tool, sql):
    module, db = tool

    with pytest.raises(module.QueryRefused):
        _run(module, "app", sql)

    conn = sqlite3.connect(db)
    assert conn.execute("select count(*) from ohlcv").fetchone()[0] == 28
    conn.close()


@pytest.mark.parametrize("sql", [
    "select load_extension('/tmp/x.so')",
    "select readfile('/etc/hostname')",
    "select writefile('/tmp/x', 'y')",
])
def test_file_and_extension_functions_are_refused(tool, sql):
    module, _ = tool

    with pytest.raises(module.QueryRefused):
        _run(module, "app", sql)


def test_an_unknown_database_alias_is_refused(tool):
    module, _ = tool

    with pytest.raises(module.QueryRefused):
        _run(module, "/etc/passwd", "select 1")


def test_the_database_is_opened_read_only(tool):
    module, db = tool
    before = db.stat().st_mtime_ns

    _run(module, "app", "select count(*) from ohlcv")

    assert db.stat().st_mtime_ns == before
    assert "mode=ro" in module.OPEN_URI_TEMPLATE


def test_the_aliases_are_the_three_project_databases():
    module = _load()

    assert set(module.DATABASES) == {"app", "feed", "debate"}
    assert all(path.name.endswith(".db") and path.parent.name == "data" for path in module.DATABASES.values())


def test_the_tool_imports_no_vendor_or_model_client():
    source = SCRIPT.read_text(encoding="utf-8")

    for forbidden in ("vnstock", "anthropic", "requests", "httpx", "subprocess"):
        assert forbidden not in source
