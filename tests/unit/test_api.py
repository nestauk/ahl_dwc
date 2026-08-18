"""Unit tests for the ahl_dwc public API: input handling and output contracts."""

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


@pytest.mark.parametrize(
    ("bw", "ht", "age", "sex", "days"),
    [(80, 1.8, 40, "female", 365), (70, 1.75, 22, "male", 200)],
)
def test_adult_weight_single_individual_shapes(bw, ht, age, sex, days):
    res = adult_weight(bw=bw, ht=ht, age=age, sex=sex, days=days)
    assert isinstance(res, dict)
    for key in TS_KEYS + ["Time"]:
        assert key in res, f"missing key: {key}"
    arr = np.asarray(res["Body_Weight"])
    assert arr.shape == (1, len(res["Time"]))
    assert arr.shape[1] == days


def test_adult_weight_population_shapes():
    res = adult_weight(
        [67, 68, 69, 70, 71],
        [1.30, 1.73, 1.77, 1.92, 1.73],
        [45, 23, 66, 44, 23],
        ["male", "female", "female", "male", "male"],
        days=200,
    )
    assert np.asarray(res["Body_Weight"]).shape == (5, 200)


def test_adult_weight_scalar_and_list_equivalent():
    scalar = adult_weight(80, 1.8, 40, "female")
    listed = adult_weight([80], [1.8], [40], ["female"])
    assert np.allclose(scalar["Body_Weight"], listed["Body_Weight"])


@pytest.mark.parametrize("mode", INTERPOLATIONS)
def test_energy_build_all_interpolations_shape(mode):
    out = np.asarray(energy_build([0, -250, 100], [0, 365, 730], interpolation=mode))
    assert out.ndim == 2
    assert out.shape == (1, 730)  # 730 daily steps from the [0, 730] horizon


@pytest.mark.parametrize(
    ("energy", "time", "match"),
    [
        ([0, -250], [0, 365, 730], "Time"),
        ([0, -250], [1, 365], "First time element must be 0"),
        ([0, -250], [0, -365], "positive"),
    ],
)
def test_energy_build_validation_errors(energy, time, match):
    with pytest.raises(ValueError, match=match):
        energy_build(energy, time, interpolation="Linear")


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
