"""The last share count per held ticker, kept beside the holdings file (`add-announcement-tags-and-insider-sizing`).

`holdings_share_counts.json` lists the investor's tickers, so it gets the holdings file's rules: outside the
repository (the holdings path is), opened without following a symlink, a regular file owned by the user, not
readable by group or others, in a directory others cannot write to, and written atomically at mode 600. An
unreadable, unsafe or malformed file is treated as empty and reported once; the brief then falls back to a fetch
or to the no-size wording. Only a value that passed the vendor cross-check is ever given to `put`; there is no
database and no schema change. The file holds the count, its period (`year_report`, `quarter`) and the fetch time.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.brief.holdings import TICKER_PATTERN

CACHE_FILE_NAME = "holdings_share_counts.json"
SCHEMA = 1
SHARE_COUNT_CACHE_MAX_AGE_DAYS = 7  # a value older than this is fetched again
FILE_MODE = 0o600
_PRIVATE_MASK, _WRITABLE_MASK = 0o077, 0o022
_MAX_BYTES = 256 * 1024
_MAX_COUNT = 10**13


@dataclass(frozen=True)
class ShareCount:
    count: int
    year_report: int
    quarter: int
    fetched_at: datetime  # UTC


def share_cache_path(holdings_path: Path) -> Path:
    """Beside the holdings file and the issued-brief log, so it has the same directory and privacy."""
    return holdings_path.parent / CACHE_FILE_NAME


def is_fresh(entry: ShareCount, now: datetime) -> bool:
    """Not older than the maximum age; a value stamped in the future is not trusted."""
    age = now - entry.fetched_at
    return timedelta(0) <= age <= timedelta(days=SHARE_COUNT_CACHE_MAX_AGE_DAYS)


class ShareCache:
    """The cache file read once; `put` writes through atomically. `notes` holds what to tell the investor, once."""

    def __init__(self, path: Path, *, uid: int | None = None) -> None:
        self.path = path
        self._uid = os.getuid() if uid is None else uid
        self.notes: list[str] = []
        self._entries: dict[str, ShareCount] = {}
        self._writable = True
        self._load()

    def get(self, ticker: str) -> ShareCount | None:
        return self._entries.get(ticker)

    def put(self, ticker: str, entry: ShareCount) -> None:
        """Remember a cross-checked count and write the file; a failure is a note, never an exception."""
        self._entries = {**self._entries, ticker: entry}
        if not self._writable:
            return
        try:
            self._write()
        except OSError as error:
            self.note(f"the share-count cache {self.path} could not be written ({type(error).__name__}); sizing will fetch again next run")

    def note(self, text: str) -> None:
        """Something to tell the investor once (stderr); a repeated text is kept once."""
        if text not in self.notes:
            self.notes.append(text)

    # --- reading ------------------------------------------------------------------------------------------
    def _load(self) -> None:
        try:
            parent_mode = self.path.parent.stat().st_mode
        except OSError:
            return  # no directory yet: an empty cache, and the first write will fail visibly
        if parent_mode & _WRITABLE_MASK:
            self._refuse(f"the directory {self.path.parent} can be written by other users; run: chmod 700 {self.path.parent}")
            return
        try:
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        except FileNotFoundError:
            return
        except OSError as error:
            self._refuse(f"the share-count cache {self.path} could not be opened ({type(error).__name__})")
            return
        try:
            raw = self._read_private(descriptor)
        except _Unsafe as problem:
            self._refuse(str(problem))
            return
        except OSError as error:  # for example an input error: no cache, and not a file to write over
            self._refuse(f"the share-count cache {self.path} could not be read ({type(error).__name__}); it was not used")
            return
        finally:
            os.close(descriptor)
        self._entries = self._parse(raw)

    def _read_private(self, descriptor: int) -> bytes:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _Unsafe(f"the share-count cache {self.path} is not a regular file; it was not used")
        if info.st_uid != self._uid:
            raise _Unsafe(f"the share-count cache {self.path} is owned by another user; it was not used")
        if info.st_mode & _PRIVATE_MASK:
            raise _Unsafe(f"the share-count cache {self.path} can be read by other users; it was not used (run: chmod 600)")
        if info.st_size > _MAX_BYTES:
            raise _Unsafe(f"the share-count cache {self.path} is larger than {_MAX_BYTES // 1024} KiB; it was not used")
        chunks, total = [], 0
        while chunk := os.read(descriptor, 65536):
            chunks.append(chunk)
            total += len(chunk)
            if total > _MAX_BYTES:
                raise _Unsafe(f"the share-count cache {self.path} is larger than {_MAX_BYTES // 1024} KiB; it was not used")
        return b"".join(chunks)

    def _refuse(self, text: str) -> None:
        self._writable = False  # never write over a file or directory the investor has not made private
        self.note(text)

    def _parse(self, raw: bytes) -> dict[str, ShareCount]:
        try:
            data = json.loads(raw.decode("utf-8"))
            counts = data["counts"]
            if data.get("schema") != SCHEMA or not isinstance(counts, dict):
                raise ValueError("unexpected shape")
        except (ValueError, KeyError, TypeError, UnicodeDecodeError, RecursionError):
            self.note(f"the share-count cache {self.path} could not be read and is treated as empty")
            return {}
        entries = {}
        for ticker, value in counts.items():
            entry = _entry(ticker, value)
            if entry is not None:
                entries[ticker] = entry
        if len(entries) != len(counts):
            self.note(f"{len(counts) - len(entries)} unusable entr{'y' if len(counts) - len(entries) == 1 else 'ies'} in {self.path} ignored")
        return entries

    # --- writing ------------------------------------------------------------------------------------------
    def _write(self) -> None:
        payload = {
            "schema": SCHEMA,
            "counts": {
                ticker: {
                    "count": e.count, "year_report": e.year_report, "quarter": e.quarter,
                    "fetched_at": e.fetched_at.isoformat(timespec="seconds"),
                }
                for ticker, e in sorted(self._entries.items())
            },
        }
        data = json.dumps(payload, ensure_ascii=True, indent=1).encode("ascii") + b"\n"
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, FILE_MODE)
        try:
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(descriptor, view):]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, self.path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise


class _Unsafe(Exception):
    """The cache file or its directory is not private enough to use."""


def _entry(ticker: object, value: object) -> ShareCount | None:
    if not isinstance(ticker, str) or TICKER_PATTERN.fullmatch(ticker) is None or not isinstance(value, dict):
        return None
    count, year, quarter = value.get("count"), value.get("year_report"), value.get("quarter")
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in (count, year, quarter)):
        return None
    if not 0 < count < _MAX_COUNT or not 1990 <= year <= 2100 or not 1 <= quarter <= 4:
        return None
    try:
        fetched = datetime.fromisoformat(value["fetched_at"])
        if fetched.tzinfo is None:
            return None
        return ShareCount(count, year, quarter, fetched.astimezone(timezone.utc))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
