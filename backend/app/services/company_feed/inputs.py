"""What a snapshot run starts from: which tickers, and whether a vendor API key is in play.

No vendor import: ticker syntax is checked by `fetch.parse_ticker`'s rule, restated here so this module
stays importable without the vendor library.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from app.db import debate_log
from app.db.connection import open_readonly

logger = logging.getLogger(__name__)

API_KEY_ENV_VAR = "VNSTOCK_API_KEY"
API_KEY_FILE = Path(".vnstock") / "api_key.json"

_TICKER = re.compile(r"[A-Z0-9]{1,12}")  # the same rule as `fetch.parse_ticker`; a test keeps them equal


def parse_ticker_list(text: str) -> tuple[str, ...]:
    """`"SAB, vpb"` -> `("SAB", "VPB")`: upper-cased, de-duplicated in order. A symbol that is not a plain
    ticker raises `ValueError` (it would end up in a vendor URL)."""
    symbols: dict[str, None] = {}
    for part in text.split(","):
        symbol = part.strip().upper()
        if not symbol:
            continue
        if not _TICKER.fullmatch(symbol):
            raise ValueError(f"not a plain ticker: {part.strip()!r}")
        symbols[symbol] = None
    return tuple(symbols)


def tickers_from_debate_log(path: Path | None = None) -> tuple[str, ...]:
    """The distinct tickers in `debate_log`, opened read-only. A missing file, or one without the table,
    gives none. A stored value that is not a plain ticker is skipped with a warning."""
    log_path = path or debate_log.DEBATE_LOG_DB_PATH
    if not log_path.exists():
        return ()
    conn = open_readonly(log_path)
    try:
        rows = conn.execute("SELECT DISTINCT ticker FROM debate_log ORDER BY ticker").fetchall()
    except sqlite3.OperationalError as error:
        if "no such table" in str(error):
            return ()
        raise
    finally:
        conn.close()
    tickers = []
    for (value,) in rows:
        if isinstance(value, str) and _TICKER.fullmatch(value):
            tickers.append(value)
        else:
            logger.warning("Skipping a debate-log ticker that is not a plain symbol")
    return tuple(tickers)


def merge_tickers(*groups: Iterable[str]) -> tuple[str, ...]:
    """Every ticker once, in the order first given."""
    return tuple(dict.fromkeys(ticker for group in groups for ticker in group))


def api_key_warnings(env: Mapping[str, str] | None = None, home: Path | None = None) -> tuple[str, ...]:
    """Warnings for a vendor API key that is present. The company feed runs on the guest tier and never
    sets, reads, stores or logs a key: this checks existence only (the variable's presence, the key
    file's existence) and never opens the file or repeats a value. It does not refuse to run: a
    registered key is the owner's call. Whether the guard covers vnai's key-gated paths is unverified."""
    environment = os.environ if env is None else env
    key_file = (home if home is not None else Path.home()) / API_KEY_FILE
    present = []
    if API_KEY_ENV_VAR in environment:
        present.append(f"the environment variable {API_KEY_ENV_VAR} is set")
    if key_file.exists():
        present.append(f"the key file {Path('~') / API_KEY_FILE} exists")
    if not present:
        return ()
    return (
        "A vnstock API key is in play ("
        + "; ".join(present)
        + "): vnai's key-gated paths are used, and whether the guard covers them is unverified. "
        "The company feed is meant to run without a key.",
    )
