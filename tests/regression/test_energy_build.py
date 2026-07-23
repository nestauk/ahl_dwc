"""Regression tests for energy_build interpolations.

Deterministic modes are pinned by reproducibility + an analytic check; the
Brownian mode (the only stochastic path) is pinned by seed-reproducibility and
seed-variance only, since std::normal_distribution is implementation-defined and
its exact values are not portable across standard libraries.
"""

import numpy as np
import pytest

from ahl_dwc import energy_build, set_seed

DETERMINISTIC = ["Linear", "Exponential", "Stepwise_R", "Stepwise_L", "Logarithmic"]


def test_energy_build_linear_is_analytic():
    out = np.asarray(energy_build([0, -250, 100], [0, 365, 730], interpolation="Linear"))
    step = -250.0 / 365.0
    expected = step * np.arange(1, 4)  # first three days of the first segment
    assert np.allclose(out[0, :3], expected, rtol=1e-9)


@pytest.mark.parametrize("mode", DETERMINISTIC)
def test_energy_build_deterministic_modes_reproducible(mode):
    a = np.asarray(energy_build([0, -250, 100], [0, 365, 730], interpolation=mode))
    b = np.asarray(energy_build([0, -250, 100], [0, 365, 730], interpolation=mode))
    assert np.array_equal(a, b)


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
