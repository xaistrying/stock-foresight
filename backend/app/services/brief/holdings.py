"""The investor's holdings file: parsing, validation and the refusals that keep it private.

TOML, standard-library `tomllib` only. The file lives outside the repository and is read only when
it is a regular file, owned by the current user, with no group or world permission bit. Error
messages name the entry and the field and never carry a share count or a cost.
"""

from __future__ import annotations

import math
import os
import re
import stat
import tomllib
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app.services.brief.timing import ict_now

TICKER_PATTERN = re.compile(r"[A-Z0-9]{1,12}")  # the same rule as the feed parser; a test keeps them equal
COMPARATORS = ("below", "above")
LEVEL_TEXT_MAX = 300
CONFIG_SUBDIRECTORY = "stock-foresight"
HOLDINGS_FILE_NAME = "holdings.toml"
_PRIVATE_MASK = 0o077
_WRITABLE_MASK = 0o022
MAX_FILE_BYTES = 256 * 1024
MAX_HOLDINGS = 200
MAX_LEVELS_PER_HOLDING = 50
MAX_SHARES = 10**12
_HOLDING_KEYS = frozenset({"ticker", "shares", "cost", "purchase_date", "shares_as_of", "levels"})
_LEVEL_KEYS = frozenset({"comparator", "price", "entered", "text"})
# Unicode categories that can hide or reorder text: control, format, surrogate, private use, unassigned, line and paragraph separators.
_FORBIDDEN_TEXT_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


class HoldingsError(Exception):
    """The holdings file cannot be used. The message never carries a share count or a cost."""


@dataclass(frozen=True)
class Level:
    """A price level the investor wrote, with their own words and the day they wrote it."""

    comparator: str  # "below" | "above"
    price: float  # thousand VND per share
    entered: date
    text: str


@dataclass(frozen=True)
class Holding:
    ticker: str
    shares: int
    cost: float  # per share, thousand VND, as on the board
    purchase_date: date | None
    shares_as_of: date | None
    levels: tuple[Level, ...] = ()


