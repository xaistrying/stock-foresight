"""Keyword classes for company filings (`add-announcement-tags-and-insider-sizing`), as data.

A class is ENABLED in `ENABLED_KEYWORD_CLASSES` only when a labelled accuracy check on stored titles shows that every
title it claims is correctly labelled and that it claims at least 3 (design Decision 2, task 2.4). On 2026-10-13 the
check passed for capital, meeting and personnel and failed for dividend and results (counts in the change's design). Functions take the enabled set as a parameter so tests can switch a class on. Matching is on
NFC, casefolded, whitespace-collapsed text, with no stemming. The phrases are written here by the author, not
copied from stored titles.

A title that mentions a bond, a penalty or a transfer restriction is never matched by any class: those notices
carry real transactions or obligations that a keyword class would misread.
"""

from __future__ import annotations

import unicodedata

CAPITAL, DIVIDEND, MEETING, RESULTS, PERSONNEL = "capital", "dividend", "meeting", "results", "personnel"

# Counts per class are recorded in the change's design. The labels were written by an AI model at the owner's request,
# not by the owner (the labels file stays outside the repository), so spot-check before relying on them. Dividend (2
# stock-dividend titles claimed) and results (9 audit-engagement notices claimed) stay disabled.
ENABLED_KEYWORD_CLASSES: frozenset[str] = frozenset({CAPITAL, MEETING, PERSONNEL})

KEYWORDS: dict[str, tuple[str, ...]] = {
    CAPITAL: (
        "phát hành cổ phiếu", "cổ phiếu thưởng", "tăng vốn điều lệ", "tăng vốn", "quyền mua cổ phiếu", "chào bán cổ phiếu",
        "hoán đổi cổ phiếu", "niêm yết bổ sung", "cổ tức bằng cổ phiếu",
    ),
    DIVIDEND: ("cổ tức", "tạm ứng cổ tức", "chi trả cổ tức"),
    MEETING: ("đại hội đồng cổ đông", "đhđcđ", "họp cổ đông"),
    RESULTS: ("báo cáo tài chính", "bctc", "kết quả kinh doanh", "kết quả hoạt động kinh doanh"),
    PERSONNEL: ("bổ nhiệm", "miễn nhiệm", "từ nhiệm", "người công bố thông tin", "người phụ trách quản trị"),
}
# A title containing any of these is never classified: bond issues and buy-backs, penalty notices, transfer restrictions.
NEVER_MATCH: tuple[str, ...] = ("trái phiếu", "xử phạt", "bị phạt", "hạn chế chuyển nhượng")


def fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def matching_classes(title: str, enabled: frozenset[str] = ENABLED_KEYWORD_CLASSES) -> tuple[str, ...]:
    """The enabled classes whose phrases occur in `title`; none when the title holds a never-match phrase."""
    folded = fold(title)
    if any(fold(phrase) in folded for phrase in NEVER_MATCH):
        return ()
    return tuple(name for name in KEYWORDS if name in enabled and any(fold(p) in folded for p in KEYWORDS[name]))
