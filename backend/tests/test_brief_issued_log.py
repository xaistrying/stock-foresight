"""issued_log.py: what earlier briefs said, kept privately (spec: "The issued-brief log records...")."""

from __future__ import annotations

import json
import os
import stat

import pytest

from app.services.brief import issued_log
from app.services.brief.holdings import default_holdings_path
from app.services.brief.issued_log import IssuedEntry, IssuedLogError, append_entries, issued_log_path, read_log

from .test_brief_support import REPO_ROOT, brief_isolation  # noqa: F401


def _entry(ticker="AAA", as_of="2026-10-09", issued_at="2026-10-09T09:00:00+00:00", **fields) -> IssuedEntry:
    base = dict(
        issued_at=issued_at, ticker=ticker, as_of=as_of, close=42.90, provisional=False, status="ok",
        band_pct=2.7, band_lo=41.76, band_hi=44.07, calibrated=True, model_version="m-1", refreshed=True,
    )
    base.update(fields)
    return IssuedEntry(**base)


def _lines(path):
    return path.read_text().splitlines()


def _good_line(ticker="AAA", as_of="2026-10-09", **extra) -> bytes:
    return json.dumps({"ticker": ticker, "as_of": as_of, "status": "ok", "close": 1.0, **extra}).encode() + b"\n"


