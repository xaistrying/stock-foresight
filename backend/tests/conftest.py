"""Install the vnstock/vnai guard before any test module is imported.

pytest imports `conftest.py` ahead of the test modules it collects, so this is
the earliest hook available — and it has to be earlier than
`test_ticker_ingestion.py`'s own top-level `from vnstock.core.exceptions
import RateLimitError`, which would otherwise trigger vnai's AI-config writes
during collection. That is exactly how the issue in `docs/KNOWN_ISSUES.md` was
originally found: `AGENTS.md` reappearing after every `pytest backend/tests`.
"""

from app.vnstock_guard import install as _install_vnstock_guard

_install_vnstock_guard()
