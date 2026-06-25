"""
make_static_chart.py

Generates a static matplotlib comparison figure (Tallinn PI=1, centroid
method) analogous in style to granollers_integrated_v8_results_*.png.
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import FuncFormatter

from city_config import TALLINN, YEARS
from mobility import run_mobility
from energy_demand import run_energy_demand
from energy_supply import run_energy_supply

mob = run_mobility(TALLINN, pi_scenario=1.0)
ed = run_energy_demand(TALLINN, mob, pkm_method="centroid")
es = run_energy_supply(TALLINN, ed)

years = np.array(YEARS)
r = mob["centroid"]

C = {"car": "#D9743C", "car_el": "#E8A33D", "pt": "#3FA7D6", "act": "#5FB89C",
     "fos": "#795548", "pv": "#F9CB42", "chp": "#4CAF50", "waste": "#8D6E63",
     "imp": "#A87DC8", "em1": "#E53935", "em2": "#FF7043", "em3": "#BF4F1E",
     "em4": "#7B1FA2", "em5": "#FF5722"}


def fax(ax, ylabel=None):
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_xlim(2019, 2050)
    ax.grid(True, alpha=0.25, ls=":")
    ax.tick_params(labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9)


fig = plt.figure(figsize=(15, 11), facecolor="#0F1A24")
fig.suptitle("Tallinn — Integrated Model (v8 architecture) | PI=1 Scenario | 2019–2050",
             fontsize=13, fontweight="bold", color="white", y=0.995)
gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.32)

text_color = "#E7EEF2"
plt.rcParams.update({"text.color": text_color, "axes.labelcolor": text_color,
                      "xtick.color": text_color, "ytick.color": text_color,
                      "axes.edgecolor": "#23394A", "axes.facecolor": "#162635",
                      "figure.facecolor": "#0F1A24"})

# [0,0] Modal split
ax = fig.add_subplot(gs[0, 0])
car_pct = (r["modal_split"]["car"] + r["modal_split"]["car passenger"]) * 100
pt_pct = r["modal_split"]["public transport"] * 100
act_pct = (r["modal_split"]["bicycle"] + r["modal_split"]["walk"]) * 100
ax.stackplot(years, car_pct, pt_pct, act_pct,
             labels=["Car", "PT", "Active"], colors=[C["car"], C["pt"], C["act"]], alpha=0.9)
ax.set_title("Modal split (km share %)", fontsize=10, fontweight="bold", color=text_color)
fax(ax, "% of km")
ax.legend(fontsize=7, loc="upper right")

# [0,1] Distance per capita
ax = fig.add_subplot(gs[0, 1])
ax.plot(years, r["dist_car_fossil_km_cap_yr"], color=C["car"], lw=2, label="Car fossil")
ax.plot(years, r["dist_car_electric_km_cap_yr"], color=C["car_el"], lw=2, label="Car electric")
ax.plot(years, r["dist_pt_km_cap_yr"], color=C["pt"], lw=2, label="PT")
ax.plot(years, r["dist_active_km_cap_yr"], color=C["act"], lw=2, label="Active")
ax.set_title("Distance per capita (km/cap/yr)", fontsize=10, fontweight="bold", color=text_color)
fax(ax, "km/cap/yr")
ax.legend(fontsize=7)

# [0,2] EV share
ax = fig.add_subplot(gs[0, 2])
ax.plot(years, mob["ev_share"], color=C["car_el"], lw=2.5)
ax.set_title("EV fleet share (%)", fontsize=10, fontweight="bold", color=text_color)
fax(ax, "%")

# [1,0] Energy demand by sector
ax = fig.add_subplot(gs[1, 0])
ax.stackplot(years, ed["total_households"], ed["total_services"], ed["total_industry"], ed["total_transport"],
             labels=["Households", "Services", "Industry", "Transport"],
             colors=["#E91E63", "#E8A33D", "#607D8B", C["car"]], alpha=0.9)
ax.set_title("Final energy demand by sector (GWh/yr)", fontsize=10, fontweight="bold", color=text_color)
fax(ax, "GWh/yr")
ax.legend(fontsize=7, loc="upper right")

# [1,1] Supply mix
ax = fig.add_subplot(gs[1, 1])
ax.stackplot(years, es["power_pv"], es["power_biomass_chp_el"], es["power_waste_chp_el"], es["net_imported_electricity"],
             labels=["PV", "Biomass CHP", "Waste CHP", "Grid import"],
             colors=[C["pv"], C["chp"], C["waste"], C["imp"]], alpha=0.9)
ax.set_title("Electricity supply mix (GWh/yr)", fontsize=10, fontweight="bold", color=text_color)
fax(ax, "GWh/yr")
ax.legend(fontsize=7, loc="upper left")

# [1,2] Emissions
ax = fig.add_subplot(gs[1, 2])
ax.stackplot(years, es["em_transport"], es["em_other"], es["em_elec_prod"], es["em_elec_imp"], es["em_dh"],
             labels=["1. Transport", "2. Bldg/ind/svc", "3. Local fossil power", "4. Grid import", "5. DH fossil (TLN only)"],
             colors=[C["em1"], C["em2"], C["em3"], C["em4"], C["em5"]], alpha=0.9)
total_em = es["em_transport"] + es["em_other"] + es["em_elec_prod"] + es["em_elec_imp"] + es["em_dh"]
ax.plot(years, total_em, color="white", lw=2, ls="--", label="Total")
ax.set_title("GHG emissions, 5-component breakdown (kt CO₂-eq/yr)", fontsize=10, fontweight="bold", color=text_color)
fax(ax, "kt CO₂-eq/yr")
ax.legend(fontsize=6.5)

plt.tight_layout(rect=[0, 0, 1, 0.97])
out = "/home/claude/work/output/tallinn_integrated_v8_results.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved {out}")
