"""The log of issued briefs: one JSON line per holding per run, kept beside the holdings file.

It records what a brief printed (close, range, model version, provisional flag) so the next brief can
compare the week with the range that was actually issued. It holds public market figures and the
ticker only: no shares, cost, purchase date, level price or level text. It still has the holdings
file's privacy (mode 600, outside the repository), because the set of tickers is what reveals a
holding. The reader is tolerant and defensive: unknown keys are ignored, a bad line is skipped and
counted, and every string read back is checked before it can reach the brief.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path

from app.services.brief.holdings import TICKER_PATTERN

LOG_FILE_NAME = "holdings_issued.jsonl"
SCHEMA = 1
LOG_MODE = 0o600
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
_STATUS = re.compile(r"[A-Za-z_]{1,40}")
_VERSION = re.compile(r"[\w.\-]{1,80}", re.ASCII)
_TIMESTAMP = re.compile(r"[\d:+\-TZ. ]{0,40}")


class IssuedLogError(Exception):
    """The log could not be written."""


@dataclass(frozen=True)
class IssuedEntry:
    issued_at: str  # UTC, ISO
    ticker: str
    as_of: str | None  # last bar date; None when no price was stored
    close: float | None  # as printed
    provisional: bool
    status: str  # a range status, or no_prices | error
    band_pct: float | None
    band_lo: float | None  # thousand VND
    band_hi: float | None
    calibrated: bool | None
    model_version: str | None
    refreshed: bool
    schema: int = SCHEMA


@dataclass(frozen=True)
class LogRead:
    entries: tuple[IssuedEntry, ...]  # latest per (ticker, as_of, provisional), ascending by as_of
    skipped: int  # lines that were not usable

    def for_ticker(self, ticker: str) -> tuple[IssuedEntry, ...]:
        return tuple(entry for entry in self.entries if entry.ticker == ticker)

    def previous_issued_at(self, ticker: str, before: str | None = None) -> str | None:
        """When the ticker was last issued, among entries whose bar is strictly before `before` (all if None)."""
        stamps = [
            e.issued_at for e in self.for_ticker(ticker) if before is None or (e.as_of is not None and e.as_of < before)
        ]
        return max(stamps, default=None)


def issued_log_path(holdings_path: Path) -> Path:
    return holdings_path.parent / LOG_FILE_NAME


def append_entries(path: Path, entries: tuple[IssuedEntry, ...], *, uid: int | None = None) -> None:
    """Append one line per entry in a single write; the file is ours, regular, mode 600, flushed to disk."""
    payload = "".join(json.dumps(asdict(entry), ensure_ascii=True) + "\n" for entry in entries).encode("ascii")
    flags = os.O_APPEND | os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        descriptor = os.open(path, flags, LOG_MODE)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != (os.getuid() if uid is None else uid):
                raise IssuedLogError(f"the issued-brief log {path} could not be appended to: not a regular file of yours")
            os.fchmod(descriptor, LOG_MODE)
            if info.st_size and os.pread(descriptor, 1, info.st_size - 1) != b"\n":
                payload = b"\n" + payload  # a torn last line must not swallow the first new entry
            if os.write(descriptor, payload) != len(payload):
                raise OSError("short write")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise IssuedLogError(f"the issued-brief log {path} could not be appended to ({type(error).__name__})") from None


def read_log(path: Path) -> LogRead:
    """Every usable line; an absent file is an empty log."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return LogRead((), 0)
    except OSError:
        return LogRead((), 1)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return LogRead((), 1)
        chunks = []
        while chunk := os.read(descriptor, 1 << 20):
            chunks.append(chunk)
    except OSError:
        return LogRead((), 1)
    finally:
        os.close(descriptor)
    latest: dict[tuple[str, str | None, bool], tuple[int, IssuedEntry]] = {}
    skipped = 0
    for number, raw in enumerate(b"".join(chunks).split(b"\n")):  # not str.splitlines: U+2028 and U+0085 do not end a line here
        line = raw.decode("utf-8", errors="replace")
        if not line.strip():
            continue
        entry = _parse_line(line)
        if entry is None:
            skipped += 1
            continue
        key = (entry.ticker, entry.as_of, entry.provisional)
        held = latest.get(key)
        if held is not None and entry.band_pct is None and held[1].band_pct is not None:
            continue  # a degraded re-run must not replace a good entry
        latest[key] = (number, entry)
    ordered = sorted(latest.values(), key=lambda item: (item[1].as_of or "", item[0]))
    return LogRead(tuple(entry for _, entry in ordered), skipped)


def _parse_line(line: str) -> IssuedEntry | None:
    try:
        raw = json.loads(line)
        if not isinstance(raw, dict) or not {"ticker", "as_of", "status"} <= raw.keys():
            return None
        return IssuedEntry(
            issued_at=_checked(raw.get("issued_at", ""), _TIMESTAMP), ticker=_checked(raw["ticker"], TICKER_PATTERN),
            as_of=_checked_or_none(raw["as_of"], _DATE), close=_number_or_none(raw.get("close")),
            provisional=bool(raw.get("provisional", False)), status=_checked(raw["status"], _STATUS),
            band_pct=_number_or_none(raw.get("band_pct")), band_lo=_number_or_none(raw.get("band_lo")),
            band_hi=_number_or_none(raw.get("band_hi")), calibrated=_bool_or_none(raw.get("calibrated")),
            model_version=_checked_or_none(raw.get("model_version"), _VERSION),
            refreshed=bool(raw.get("refreshed", False)), schema=int(raw.get("schema", SCHEMA)),
        )
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        return None


def _checked(value: object, pattern: re.Pattern) -> str:
    """A string read back from the log must match its pattern, so no escape sequence can reach the brief."""
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise TypeError("unexpected text")
    return value


def _checked_or_none(value: object, pattern: re.Pattern) -> str | None:
    return None if value is None else _checked(value, pattern)


def _number_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("expected a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("not finite")
    return number


def _bool_or_none(value: object) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError("expected a boolean")
    return value
