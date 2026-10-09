"""Turn vendor frames and feed items into storable records: clean, identify, hash.

Pure (pandas and numpy only): it imports no `vnstock` module, directly or through another
repository module, so it can be tested and used without the vendor library.

"Stored as fetched" means not translated, not summarised, not re-worded: markup, control
characters and length are the only changes. The cleaned form is the only form kept.
Titles keep their original language; no language-model call exists anywhere in this package.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable

import numpy as np
import pandas as pd

from app.services.debate.news_feeds import _clean as clean_text  # one definition of "clean"; a rename there fails a test here

# New and operational (design Decision 13): a bound against a hostile oversized value, not a
# design target and not a threshold on a price move. The debate's 200-character prompt budget
# (`news_feeds.TITLE_MAX`) is not borrowed because this log is not a prompt.
COMPANY_TITLE_MAX = 500
COMPANY_FIELD_MAX = 200

KIND_NEWS = "news"
KIND_EVENTS = "events"
KIND_RSS = "rss"
VENDOR_KINDS = (KIND_NEWS, KIND_EVENTS)

_IDENTITY_HASH_HEX = 16


class UnexpectedFrame(ValueError):
    """A non-empty vendor frame lacks a column this module needs: the vendor changed, which is
    not the same thing as a quiet ticker."""


@dataclass(frozen=True)
class FrameSpec:
    """The columns of one vendor frame kind, fixed from a live VCI frame (tasks.md 4.1, SAB,
    2026-10-09). A column that is not listed here is not stored."""

    kind: str
    title_column: str
    published_column: str
    required_columns: tuple[str, ...]
    identity_columns: tuple[str, ...]  # beyond the published date and the title
    field_columns: tuple[str, ...]  # stored in `fields` (the title and the date have their own columns)
    body_columns: tuple[str, ...]  # never stored; a non-empty value is reported


NEWS_SPEC = FrameSpec(
    kind=KIND_NEWS,
    title_column="news_title",
    published_column="public_date",
    required_columns=("news_title", "public_date"),
    identity_columns=(),
    field_columns=("news_source", "news_source_link", "news_author"),
    body_columns=("news_full_content", "news_short_content"),
)
EVENTS_SPEC = FrameSpec(
    kind=KIND_EVENTS,
    title_column="event_title_vi",
    published_column="public_date",
    required_columns=("event_code", "event_title_vi", "public_date"),
    identity_columns=("event_code",),
    field_columns=(
        "event_code", "category", "display_date1", "display_date2", "record_date", "exright_date",
        "payout_date", "issue_date", "listing_date", "start_date", "end_date", "value_per_share",
        "exercise_ratio", "action_type_vi", "action_type_en",
    ),
    body_columns=(),
)
SPECS = {KIND_NEWS: NEWS_SPEC, KIND_EVENTS: EVENTS_SPEC}


@dataclass(frozen=True)
class ItemRecord:
    kind: str
    ticker: str
    source: str
    item_id: str
    content_hash: str
    published_at: str | None
    title: str | None
    fields_json: str


@dataclass(frozen=True)
class NormalisedFrame:
    records: tuple[ItemRecord, ...]
    skipped_cells: int = 0
    body_columns_filled: tuple[str, ...] = ()


_SKIP = object()
_NON_SCALAR = (list, tuple, set, frozenset, dict, bytes, bytearray, np.ndarray)


def _is_missing(value: Any) -> bool:
    return value is None or value is pd.NaT or value is pd.NA or (isinstance(value, float) and math.isnan(value))


def _scalar(value: Any) -> Any:
    """A JSON-safe plain value, `None` for a missing one, `_SKIP` for a cell that is not a scalar.
    NaN, NaT and numpy scalars never reach the JSON encoder."""
    if _is_missing(value):
        return None
    if isinstance(value, _NON_SCALAR):
        return _SKIP
    if isinstance(value, str):
        return clean_text(value, COMPANY_FIELD_MAX) or None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (datetime, date)):  # pd.Timestamp is a datetime
        return value.isoformat()
    return _SKIP


def _title(value: Any) -> str | None:
    """A title keeps the longer title cap; any other string field is capped at `COMPANY_FIELD_MAX`."""
    if _is_missing(value):
        return None
    return clean_text(value if isinstance(value, str) else str(value), COMPANY_TITLE_MAX) or None


def _is_filled(value: Any) -> bool:
    """Whether a cell holds anything, for the body-column warning (a blank string is empty)."""
    if _is_missing(value):
        return False
    return not isinstance(value, str) or bool(clean_text(value, 1))


def _published_at(value: Any) -> str | None:
    """The item's own date as the source gave it, in ISO-8601 with no timezone shifting.
    A date with a time keeps its time; a bare date stays a bare date; text that is not ISO
    is kept as it came (cleaned), never dropped."""
    scalar = _scalar(value)
    if scalar is None or scalar is _SKIP:
        return None
    if not isinstance(scalar, str):
        return str(scalar)
    try:
        parsed = datetime.fromisoformat(scalar)
    except ValueError:
        return scalar
    return parsed.isoformat() if len(scalar) > len("YYYY-MM-DD") else parsed.date().isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _build_record(
    *, kind: str, ticker: str, source: str, published_at: str | None, title: str | None,
    identity_extra: tuple[Any, ...], fields: dict[str, Any],
) -> ItemRecord:
    """`item_id` hashes only what identifies the item, so a field the vendor can revise later
    changes `content_hash` but not `item_id`: a new version of the same item, never a duplicate."""
    item_id = _digest([kind, ticker, source, published_at, title, *identity_extra])[:_IDENTITY_HASH_HEX]
    content_hash = _digest([kind, ticker, source, published_at, title, fields])
    return ItemRecord(
        kind=kind, ticker=ticker, source=source, item_id=item_id, content_hash=content_hash,
        published_at=published_at, title=title, fields_json=_canonical_json(fields),
    )


def _unique(records: Iterable[ItemRecord]) -> tuple[ItemRecord, ...]:
    seen: set[tuple[str, str]] = set()
    unique: list[ItemRecord] = []
    for record in records:
        key = (record.item_id, record.content_hash)
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return tuple(unique)


def spec_for(kind: str) -> FrameSpec:
    try:
        return SPECS[kind]
    except KeyError:
        raise ValueError(f"unknown vendor kind {kind!r}; expected one of {VENDOR_KINDS}") from None


def require_columns(frame: pd.DataFrame, kind: str) -> None:
    """Raise `UnexpectedFrame` for a non-empty frame without a required column. An empty frame
    is a normal answer for a quiet ticker and needs no columns."""
    spec = spec_for(kind)
    if frame.empty:
        return
    missing = [column for column in spec.required_columns if column not in frame.columns]
    if missing:
        raise UnexpectedFrame(f"{kind} frame is missing required column(s): {', '.join(missing)}")


def frame_to_records(frame: pd.DataFrame, *, kind: str, ticker: str, source: str) -> NormalisedFrame:
    """Records for the rows of one VCI frame, stored under the requested `ticker` (the news frame's
    own ticker column is empty). Rows that repeat within a frame give one record."""
    spec = spec_for(kind)
    require_columns(frame, kind)
    if frame.empty:
        return NormalisedFrame(records=())

    body_filled = tuple(
        column for column in spec.body_columns
        if column in frame.columns and any(_is_filled(value) for value in frame[column])
    )
    skipped = 0
    records: list[ItemRecord] = []
    for row in frame.to_dict(orient="records"):
        title = _title(row[spec.title_column])
        fields: dict[str, Any] = {}
        for column in spec.field_columns:
            if column not in row:
                continue
            value = _scalar(row[column])
            if value is _SKIP:
                skipped += 1
            else:
                fields[column] = value
        published_at = _published_at(row[spec.published_column])
        identity_extra = tuple(_scalar(row[column]) for column in spec.identity_columns)
        records.append(_build_record(
            kind=kind, ticker=ticker, source=source, published_at=published_at, title=title,
            identity_extra=identity_extra, fields=fields,
        ))
    return NormalisedFrame(records=_unique(records), skipped_cells=skipped, body_columns_filled=body_filled)


def rss_items_to_records(items: Iterable[tuple[datetime, str, str]], *, source: str) -> NormalisedFrame:
    """Records for the `(published, title, snippet)` tuples `news_feeds._fetch_feed` returns.

    They are stored as that function returns them (already cleaned there), i.e. as the News agent
    would have seen them: a second `_clean` could differ on a double-escaped title. Not filtered by
    ticker, sector or age. `published_at` is UTC; `ticker` is empty (a feed has none).
    """
    records = []
    for published, title, snippet in items:
        records.append(_build_record(
            kind=KIND_RSS, ticker="", source=source,
            published_at=published.astimezone(timezone.utc).isoformat(), title=title or None,
            identity_extra=(), fields={"snippet": snippet or None},
        ))
    return NormalisedFrame(records=_unique(records))
