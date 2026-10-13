"""The share-count cache file (`add-announcement-tags-and-insider-sizing`, task 3.3): beside the holdings file,
private, atomic, malformed means empty and is reported once, a 7-day age rule. Injected paths only."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.brief.share_cache import (
    CACHE_FILE_NAME, SHARE_COUNT_CACHE_MAX_AGE_DAYS, ShareCache, ShareCount, is_fresh, share_cache_path,
)

from .test_brief_support import REPO_ROOT, brief_isolation  # noqa: F401

NOW = datetime(2026, 10, 12, 5, 0, tzinfo=timezone.utc)
ENTRY = ShareCount(1_282_562_372, 2026, 2, NOW - timedelta(days=3))


def _private_dir(tmp_path) -> Path:
    directory = tmp_path / "config"
    directory.mkdir(mode=0o700)
    return directory / CACHE_FILE_NAME


def test_the_path_is_beside_the_holdings_file_under_the_holdings_prefix(tmp_path):
    assert share_cache_path(tmp_path / "x" / "holdings.toml") == tmp_path / "x" / "holdings_share_counts.json"
    assert CACHE_FILE_NAME.startswith("holdings") and CACHE_FILE_NAME.endswith(".json")


def test_git_ignores_the_cache_file_name_at_the_root_and_under_backend():
    result = subprocess.run(
        ["git", "check-ignore", CACHE_FILE_NAME, f"backend/{CACHE_FILE_NAME}"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )

    assert set(result.stdout.split()) == {CACHE_FILE_NAME, f"backend/{CACHE_FILE_NAME}"}


def test_a_missing_file_is_an_empty_cache_without_a_note(tmp_path):
    cache = ShareCache(_private_dir(tmp_path))

    assert cache.get("AAA") is None and cache.notes == []


def test_a_put_is_written_atomically_at_mode_600_and_read_back_by_the_next_run(tmp_path):
    path = _private_dir(tmp_path)

    ShareCache(path).put("AAA", ENTRY)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [p.name for p in path.parent.iterdir()] == [CACHE_FILE_NAME]  # no temporary file left
    again = ShareCache(path).get("AAA")
    assert again == ENTRY and again.fetched_at.tzinfo is not None
    data = json.loads(path.read_text())
    assert data["counts"]["AAA"]["count"] == 1_282_562_372 and data["counts"]["AAA"]["year_report"] == 2026 and "fetched_at" in data["counts"]["AAA"]


def test_a_put_keeps_the_other_tickers(tmp_path):
    path = _private_dir(tmp_path)
    cache = ShareCache(path)
    cache.put("AAA", ENTRY)
    cache.put("BBB", ShareCount(500, 2026, 1, NOW))

    reread = ShareCache(path)

    assert reread.get("AAA") == ENTRY and reread.get("BBB").count == 500


def test_a_group_or_world_readable_file_is_refused_and_not_overwritten(tmp_path):
    path = _private_dir(tmp_path)
    ShareCache(path).put("AAA", ENTRY)
    path.chmod(0o644)

    cache = ShareCache(path)
    cache.put("BBB", ShareCount(500, 2026, 1, NOW))

    assert cache.get("AAA") is None and cache.get("BBB") is not None  # nothing was read; the new value lives in memory only
    assert any("can be read by other users" in note for note in cache.notes)
    assert "BBB" not in path.read_text()  # not written over a file the investor has not made private


def test_a_directory_others_can_write_to_is_refused(tmp_path):
    path = _private_dir(tmp_path)
    path.parent.chmod(0o777)
    try:
        cache = ShareCache(path)
        cache.put("AAA", ENTRY)

        assert any("can be written by other users" in n for n in cache.notes) and not path.exists()
    finally:
        path.parent.chmod(0o700)


def test_a_symlink_is_not_followed(tmp_path):
    path = _private_dir(tmp_path)
    target = tmp_path / "elsewhere.json"
    target.write_text("{}")
    target.chmod(0o600)
    path.symlink_to(target)

    cache = ShareCache(path)

    assert cache.get("AAA") is None and cache.notes and target.read_text() == "{}"


def test_a_file_owned_by_another_user_is_refused(tmp_path):
    path = _private_dir(tmp_path)
    ShareCache(path).put("AAA", ENTRY)

    cache = ShareCache(path, uid=os.getuid() + 1)

    assert cache.get("AAA") is None and any("another user" in n for n in cache.notes)


def test_a_malformed_file_is_treated_as_empty_and_reported_once(tmp_path):
    path = _private_dir(tmp_path)
    path.write_text("{not json")
    path.chmod(0o600)

    cache = ShareCache(path)

    assert cache.get("AAA") is None and len(cache.notes) == 1 and "treated as empty" in cache.notes[0]
    cache.put("AAA", ENTRY)
    assert len(cache.notes) == 1 and ShareCache(path).get("AAA") == ENTRY  # replaced by a good file on the next put


def test_unusable_entries_are_dropped_and_counted_in_one_note(tmp_path):
    path = _private_dir(tmp_path)
    good = {"count": 10, "year_report": 2026, "quarter": 2, "fetched_at": "2026-10-09T05:00:00+00:00"}
    path.write_text(json.dumps({"schema": 1, "counts": {
        "AAA": good, "bbb": good, "CCC": {**good, "count": 0}, "DDD": {**good, "count": True}, "EEE": {**good, "quarter": 5},
        "FFF": {**good, "fetched_at": "2026-10-09T05:00:00"}, "GGG": {**good, "fetched_at": "garbage"}, "HHH": "x",
    }}))
    path.chmod(0o600)

    cache = ShareCache(path)

    assert cache.get("AAA") is not None and all(cache.get(t) is None for t in ("bbb", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"))
    assert len(cache.notes) == 1 and "7 unusable entries" in cache.notes[0]


def test_a_wrong_schema_is_treated_as_empty(tmp_path):
    path = _private_dir(tmp_path)
    path.write_text(json.dumps({"schema": 99, "counts": {}}))
    path.chmod(0o600)

    assert ShareCache(path).notes and ShareCache(path).get("AAA") is None


def test_a_missing_directory_is_an_empty_cache_and_a_put_is_a_note_not_a_crash(tmp_path):
    cache = ShareCache(tmp_path / "absent" / CACHE_FILE_NAME)

    cache.put("AAA", ENTRY)

    assert cache.get("AAA") == ENTRY and any("could not be written" in n for n in cache.notes)


def test_the_seven_day_age_rule():
    assert SHARE_COUNT_CACHE_MAX_AGE_DAYS == 7
    assert is_fresh(ShareCount(1, 2026, 1, NOW - timedelta(days=3)), NOW)
    assert is_fresh(ShareCount(1, 2026, 1, NOW - timedelta(days=7)), NOW)
    assert not is_fresh(ShareCount(1, 2026, 1, NOW - timedelta(days=7, seconds=1)), NOW)
    assert not is_fresh(ShareCount(1, 2026, 1, NOW + timedelta(hours=1)), NOW)  # stamped in the future: not trusted


def test_a_fetch_time_that_overflows_is_an_unusable_entry_not_a_crash(tmp_path):
    path = _private_dir(tmp_path)
    good = {"count": 10, "year_report": 2026, "quarter": 2}
    path.write_text(json.dumps({"schema": 1, "counts": {
        "AAA": {**good, "fetched_at": "0001-01-01T00:00:00+05:00"}, "BBB": {**good, "fetched_at": "9999-12-31T23:59:59-05:00"},
        "CCC": {**good, "fetched_at": "2026-10-09T05:00:00+00:00"},
    }}))
    path.chmod(0o600)

    cache = ShareCache(path)

    assert cache.get("AAA") is None and cache.get("BBB") is None and cache.get("CCC") is not None


def test_a_fifo_at_the_cache_path_is_refused_without_blocking(tmp_path):
    path = _private_dir(tmp_path)
    os.mkfifo(path, 0o600)

    cache = ShareCache(path)

    assert cache.get("AAA") is None and any("not a regular file" in n for n in cache.notes)


def test_an_input_error_while_reading_the_cache_is_no_cache_with_a_note_and_the_file_is_not_overwritten(tmp_path, monkeypatch):
    import errno

    path = _private_dir(tmp_path)
    ShareCache(path).put("AAA", ENTRY)
    before = path.read_text()

    def failing_read(descriptor, length):
        raise OSError(errno.EIO, "synthetic")

    monkeypatch.setattr(os, "read", failing_read)
    cache = ShareCache(path)
    monkeypatch.undo()
    cache.put("BBB", ShareCount(500, 2026, 1, NOW))

    assert cache.get("AAA") is None and any("could not be read" in n for n in cache.notes)
    assert path.read_text() == before  # an unreadable cache is not replaced by a partial one
