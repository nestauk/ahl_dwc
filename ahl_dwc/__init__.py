import numpy as np
import polars as pl

from . import _core

# Expose the set_seed function directly
set_seed = _core.set_seed


def adult_weight(
    bw: float | int | list[float] | list[int] | np.ndarray,
    ht: float | int | list[float] | list[int] | np.ndarray,
    age: float | int | list[float] | list[int] | np.ndarray,
    sex: str | list[str] | np.ndarray,
    ei_change: list[float] | np.ndarray | None = None,
    na_change: list[float] | np.ndarray | None = None,
    days: int = 365,
    dt: float = 1.0,
    **kwargs: dict,
) -> dict:
    """
    Simulates adult body weight changes over time.

    Args:
        bw: Initial body weight (kg).
        ht: Height (m).
        age: Age (years).
        sex: "male" or "female".
        ei_change: Change in energy intake (kcal/day) over time.
        na_change: Change in sodium intake (mmol/day) over time.
        days: Total simulation days.
        dt: Time step (days).
        **kwargs: Additional parameters like pal, pcarb, ei, fat, etc.

    Returns:
        A dictionary with time-series data of body weight and related metrics.
    """
    bw = np.atleast_1d(bw).astype(float)
    ht = np.atleast_1d(ht).astype(float)
    age = np.atleast_1d(age).astype(float)
    sex_input = np.atleast_1d(sex)
    sex_vals = np.array([1.0 if s == "female" else 0.0 for s in sex_input], dtype=float)
    n_ind = len(bw)
    steps = int(np.ceil(days / dt))

    if ei_change is None:
        ei_change = np.zeros((n_ind, steps))
    else:
        ei_change = np.array(ei_change, dtype=float)
        if ei_change.ndim == 1:
            if len(ei_change) == steps:
                ei_change = np.tile(ei_change, (n_ind, 1))
            else:
                ei_change = ei_change.reshape(n_ind, -1)

    if na_change is None:
        na_change = np.zeros((n_ind, steps))
    else:
        na_change = np.array(na_change, dtype=float)
        if na_change.ndim == 1:
            if len(na_change) == steps:
                na_change = np.tile(na_change, (n_ind, 1))
            else:
                na_change = na_change.reshape(n_ind, -1)

    ei_cpp = ei_change.T.tolist()
    na_cpp = na_change.T.tolist()
    pal = np.full(n_ind, kwargs.get("pal", 1.5)).astype(float)
    pcarb = np.full(n_ind, kwargs.get("pcarb", 0.5)).astype(float)
    pcarb_base = np.full(n_ind, kwargs.get("pcarb_base", 0.5)).astype(float)

    if "ei" in kwargs and "fat" in kwargs:
        return _core.adult_weight_wrapper_EI_fat(
            bw.tolist(),
            ht.tolist(),
            age.tolist(),
            sex_vals.tolist(),
            ei_cpp,
            na_cpp,
            pal.tolist(),
            pcarb_base.tolist(),
            pcarb.tolist(),
            dt,
            np.atleast_1d(kwargs["ei"]).astype(float).tolist(),
            np.atleast_1d(kwargs["fat"]).astype(float).tolist(),
            days,
            True,
        )
    elif "ei" in kwargs or "fat" in kwargs:
        is_energy = "ei" in kwargs
        extradata = np.atleast_1d(kwargs["ei"]) if is_energy else np.atleast_1d(kwargs["fat"])
        return _core.adult_weight_wrapper_EI(
            bw.tolist(),
            ht.tolist(),
            age.tolist(),
            sex_vals.tolist(),
            ei_cpp,
            na_cpp,
            pal.tolist(),
            pcarb_base.tolist(),
            pcarb.tolist(),
            dt,
            extradata.astype(float).tolist(),
            days,
            True,
            is_energy,
        )
    else:
        return _core.adult_weight_wrapper(
            bw.tolist(),
            ht.tolist(),
            age.tolist(),
            sex_vals.tolist(),
            ei_cpp,
            na_cpp,
            pal.tolist(),
            pcarb_base.tolist(),
            pcarb.tolist(),
            dt,
            days,
            True,
        )


def energy_build(
    energy: list[float] | list[list[float]] | np.ndarray,
    time: list[float] | np.ndarray,
    interpolation: str = "Brownian",
) -> np.ndarray:
    """
    Interpolates energy consumption moments.

    Args:
        energy: Energy values at specified time points.
        time: Time points corresponding to energy values.
        interpolation: Interpolation method. Options are
            "Linear", "Exponential", "Stepwise_R", "Stepwise_L",
            "Logarithmic", "Brownian".

    Returns:
        A 2D numpy array with interpolated energy values over time.
    """
    energy = np.array(energy, dtype=float)
    if energy.ndim == 1:
        energy = energy.reshape(1, -1)
    time = np.array(time, dtype=float)

    if energy.shape[1] != len(time):
        raise ValueError(f"Columns ({energy.shape[1]}) != Time ({len(time)})")
    if time[0] != 0:
        raise ValueError("First time element must be 0")
    if np.any(time < 0):
        raise ValueError("Time values must be positive")

    res = _core.EnergyBuilder(energy.tolist(), time.tolist(), interpolation)
    return res[:, 1:]


def results_to_polars(results: dict) -> pl.DataFrame:
    """
    Converts the dictionary output of adult_weight to a Polars DataFrame.

    Args:
        results: Dictionary output from adult_weight function.

    Returns:
        A Polars DataFrame in long format with columns for Time, Individual_ID,
        and all time-series variables.
    """
    # 1. Identify time-series keys
    # These are the keys that have the same length as 'Time' (cols)
    # and n_individuals (rows)
    ts_keys = [
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

    # 2. Get Time Vector
    time_vec = results["Time"]
    n_steps = len(time_vec)

    # 3. Detect number of individuals
    # Check the first variable (e.g. Body_Weight) to see how many rows it has
    # The C++ output is List[List] -> Matrix[Rows=Ind, Cols=Time]
    first_var = results["Body_Weight"]
    n_inds = len(first_var)

    data_dict = {}

    # 4. Flatten Data for Long Format
    # We repeat the time vector for each individual
    # Time: [0, 1, ... 365, 0, 1, ... 365]
    data_dict["Time"] = np.tile(time_vec, n_inds)

    # Create an ID column: [0, 0... 0, 1, 1... 1]
    # Using repeat ensures we get [0,0,0, 1,1,1] matching the tiled time
    data_dict["Individual_ID"] = np.repeat(range(n_inds), n_steps)

    for key in ts_keys:
        # The data comes as [Ind1_Series, Ind2_Series, ...]
        # np.ravel (or flatten) effectively stacks them: Ind1 then Ind2...
        # consistent with our Time/ID tiling above.
        values = np.array(results[key])  # Ensure it's an array for easy flattening
        data_dict[key] = values.ravel()

    # 5. Create DataFrame
    return pl.DataFrame(data_dict)
