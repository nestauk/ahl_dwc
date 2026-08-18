"""Regression tests: pin known-good numerical behaviour of the adult_weight model.

These guard against silent changes in the compiled extension. Golden final-weight
values were captured from the reference build; physical quantities use a loose
relative tolerance to absorb cross-platform floating-point differences while still
catching genuine regressions (which shift results by whole kilograms).
"""

import numpy as np
import pytest

from ahl_dwc import adult_weight

# Loose enough for cross-platform libm/FMA differences, tight enough that a real
# model regression (order 0.1 kg+) fails.
PHYS_RTOL = 1e-4

# A sustained one-year deficit, reused across scenarios.
DEFICIT = {"ei_change": np.full(365, -250.0), "na_change": np.full(365, -20.0)}

# (name, adult_weight kwargs, expected final Body_Weight) — golden from reference build.
# Covers the basic wrapper plus the previously-untested EI and EI+fat variants.
GOLDEN = [
    ("female_deficit", {"bw": 80, "ht": 1.8, "age": 40, "sex": "female", **DEFICIT}, 73.178765),
    ("male_deficit", {"bw": 90, "ht": 1.85, "age": 35, "sex": "male", **DEFICIT}, 83.194082),
    ("ei_variant", {"bw": 80, "ht": 1.8, "age": 40, "sex": "female", "days": 365, "ei": 2500}, 85.140406),
    (
        "ei_fat_variant",
        {"bw": 80, "ht": 1.8, "age": 40, "sex": "female", "days": 365, "ei": 2500, "fat": 24},
        85.154781,
    ),
]


def test_no_energy_change_maintains_weight():
    bw = np.asarray(adult_weight(bw=80, ht=1.8, age=40, sex="female", days=365)["Body_Weight"])[0]
    # With no intake change the model holds weight at the initial value.
    assert np.allclose(bw, 80.0, atol=1e-6)


@pytest.mark.parametrize(("name", "kwargs", "expected"), GOLDEN, ids=[g[0] for g in GOLDEN])
def test_adult_weight_golden_final_weight(name, kwargs, expected):
    bw = np.asarray(adult_weight(**kwargs)["Body_Weight"])[0]
    assert np.isclose(bw[-1], expected, rtol=PHYS_RTOL)


def test_calorie_deficit_causes_weight_loss():
    res = adult_weight(80, 1.8, 40, "female", **DEFICIT)
    bw = np.asarray(res["Body_Weight"])[0]
    fat = np.asarray(res["Fat_Mass"])[0]
    assert bw[0] == 80.0
    assert bw[-1] < bw[0]  # net loss
    assert fat[-1] < fat[0]  # fat mass falls too


def test_adult_weight_is_deterministic():
    r1 = adult_weight(80, 1.8, 40, "female")
    r2 = adult_weight(80, 1.8, 40, "female")
    assert np.array_equal(np.asarray(r1["Body_Weight"]), np.asarray(r2["Body_Weight"]))