def default_holdings_path(environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """`<XDG_CONFIG_HOME or ~/.config>/stock-foresight/holdings.toml`."""
    environ = os.environ if environ is None else environ
    config_dir = environ.get("XDG_CONFIG_HOME") or str((home or Path.home()) / ".config")
    return Path(config_dir) / CONFIG_SUBDIRECTORY / HOLDINGS_FILE_NAME


def directory_warnings(path: Path) -> tuple[str, ...]:
    """Warnings, not refusals: a folder open to read, or sitting inside a git working tree."""
    resolved = path.resolve()
    warnings: list[str] = []
    try:
        if resolved.parent.stat().st_mode & _PRIVATE_MASK:
            warnings.append(f"the directory {resolved.parent} is accessible to other users; consider chmod 700 on it")
    except OSError:
        pass
    for parent in resolved.parents:
        if (parent / ".git").exists():
            warnings.append(f"{parent} is a git working tree; keep the holdings file and the log out of it")
            break
    return tuple(warnings)


def load_holdings(
    path: Path, *, repo_root: Path, today: date | None = None, uid: int | None = None,
) -> tuple[Holding, ...]:
    """Read and validate the file at `path`, or raise `HoldingsError` before anything else happens."""
    today = today or ict_now(datetime.now(timezone.utc)).date()
    resolved = path.resolve()
    if resolved.is_relative_to(repo_root.resolve()):
        raise HoldingsError(f"the holdings file is inside the repository ({path}); keep it outside, for example at {default_holdings_path()}")
    data = _read_private_file(path, resolved, os.getuid() if uid is None else uid)
    try:
        raw = tomllib.loads(data.decode("utf-8"))
    except tomllib.TOMLDecodeError as error:
        position = re.search(r"\(at line \d+, column \d+\)", str(error))
        raise HoldingsError(f"the holdings file is not valid TOML {position.group(0) if position else ''}".strip()) from None
    except (UnicodeDecodeError, RecursionError, ValueError, OverflowError):
        raise HoldingsError("the holdings file could not be parsed (not valid UTF-8 TOML, or too deeply nested)") from None

    entries = raw.get("holdings")
    if not isinstance(entries, list) or not entries:
        raise HoldingsError("the holdings file has no holdings: add at least one [[holdings]] entry")
    if len(entries) > MAX_HOLDINGS:
        raise HoldingsError(f"the holdings file lists more than {MAX_HOLDINGS} holdings")
    try:
        holdings = tuple(_parse_holding(index, entry, today) for index, entry in enumerate(entries, start=1))
    except (RecursionError, ValueError, OverflowError):
        raise HoldingsError("the holdings file has a value that could not be read") from None
    tickers = [holding.ticker for holding in holdings]
    for ticker in sorted(set(tickers)):
        if tickers.count(ticker) > 1:
            raise HoldingsError(f"ticker {ticker} is listed more than once")
    return holdings


def _read_private_file(path: Path, resolved: Path, uid: int) -> bytes:
    """Open once (no symlink at the final component), check the descriptor, read from that descriptor."""
    parent = resolved.parent
    try:
        parent_mode = parent.stat().st_mode
    except FileNotFoundError:
        raise HoldingsError(f"no holdings file at {path}") from None
    if parent_mode & _WRITABLE_MASK:
        raise HoldingsError(f"the directory {parent} can be written by other users; run: chmod 700 {parent}")
    try:
        descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        raise HoldingsError(f"no holdings file at {path}") from None
    except OSError as error:
        raise HoldingsError(f"{path} could not be opened ({type(error).__name__})") from None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise HoldingsError(f"{path} is not a regular file")
        if info.st_uid != uid:
            raise HoldingsError(f"{path} is owned by another user")
        if info.st_mode & _PRIVATE_MASK:
            raise HoldingsError(f"{path} can be read by other users; run: chmod 600 {path}")
        if info.st_size > MAX_FILE_BYTES:
            raise HoldingsError(f"{path} is larger than {MAX_FILE_BYTES // 1024} KiB")
        chunks, total = [], 0
        while chunk := os.read(descriptor, 65536):
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise HoldingsError(f"{path} is larger than {MAX_FILE_BYTES // 1024} KiB")
        return b"".join(chunks)
    except OSError as error:
        raise HoldingsError(f"{path} could not be read ({type(error).__name__})") from None
    finally:
        os.close(descriptor)


def _parse_holding(index: int, entry: object, today: date) -> Holding:
    if not isinstance(entry, dict):
        raise HoldingsError(f"holdings entry {index} is not a table")
    ticker = entry.get("ticker")
    label = f"holdings entry {index}" + (f" ({ticker})" if isinstance(ticker, str) and TICKER_PATTERN.fullmatch(ticker) else "")
    if not (isinstance(ticker, str) and TICKER_PATTERN.fullmatch(ticker)):
        raise HoldingsError(f"{label}: field ticker must be 1 to 12 capital letters or digits")
    _reject_unknown_keys(entry, _HOLDING_KEYS, label)
    shares = entry.get("shares")
    if not _is_int(shares) or not 0 < shares <= MAX_SHARES:
        raise HoldingsError(f"{label}: field shares must be a positive whole number of at most {MAX_SHARES:,}")
    cost = _positive_number(entry.get("cost"))
    if cost is None:
        raise HoldingsError(f"{label}: field cost must be a positive number")
    purchase_date = _optional_date(entry, "purchase_date", label, today)
    shares_as_of = _optional_date(entry, "shares_as_of", label, today) or purchase_date  # defaults to purchase_date
    raw_levels = entry.get("levels", [])
    if not isinstance(raw_levels, list):
        raise HoldingsError(f"{label}: field levels must be a list of [[holdings.levels]] tables")
    if len(raw_levels) > MAX_LEVELS_PER_HOLDING:
        raise HoldingsError(f"{label}: more than {MAX_LEVELS_PER_HOLDING} levels")
    levels = tuple(_parse_level(label, n, raw, today) for n, raw in enumerate(raw_levels, start=1))
    return Holding(ticker, shares, cost, purchase_date, shares_as_of, levels)


def _parse_level(label: str, number: int, raw: object, today: date) -> Level:
    where = f"{label}, level {number}"
    if not isinstance(raw, dict):
        raise HoldingsError(f"{where} is not a table")
    _reject_unknown_keys(raw, _LEVEL_KEYS, where)
    comparator = raw.get("comparator")
    if comparator not in COMPARATORS:
        raise HoldingsError(f'{where}: field comparator must be "below" or "above"')
    price = _positive_number(raw.get("price"))
    if price is None:
        raise HoldingsError(f"{where}: field price must be a positive number")
    entered = _optional_date(raw, "entered", where, today)
    if entered is None:
        raise HoldingsError(f"{where}: field entered is required (a date)")
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HoldingsError(f"{where}: field text must be a non-empty line")
    if len(text) > LEVEL_TEXT_MAX:
        raise HoldingsError(f"{where}: field text is longer than {LEVEL_TEXT_MAX} characters")
    if any(ord(char) < 32 or ord(char) == 127 or unicodedata.category(char) in _FORBIDDEN_TEXT_CATEGORIES for char in text):
        raise HoldingsError(f"{where}: field text must be one line of visible characters (no control, format or separator characters)")
    return Level(comparator, price, entered, text)


def _reject_unknown_keys(table: dict, allowed: frozenset[str], where: str) -> None:
    for key in table:
        if key not in allowed:
            raise HoldingsError(f'{where}: unknown field "{str(key)[:40]}" (a typo would silently drop a value)')


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _optional_date(table: dict, field: str, where: str, today: date) -> date | None:
    if field not in table:
        return None
    value = table[field]
    if isinstance(value, datetime):
        parsed = None
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            parsed = None
    else:
        parsed = None
    if parsed is None:
        raise HoldingsError(f"{where}: field {field} must be a date (YYYY-MM-DD)")
    if parsed > today:
        raise HoldingsError(f"{where}: field {field} is in the future")
    return parsed
