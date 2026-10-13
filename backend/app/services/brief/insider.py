"""A registered trade of a major shareholder or insider, read from the stored record (`add-announcement-tags-and-insider-sizing`).

Pure. The title shape is `<name> - Đăng kí Bán|Mua [<quantity>] <TICKER>`; the window comes from the record's start
and end dates and is compared with the brief's last-bar date, calendar days only (there is no trading calendar). The
direction shown is taken from the record's action field through a closed set and is used only when it agrees with the
title and the title's ticker is the held ticker. The event code's class (individual, institution, related person) is
not read: the library documents the three codes only as a group. Nothing here says what the record does not say: the
record gives no execution status.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from app.services.brief.feed_source import Announcement

TRADE_TITLE = re.compile(r"^(?P<name>.+) - Đăng k[íý] (?P<act>Mua|Bán)(?: (?P<qty>[\d,]+))? (?P<tk>[A-Z0-9]+)$")
# The vendor's action field to the title's word and to the noun the brief uses (no buy, sell or hold word in tool text).
_DIRECTIONS = {"Sell": ("Bán", "sale"), "Buy": ("Mua", "purchase")}
BRIEF_COVERS_DAYS = 7  # calendar days: the brief covers one week
_MAX_QUANTITY = 10**13  # above any share count; a larger number in a title is not read as a quantity


class WindowStatus(Enum):
    NOT_STARTED = "not started"
    UNDER_WAY = "under way"
    ENDED = "ended"
    UNKNOWN = "unknown"  # a date is missing


@dataclass(frozen=True)
class Trade:
    item: Announcement
    name: str | None  # raw text before " - Đăng kí"; shown only through the sanitiser
    direction: str | None  # "sale" or "purchase"; None when it cannot be read or disagrees
    quantity: int | None
    start: date | None
    end: date | None
    status: WindowStatus

    @property
    def weeks(self) -> int | None:
        """The window length in weeks, rounded up, when both dates are given."""
        if self.start is None or self.end is None or self.end < self.start:
            return None
        return math.ceil(((self.end - self.start).days + 1) / 7)

    def extends_past(self, as_of: date) -> bool:
        """The window ends more than one brief's span after the last bar."""
        return self.end is not None and self.end > as_of + timedelta(days=BRIEF_COVERS_DAYS)


def window_status(start: date | None, end: date | None, as_of: date) -> WindowStatus:
    if start is None or end is None:
        return WindowStatus.UNKNOWN
    if start > as_of:
        return WindowStatus.NOT_STARTED
    return WindowStatus.UNDER_WAY if end >= as_of else WindowStatus.ENDED


def parse_trade(item: Announcement, ticker: str, as_of: date) -> Trade:
    """The trade a record describes; `direction` and `quantity` are None when the title cannot be trusted."""
    status = window_status(item.start_date, item.end_date, as_of)
    common = dict(item=item, start=item.start_date, end=item.end_date, status=status)
    match = TRADE_TITLE.match(unicodedata.normalize("NFC", item.title.strip()))
    if match is None:
        return Trade(name=None, direction=None, quantity=None, **common)
    word, noun = _DIRECTIONS.get(item.action_type_en or "", (None, None))
    if match["act"] != word or match["tk"] != ticker:
        return Trade(name=match["name"], direction=None, quantity=None, **common)
    return Trade(name=match["name"], direction=noun, quantity=_quantity(match["qty"]), **common)


def _quantity(text: str | None) -> int | None:
    digits = (text or "").replace(",", "")
    if not digits.isdigit():
        return None
    value = int(digits)
    return value if 0 < value < _MAX_QUANTITY else None


def window_is_open(item: Announcement, as_of: date) -> bool:
    """The window has not ended (not started, or under way): a trade like this stays listed. A missing date is not open."""
    return window_status(item.start_date, item.end_date, as_of) in (WindowStatus.NOT_STARTED, WindowStatus.UNDER_WAY)
