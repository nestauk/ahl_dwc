import matplotlib.pyplot as plt
import numpy as np

from ahl_dwc import adult_weight, energy_build, set_seed

set_seed(623)


def plot_model(model_data: dict, variable: str, title: str) -> None:
    time = model_data["Time"]
    values = model_data[variable]  # Shape is (Individuals, Time)

    plt.figure(figsize=(7, 4))
    if values.ndim == 1:
        plt.plot(time, values)
    else:
        for i, row in enumerate(values):
            plt.plot(time, row, label=f"Ind {i + 1}")

    plt.title(title)
    plt.xlabel("Time (days)")
    plt.ylabel(variable.replace("_", " "))
    plt.grid(True, linestyle="--", alpha=0.5)
    if values.shape[0] > 1:
        plt.legend()

    filename = f"{title.replace(' ', '_').replace('(', '').replace(')', '')}.png"
    plt.savefig(filename)
    print(f"Saved plot: {filename}")
    plt.close()


# --- 1. Individual Modelling ---
print("--- 1. Individual Modelling ---")
f_bw_base = adult_weight(bw=80, ht=1.8, age=40, sex="female")
print(f"Baseline Final Weight: {f_bw_base['Body_Weight'][0, -1]:.2f} kg")

days = 365
ei_change = np.full(days, -250)
na_change = np.full(days, -20)

f_diet = adult_weight(80, 1.8, 40, "female", ei_change=ei_change, na_change=na_change)
print(f"Diet Final Weight: {f_diet['Body_Weight'][0, -1]:.2f} kg")
plot_model(f_diet, "Body_Weight", "Female Diet (-250kcal)")


# --- 2. Energy Build & Weight Change Comparison ---
print("\n--- 2. Energy Build & Weight Change Comparison ---")
times = [0, 365, 730]
measures = [0, -250, 100]

# Define interpolations and their colors (matching your ggplot spec)
interpolations = [
    ("Linear", "deepskyblue"),
    ("Exponential", "forestgreen"),
    ("Stepwise_R", "black"),
    ("Stepwise_L", "green"),
    ("Logarithmic", "purple"),
    ("Brownian", "red"),
]

# Store EI curves for the weight model step
ei_curves = {}

# Plot 1: Energy Interpolation (The inputs)
plt.figure(figsize=(8, 5))
for mode, color in interpolations:
    # Get energy curve (1 row, extract vector)
    ei_curve = energy_build(measures, times, interpolation=mode)[0]
    ei_curves[mode] = ei_curve

    # Plot style
    if "Stepwise" in mode:
        plt.step(range(len(ei_curve)), ei_curve, label=mode, color=color, where="post" if "_R" in mode else "pre")
    else:
        plt.plot(ei_curve, label=mode, color=color)

plt.title("Energy Interpolation")
plt.xlabel("Days")
plt.ylabel("Energy change (kcals)")
plt.legend(title="Interpolation")
plt.grid(True, linestyle="--", alpha=0.3)
plt.savefig("Energy_Interpolation.png")
print("Saved plot: Energy_Interpolation.png")
plt.close()

# Plot 2: Weight Change (The outputs) -> THIS IS THE NEW PLOT YOU REQUESTED
plt.figure(figsize=(8, 5))
print("Calculating weight models for all interpolations...")

for mode, color in interpolations:
    # Run model: bw=70, ht=1.75, age=22, male, days=730
    res = adult_weight(70, 1.75, 22, "male", ei_change=ei_curves[mode], days=730)

    weight_traj = res["Body_Weight"][0]  # Extract trajectory for individual 0

    plt.plot(weight_traj, label=mode, color=color)

plt.title("Weight change under different energy interpolations")
plt.xlabel("Days")
plt.ylabel("Weight (kg)")
plt.legend(title="Interpolation")
plt.grid(True, linestyle="--", alpha=0.3)
plt.savefig("Weight_Change_Interpolations.png")
print("Saved plot: Weight_Change_Interpolations.png")
plt.close()


# --- 3. Database Modelling ---
print("\n--- 3. Database Modelling ---")
weights = [67, 68, 69, 70, 71]
heights = [1.30, 1.73, 1.77, 1.92, 1.73]
ages = [45, 23, 66, 44, 23]
sexes = ["male", "female", "female", "male", "male"]
energy_changes = [-150, -100, 50, -200, 0]

pop_measures = np.column_stack((np.zeros(5), energy_changes))
pop_times = [0, 365]
pop_ei = energy_build(pop_measures, pop_times, interpolation="Linear")
pop_model = adult_weight(weights, heights, ages, sexes, ei_change=pop_ei, days=365)

print("Population Final Weights:")
print(pop_model["Body_Weight"][:, -1])

plot_model(pop_model, "Body_Weight", "Population Model Results")
