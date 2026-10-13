"""Whether a share issue is small or material, in one place (`add-announcement-tags-and-insider-sizing`).

An issue's ratio is "new shares per share held" (0.01 is 1% of the shares). The rules are shared by the
listing (small issues are counted, not listed), the size withhold rule and the benchmark's comparable period.
They are policy values, not thresholds on a price move (Rule 3 is not engaged: they measure a share-count change).
"""

from __future__ import annotations

import math
from datetime import date
from typing import Protocol

# Policy constant, resting on one example: the owner accepted 1% on 2026-10-12. Stored employee issues are
# 0.1% to 0.5% each; the larger ones are bonus, stock-dividend, rights and placement issues.
ISSUE_MATERIAL_RATIO = 0.01


class _Issue(Protocol):
    @property
    def issue_class(self) -> object: ...
    @property
    def exercise_ratio(self) -> float | None: ...
    @property
    def exright_date(self) -> date | None: ...
    @property
    def record_date(self) -> date | None: ...
    @property
    def published_at(self) -> date | None: ...


def class_name(issue: _Issue) -> str:
    """The issue class name; an issue without one is OTHER (the adapter sets a class on every ISS row)."""
    return issue.issue_class.name if issue.issue_class is not None else "OTHER"


def ratio_known(issue: _Issue) -> bool:
    ratio = issue.exercise_ratio
    return ratio is not None and math.isfinite(ratio) and ratio > 0


def is_small(issue: _Issue) -> bool:
    """A known ratio below `ISSUE_MATERIAL_RATIO` in any class, or an employee issue with a missing or zero ratio."""
    if ratio_known(issue):
        return issue.exercise_ratio < ISSUE_MATERIAL_RATIO
    return class_name(issue) == "EMPLOYEE"


def is_material(issue: _Issue) -> bool:
    """1% or more in any class, or a non-employee issue of unknown size."""
    return not is_small(issue)


def issue_date(issue: _Issue) -> date | None:
    """The date the issue counts from: ex-rights date, else record date, else publication date."""
    return issue.exright_date or issue.record_date or issue.published_at
