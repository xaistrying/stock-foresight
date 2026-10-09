"""Tests for `backend/scripts/evaluate_fibonacci_levels.py`.

The script lives under `backend/scripts/`, which is not a package, so it is loaded by path
(the precedent in `test_evaluate_cross_sectional_momentum.py`).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("evaluate_fibonacci_levels", BACKEND / "scripts" / "evaluate_fibonacci_levels.py")
ef = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ef)


def _wave(seed: int = 3, n: int = 400) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A trending-and-reversing close series with a high/low a little around it."""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, n) + 0.004 * np.sin(np.arange(n) / 15)))
    return close * 1.004, close * 0.996, close


def test_a_pivot_is_confirmed_after_it_occurs():
    high, low, close = _wave()
    sigma = np.full(len(close), 0.012)

    pivots = ef.zigzag(high, low, sigma, 4)

    assert pivots
    assert all(confirm > bar for bar, _, _, confirm in pivots)


def test_the_zigzag_never_uses_data_after_the_confirmation_bar():
    high, low, close = _wave()
    sigma = np.full(len(close), 0.012)
    full = ef.zigzag(high, low, sigma, 4)

    for cut in (150, 250, 399):
        known = [p for p in full if p[3] <= cut]
        assert ef.zigzag(high[: cut + 1], low[: cut + 1], sigma[: cut + 1], 4) == known


def test_a_steady_rise_gives_no_leg():
    close = np.linspace(100, 140, 200)

    pivots = ef.zigzag(close * 1.001, close * 0.999, np.full(200, 0.01), 4)

    assert len(pivots) <= 1  # the starting low is confirmed by the rise; there is no second pivot, so no leg


def _leg_series(confirm_close: float, path_after_confirm: list[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Closes: a quiet lead-in, the confirmation bar (leg 100 -> 120), then the given path, then flat."""
    close = np.array([100.0] * 5 + [confirm_close] + path_after_confirm + [path_after_confirm[-1]] * 40)
    return close, close.copy(), close.copy(), 5


@pytest.mark.parametrize("close_after_touch, held", [(110.0 * 1.10, True), (110.0 * 0.90, False)])
def test_a_level_holds_when_price_turns_back_before_breaking_through(close_after_touch, held):
    # Leg 100 -> 120 confirmed with price at 115. The 50% retracement, 110, is still ahead: approached from
    # above. Price reaches 110, then closes 10% back above it (hold) or 10% through it (break).
    close, high, low, confirm = _leg_series(115.0, [110.0] + [close_after_touch] * 12)

    valid, hold = ef.evaluate_leg(confirm, 100.0, 120.0, close, high, low, 0.02, np.array([0.5]), "ret")

    assert valid[0]
    assert hold[0] == held


def test_a_retracement_level_price_has_already_passed_is_not_counted():
    close, high, low, confirm = _leg_series(105.0, [105.0] * 12)

    valid, _ = ef.evaluate_leg(confirm, 100.0, 120.0, close, high, low, 0.02, np.array([0.3]), "ret")  # 114: behind 105

    assert not valid[0]


def test_too_few_events_are_not_reported():
    ratios = ef.RETRACEMENT
    valid = np.full(len(ratios), 10.0)

    result = ef.excess_over_baseline(valid, valid * 0.5, ratios, ef.FIB_RETRACEMENT, np.random.default_rng(0))

    assert result["reported"] is False