def test_append_creates_a_private_file_with_one_valid_json_line_per_entry(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"

    append_entries(path, (_entry("AAA"), _entry("BBB")))

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    rows = [json.loads(line) for line in _lines(path)]
    assert [row["ticker"] for row in rows] == ["AAA", "BBB"]
    assert set(rows[0]) == {
        "schema", "issued_at", "ticker", "as_of", "close", "provisional", "status", "band_pct", "band_lo",
        "band_hi", "calibrated", "model_version", "refreshed",
    }
    assert rows[0]["schema"] == 1


def test_the_log_carries_no_shares_cost_purchase_date_or_level_data(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"

    append_entries(path, (_entry(),))

    text = path.read_text()
    assert not any(word in text for word in ("shares", "cost", "purchase", "levels", "text", "comparator", "reached"))


def test_a_batch_is_written_with_a_single_write_call(tmp_path, monkeypatch):
    calls = []
    real_write = os.write
    monkeypatch.setattr(issued_log.os, "write", lambda fd, data: calls.append(data) or real_write(fd, data))

    append_entries(tmp_path / "holdings_issued.jsonl", (_entry("AAA"), _entry("BBB"), _entry("CCC")))

    assert len(calls) == 1 and calls[0].count(b"\n") == 3


def test_the_data_is_flushed_to_disk(tmp_path, monkeypatch):
    synced = []
    monkeypatch.setattr(issued_log.os, "fsync", lambda fd: synced.append(fd))

    append_entries(tmp_path / "holdings_issued.jsonl", (_entry(),))

    assert len(synced) == 1


def test_append_adds_to_an_existing_file(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    append_entries(path, (_entry("AAA"),))
    append_entries(path, (_entry("BBB"),))

    assert len(_lines(path)) == 2


def test_an_append_failure_raises_a_clear_error(tmp_path):
    with pytest.raises(IssuedLogError, match="could not be appended"):
        append_entries(tmp_path / "missing_dir" / "holdings_issued.jsonl", (_entry(),))


def test_a_looser_existing_file_is_made_private(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    path.write_bytes(_good_line())
    path.chmod(0o644)

    append_entries(path, (_entry(),))

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_symlinked_log_is_refused(tmp_path):
    target = tmp_path / "elsewhere.jsonl"
    target.write_bytes(b"")
    link = tmp_path / "holdings_issued.jsonl"
    link.symlink_to(target)

    with pytest.raises(IssuedLogError, match="could not be appended"):
        append_entries(link, (_entry(),))

    assert target.read_bytes() == b""


def test_a_directory_in_place_of_the_log_is_refused(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    path.mkdir()

    with pytest.raises(IssuedLogError):
        append_entries(path, (_entry(),))


def test_a_log_owned_by_someone_else_is_refused(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    path.write_bytes(b"")

    with pytest.raises(IssuedLogError, match="not a regular file of yours"):
        append_entries(path, (_entry(),), uid=path.stat().st_uid + 1)


def test_the_log_is_opened_without_following_a_symlink(tmp_path):
    import inspect

    assert "O_NOFOLLOW" in inspect.getsource(issued_log.append_entries) + inspect.getsource(issued_log.read_log)


# --- reading ---------------------------------------------------------------------------------------------

def test_the_reader_round_trips_an_entry(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    original = _entry()
    append_entries(path, (original,))

    result = read_log(path)

    assert result.entries == (original,) and result.skipped == 0


def test_the_reader_keeps_the_latest_entry_per_ticker_and_date(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    append_entries(path, (_entry(close=42.9),))
    append_entries(path, (_entry(close=43.0), _entry("BBB")))

    by_key = {(e.ticker, e.as_of): e for e in read_log(path).entries}

    assert len(by_key) == 2 and by_key[("AAA", "2026-10-09")].close == 43.0


def test_a_provisional_and_a_final_entry_for_the_same_bar_are_both_kept(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    append_entries(path, (_entry(close=22.9, provisional=True),))
    append_entries(path, (_entry(close=23.0, provisional=False),))

    result = read_log(path)

    assert sorted((e.provisional, e.close) for e in result.entries) == [(False, 23.0), (True, 22.9)]


def test_a_degraded_rerun_does_not_replace_a_good_entry(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    append_entries(path, (_entry(),))
    append_entries(path, (_entry(status="error", band_pct=None, band_lo=None, band_hi=None, calibrated=None),))

    (entry,) = read_log(path).entries

    assert entry.status == "ok" and entry.band_pct == 2.7


def test_a_good_entry_replaces_a_degraded_one(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    append_entries(path, (_entry(status="error", band_pct=None, band_lo=None, band_hi=None, calibrated=None),))
    append_entries(path, (_entry(),))

    assert read_log(path).entries[0].status == "ok"


def test_for_ticker_filters_by_ticker(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    append_entries(path, (_entry("AAA", as_of="2026-10-02"), _entry("AAA"), _entry("BBB")))

    result = read_log(path)

    assert [e.as_of for e in result.for_ticker("AAA")] == ["2026-10-02", "2026-10-09"]
    assert result.for_ticker("ZZZ") == ()


def test_previous_issued_at_is_the_latest_strictly_earlier_run(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    append_entries(path, (_entry(as_of="2026-10-02", issued_at="2026-10-02T09:00:00+00:00"),))
    append_entries(path, (_entry(as_of="2026-10-09", issued_at="2026-10-09T09:00:00+00:00"),))
    result = read_log(path)

    assert result.previous_issued_at("AAA", before="2026-10-09") == "2026-10-02T09:00:00+00:00"
    assert result.previous_issued_at("AAA") == "2026-10-09T09:00:00+00:00"
    assert result.previous_issued_at("ZZZ") is None
    assert result.previous_issued_at("AAA", before="2026-10-02") is None


def test_a_bad_line_is_skipped_and_counted(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    path.write_bytes(b"not json\n" + _good_line() + b'{"ticker": "BBB"}\n[1, 2]\n\n')

    result = read_log(path)

    assert [e.ticker for e in result.entries] == ["AAA"] and result.skipped == 3


def test_unknown_keys_and_the_old_levels_key_are_ignored(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    path.write_bytes(_good_line(dividends=[1, 2], levels=[{"text": "old"}], status_extra=1))

    (entry,) = read_log(path).entries

    assert entry.band_pct is None and entry.provisional is False and entry.refreshed is False


def test_a_missing_file_is_an_empty_log(tmp_path):
    result = read_log(tmp_path / "holdings_issued.jsonl")

    assert result.entries == () and result.skipped == 0


@pytest.mark.parametrize("separator", [" ", " ", "\u0085", "\x0b", "\x0c", "\x1c"])
def test_unicode_line_separators_do_not_split_or_lose_lines(tmp_path, separator):
    path = tmp_path / "holdings_issued.jsonl"
    odd = json.dumps({"ticker": "BBB", "as_of": "2026-10-09", "status": "ok", "model_version": f"a{separator}b"}, ensure_ascii=False)
    path.write_bytes(_good_line("AAA") + odd.encode() + b"\n" + _good_line("CCC"))

    result = read_log(path)

    assert [e.ticker for e in result.entries] == ["AAA", "CCC"] and result.skipped == 1


def test_an_invalid_utf8_byte_costs_one_line_not_the_file(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    path.write_bytes(_good_line("AAA") + b'{"ticker": "B\xffB"}\n' + _good_line("CCC"))

    result = read_log(path)

    assert [e.ticker for e in result.entries] == ["AAA", "CCC"] and result.skipped == 1


def test_a_torn_last_line_is_skipped_and_the_next_append_starts_a_new_line(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    path.write_bytes(_good_line("AAA") + b'{"ticker": "BBB", "as_of": "2026-10')

    assert read_log(path).skipped == 1
    append_entries(path, (_entry("CCC"),))
    result = read_log(path)

    assert [e.ticker for e in result.entries] == ["AAA", "CCC"] and result.skipped == 1


def test_an_append_after_a_complete_last_line_adds_no_blank_line(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    path.write_bytes(_good_line("AAA"))

    append_entries(path, (_entry("BBB"),))

    assert b"\n\n" not in path.read_bytes()


@pytest.mark.parametrize(
    "fields",
    [
        {"model_version": "\x1b[31mred"}, {"status": "ok\x1b]0;x\x07"}, {"ticker": "AA\nA"}, {"as_of": "2026-10-09\x1b"},
        {"as_of": "２０２６-10-09"}, {"close": float("nan")}, {"issued_at": "\x1b[2J"},
    ],
)
def test_a_string_with_an_escape_sequence_is_not_read_back(tmp_path, fields):
    path = tmp_path / "holdings_issued.jsonl"
    row = {"ticker": "AAA", "as_of": "2026-10-09", "status": "ok", **fields}
    path.write_text(json.dumps(row) + "\n")  # json.dumps writes NaN as the bare token NaN

    assert read_log(path).entries == () and read_log(path).skipped == 1


def test_a_huge_number_is_a_bad_line_not_a_crash(tmp_path):
    path = tmp_path / "holdings_issued.jsonl"
    path.write_bytes(b'{"ticker": "AAA", "as_of": "2026-10-09", "status": "ok", "close": ' + b"9" * 400 + b"}\n")

    assert read_log(path).skipped == 1


def test_a_symlinked_or_directory_log_reads_as_unreadable_not_followed(tmp_path):
    target = tmp_path / "t.jsonl"
    target.write_bytes(_good_line())
    link = tmp_path / "holdings_issued.jsonl"
    link.symlink_to(target)

    assert read_log(link).entries == () and read_log(link).skipped == 1


def test_the_log_sits_beside_the_holdings_file_outside_the_repository():
    holdings = default_holdings_path()

    log = issued_log_path(holdings)

    assert log.parent == holdings.parent and log.name == "holdings_issued.jsonl"
    assert not log.resolve().is_relative_to(REPO_ROOT)
    assert not log.resolve().is_relative_to(REPO_ROOT / "reports")
