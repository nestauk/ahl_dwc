"""Unit tests for the ahl_dwc public API (input handling, output contracts)."""

import numpy as np
import polars as pl
import pytest

from ahl_dwc import adult_weight, energy_build, results_to_polars, set_seed

INTERPOLATIONS = [
    "Linear",
    "Exponential",
    "Stepwise_R",
    "Stepwise_L",
    "Logarithmic",
    "Brownian",
]

# Keys results_to_polars flattens; every adult_weight result must contain them.
TS_KEYS = [
    "Body_Weight",
    "Fat_Mass",
    "Lean_Mass",
    "Glycogen",
    "Extracellular_Fluid",
    "Adaptive_Thermogenesis",
    "Energy_Intake",
    "Body_Mass_Index",
    "BMI_Category",
    "Age",
]


def test_set_seed_accepts_int():
    # Should not raise; RNG control is exposed straight from the extension.
    set_seed(0)
    set_seed(623)


def test_adult_weight_single_individual_shapes():
    res = adult_weight(bw=80, ht=1.8, age=40, sex="female", days=365)
    assert isinstance(res, dict)
    for key in TS_KEYS + ["Time"]:
        assert key in res, f"missing key: {key}"
    bw = np.asarray(res["Body_Weight"])
    assert bw.shape == (1, len(res["Time"]))
    assert bw.shape[1] == 365


def test_adult_weight_population_shapes():
    weights = [67, 68, 69, 70, 71]
    heights = [1.30, 1.73, 1.77, 1.92, 1.73]
    ages = [45, 23, 66, 44, 23]
    sexes = ["male", "female", "female", "male", "male"]
    res = adult_weight(weights, heights, ages, sexes, days=200)
    bw = np.asarray(res["Body_Weight"])
    assert bw.shape == (5, 200)


def test_adult_weight_scalar_and_list_equivalent():
    scalar = adult_weight(80, 1.8, 40, "female")
    listed = adult_weight([80], [1.8], [40], ["female"])
    assert np.allclose(scalar["Body_Weight"], listed["Body_Weight"])


@pytest.mark.parametrize("mode", INTERPOLATIONS)
def test_energy_build_all_interpolations_shape(mode):
    out = energy_build([0, -250, 100], [0, 365, 730], interpolation=mode)
    out = np.asarray(out)
    assert out.ndim == 2
    assert out.shape[0] == 1
    # 730 daily steps from the [0, 730] horizon.
    assert out.shape[1] == 730


def test_energy_build_rejects_mismatched_columns():
    with pytest.raises(ValueError, match="Time"):
        energy_build([0, -250], [0, 365, 730], interpolation="Linear")


def test_energy_build_rejects_nonzero_first_time():
    with pytest.raises(ValueError, match="First time element must be 0"):
        energy_build([0, -250], [1, 365], interpolation="Linear")


def test_energy_build_rejects_negative_time():
    with pytest.raises(ValueError, match="positive"):
        energy_build([0, -250], [0, -365], interpolation="Linear")


def test_results_to_polars_returns_long_dataframe():
    res = adult_weight([80, 70], [1.8, 1.75], [40, 22], ["female", "male"], days=100)
    df = results_to_polars(res)
    assert isinstance(df, pl.DataFrame)
    assert {"Time", "Individual_ID"}.issubset(df.columns)
    for key in TS_KEYS:
        assert key in df.columns
    # Long format: one row per (individual, timestep).
    assert df.height == 2 * len(res["Time"])
    assert sorted(df["Individual_ID"].unique().to_list()) == [0, 1]
