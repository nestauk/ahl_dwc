"""Regression tests: pin known-good numerical behaviour of the C++ model.

These guard against silent changes in the compiled extension (including the
GCC/libstdc++ compatibility fix, which must not alter results). Golden values
were captured from the reference macOS build; physical quantities use a loose
relative tolerance to absorb cross-platform floating-point differences while
still catching genuine regressions (which shift results by whole kilograms).
"""

import numpy as np

from ahl_dwc import adult_weight, energy_build, set_seed

# Loose enough for cross-platform libm/FMA differences, tight enough that a real
# model regression (order 0.1 kg+) fails.
PHYS_RTOL = 1e-4


def test_no_energy_change_maintains_weight():
    res = adult_weight(bw=80, ht=1.8, age=40, sex="female", days=365)
    bw = np.asarray(res["Body_Weight"])[0]
    # With no intake change the model holds weight at the initial value.
    assert np.allclose(bw, 80.0, atol=1e-6)


def test_calorie_deficit_causes_weight_loss():
    days = 365
    ei_change = np.full(days, -250.0)
    na_change = np.full(days, -20.0)
    res = adult_weight(80, 1.8, 40, "female", ei_change=ei_change, na_change=na_change)
    bw = np.asarray(res["Body_Weight"])[0]
    assert bw[0] == 80.0
    # Golden: sustained -250 kcal/day deficit for a year.
    assert np.isclose(bw[-1], 73.1787651565, rtol=PHYS_RTOL)
    assert bw[-1] < bw[0]  # net loss
    # Fat mass should fall too.
    fat = np.asarray(res["Fat_Mass"])[0]
    assert fat[-1] < fat[0]


def test_adult_weight_is_deterministic():
    r1 = adult_weight(80, 1.8, 40, "female")
    r2 = adult_weight(80, 1.8, 40, "female")
    assert np.array_equal(np.asarray(r1["Body_Weight"]), np.asarray(r2["Body_Weight"]))


def test_energy_build_linear_is_analytic():
    out = np.asarray(energy_build([0, -250, 100], [0, 365, 730], interpolation="Linear"))
    step = -250.0 / 365.0
    expected = step * np.arange(1, 4)  # first three days of the first segment
    assert np.allclose(out[0, :3], expected, rtol=1e-9)


def test_brownian_is_seed_reproducible():
    set_seed(1)
    a = np.asarray(energy_build([0, -250, 100], [0, 365, 730], interpolation="Brownian"))
    set_seed(1)
    b = np.asarray(energy_build([0, -250, 100], [0, 365, 730], interpolation="Brownian"))
    assert np.array_equal(a, b)


def test_brownian_varies_with_seed():
    set_seed(1)
    a = np.asarray(energy_build([0, -250, 100], [0, 365, 730], interpolation="Brownian"))
    set_seed(2)
    c = np.asarray(energy_build([0, -250, 100], [0, 365, 730], interpolation="Brownian"))
    assert not np.array_equal(a, c)
