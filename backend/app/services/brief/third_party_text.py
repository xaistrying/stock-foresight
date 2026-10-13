"""The one sanitiser for text the brief shows but did not write: stored announcement titles and counterparty names.

Third-party text is shown in its original language, bounded and neutralised, inside U+201C and U+201D, under a
label that says it is third-party text (Rule 5). The two quote characters are removed from the input, so a
source cannot close its own span, invisible characters are removed and look-alike quotation marks become an
apostrophe; the brief's text guard (Rule 6) exempts only what sits inside such a span and no constant tool string
contains either character. Nothing here translates, summarises or rewords, and no
language model is called. Emphasis characters (`*`, `_`, `#`) are left alone: they change appearance, not structure.
"""

from __future__ import annotations

import re

from app.services.debate.news_feeds import _clean  # one definition of "clean"; a rename there fails a test here

OPEN, CLOSE = "“", "”"
TITLE_LIMIT, NAME_LIMIT = 200, 120
ELLIPSIS = "…"
LINK_REMOVED = "(link removed)"
_RAW_LIMIT = 4000  # `_clean` cuts first; the replacements below can lengthen a text, and the real cap follows them
_LINK = re.compile(r"https?://\S*", re.IGNORECASE)
# Characters `_clean` leaves in place that render as nothing (default-ignorable fillers, joiners and variation selectors): a
# title could use them to hide where a word or a delimiter begins. Marks that Vietnamese and other scripts need are kept.
_INVISIBLE = (
    [0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x2800, 0x3164, 0xFFA0]
    + list(range(0x180B, 0x1810)) + list(range(0xFE00, 0xFE10)) + list(range(0xE0100, 0xE01F0))
)
# Quotation marks that look like a closing quote become a plain apostrophe, so nothing inside a span can pass for its end.
_QUOTE_LOOKALIKES = [0x22, 0x201E, 0x201F, 0x2033, 0xFF02, 0x00AB, 0x00BB, *range(0x300C, 0x3010)]
_REPLACEMENTS = str.maketrans({
    OPEN: "", CLOSE: "", "|": "/", "`": "'", "<": "‹", ">": "›", "[": "(", "]": ")",
    **{code: None for code in _INVISIBLE}, **{code: "'" for code in _QUOTE_LOOKALIKES},
})
_SPAN = re.compile(f"{OPEN}([^{OPEN}{CLOSE}]*){CLOSE}")


def third_party(text: str | None, limit: int = TITLE_LIMIT) -> str:
    """`text` sanitised, cut to `limit` characters (plus an ellipsis) and wrapped as one third-party span."""
    cleaned = _LINK.sub(LINK_REMOVED, _clean(text, _RAW_LIMIT))
    cleaned = " ".join(cleaned.translate(_REPLACEMENTS).split())
    if len(cleaned) > limit:
        cleaned = cleaned[:limit].rstrip() + ELLIPSIS
    return f"{OPEN}{cleaned}{CLOSE}"


def spans(line: str) -> list[str]:
    """The contents of every well-formed third-party span in `line`, in order."""
    return _SPAN.findall(line)


def strip_spans(line: str) -> str:
    """`line` with every well-formed span (quotes included) removed: what the text guard scans."""
    return _SPAN.sub("", line)
