"""
compare_ev_rates.py

Runs the integrated model for Tallinn and Granollers under BAU (PI=0) and
PI=1 scenarios and produces a diagram comparing EV fleet share trajectories.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

from city_config import TALLINN, GRANOLLERS
from mobility import run_mobility

OUT = Path(__file__).parent / "ev_comparison.png"

SCENARIOS = [("PI=1", 1.0), ("BAU", 0.0)]
CITIES = [TALLINN, GRANOLLERS]
COLORS = {
    "Tallinn": "#1a6faf",
    "Granollers": "#d94f00",
}
LINESTYLES = {"PI=1": "-", "BAU": "--"}

fig, ax = plt.subplots(figsize=(10, 6))

for city in CITIES:
    for label, pi in SCENARIOS:
        mob = run_mobility(city, pi_scenario=pi)
        years = mob["years"]
        ev = mob["ev_share"]
        ax.plot(
            years, ev,
            color=COLORS[city.name],
            linestyle=LINESTYLES[label],
            linewidth=2.2 if label == "PI=1" else 1.4,
            label=f"{city.name} – {label}",
        )

# Reference anchor markers for Granollers (from ev_pi_trajectory in city_config)
gran_anchors = {2019: 0.2, 2022: 1.5, 2025: 7.0, 2028: 14.0, 2030: 20.0, 2040: 55.0, 2050: 80.0}
ax.scatter(list(gran_anchors.keys()), list(gran_anchors.values()),
           color=COLORS["Granollers"], marker="o", s=40, zorder=5,
           label="Granollers PI=1 anchors")

ax.set_xlabel("Year", fontsize=12)
ax.set_ylabel("EV fleet share (%)", fontsize=12)
ax.set_title("EV Fleet Share 2019–2050\nTallinn vs. Granollers — BAU and PI=1 scenarios", fontsize=13)
ax.set_xlim(2019, 2050)
ax.set_ylim(0, 100)
ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(xmax=100, decimals=0))
ax.grid(True, alpha=0.3)
ax.legend(loc="upper left", fontsize=10)

# Annotate 2050 endpoints
for city in CITIES:
    for label, pi in SCENARIOS:
        mob = run_mobility(city, pi_scenario=pi)
        val = mob["ev_share"][-1]
        ax.annotate(
            f"{val:.0f}%",
            xy=(2050, val),
            xytext=(6, 0),
            textcoords="offset points",
            fontsize=9,
            color=COLORS[city.name],
            va="center",
        )

fig.tight_layout()
fig.savefig(OUT, dpi=150)
print(f"Saved: {OUT}")
