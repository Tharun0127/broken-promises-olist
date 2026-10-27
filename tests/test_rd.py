"""Known-answer tests for the regression discontinuity tools.

Synthetic inputs here are test fixtures with a known true effect, not analysis data.
"""
import numpy as np
import pytest

from src import rd


def step_data(jump=0.2, slope=0.01, reps=50, lo=-15, hi=15):
    x = np.repeat(np.arange(lo, hi + 1), reps).astype(float)
    y = 0.1 + slope * x + jump * (x >= 1)
    return x, y


def test_recovers_exact_jump_without_noise():
    x, y = step_data(jump=0.2, slope=0.01)
    for h in [3, 5, 10]:
        r = rd.local_linear_rd(x, y, h=h)
        assert r["estimate"] == pytest.approx(0.2, abs=1e-9)


def test_jump_is_measured_between_day_0_and_day_1():
    # Different slopes each side: the jump is the gap between the two lines at x = 0.5.
    x = np.repeat(np.arange(-10, 11), 20).astype(float)
    y = np.where(x >= 1, 0.5 + 0.03 * (x - 0.5), 0.2 + 0.01 * (x - 0.5))
    assert rd.local_linear_rd(x, y, h=6)["estimate"] == pytest.approx(0.3, abs=1e-9)


def test_no_jump_gives_zero_and_ci_covers_zero_with_noise():
    rng = np.random.default_rng(0)
    x, y = step_data(jump=0.0, reps=400)
    y = y + rng.normal(0, 0.1, size=len(y))
    r = rd.local_linear_rd(x, y, h=5)
    assert r["ci_low"] < 0 < r["ci_high"]


def test_ci_covers_true_jump_with_noise():
    rng = np.random.default_rng(1)
    x, y = step_data(jump=0.15, reps=400)
    y = y + rng.normal(0, 0.1, size=len(y))
    r = rd.local_linear_rd(x, y, h=5)
    assert r["ci_low"] < 0.15 < r["ci_high"]
    assert r["p_value"] < 0.001


def test_window_and_counts():
    x, y = step_data(reps=10)
    r = rd.local_linear_rd(x, y, h=4)
    assert r["n_left"] == 40 and r["n_right"] == 40      # days -3..0 and 1..4


def test_donut_drops_days_at_the_line():
    x, y = step_data(reps=10)
    r = rd.local_linear_rd(x, y, h=4, exclude=[0, 1])
    assert r["n_left"] == 30 and r["n_right"] == 30
    assert r["estimate"] == pytest.approx(0.2, abs=1e-9)


def test_adjacent_days_difference():
    x, y = step_data(jump=0.2, slope=0.0, reps=10)
    assert rd.adjacent_days(x, y)["estimate"] == pytest.approx(0.2)


def test_placebo_cutoffs_find_nothing_on_a_line():
    x, y = step_data(jump=0.2, slope=0.01)
    for p in rd.placebo_cutoffs(x, y, h=4):
        assert p["estimate"] == pytest.approx(0.0, abs=1e-9)


def test_placebo_windows_stay_on_one_side():
    x, y = step_data()
    below, above = rd.placebo_cutoffs(x, y, h=4)
    assert below["c"] == -3 and above["c"] == 5


def test_cv_prefers_small_bandwidth_when_curve_bends():
    x = np.repeat(np.arange(-20, 21), 30).astype(float)
    y = 0.1 + 0.002 * x ** 2
    h, table = rd.cv_bandwidth(x, y, grid=[3, 6, 12])
    assert h == 3
    assert table.cv_mse.is_monotonic_increasing


def test_density_test_detects_drop_and_passes_flat():
    days = np.arange(-10, 11)
    wiggle = np.where(days % 2 == 0, 4, -4)          # a perfect fit has zero dispersion; real counts never do
    flat = np.repeat(days, 400 + wiggle)
    r = rd.density_test(flat, h=6)
    assert r["count_ratio"] == pytest.approx(1.0, abs=0.05)
    assert r["p_value"] > 0.05
    dropped = np.repeat(days, np.where(days >= 1, 200, 400) + wiggle)
    r = rd.density_test(dropped, h=6)
    assert r["count_ratio"] == pytest.approx(0.5, abs=0.05)
    assert r["p_value"] < 0.001
