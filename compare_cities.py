"""
compare_cities.py

Side-by-side comparison of Tallinn, Granollers and Naples (PI=1 scenario)
across four dimensions:
  Row 1 — Modal split (car / PT / active share over time)
  Row 2 — Final energy demand by sector (stacked area, GWh)
  Row 3 — Electricity supply breakdown (stacked area, GWh)
  Row 4 — Total emissions by component (stacked area, kt CO2-eq)
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

from city_config import TALLINN, GRANOLLERS, NAPLES
from mobility import run_mobility
from energy_demand import run_energy_demand
from energy_supply import run_energy_supply

OUT = Path(__file__).parent / "cities_comparison.png"

# ---------------------------------------------------------------------------
# Run all three cities
# ---------------------------------------------------------------------------
CITIES = [TALLINN, GRANOLLERS, NAPLES]
PI = 1.0

results = {}
for city in CITIES:
    mob = run_mobility(city, pi_scenario=PI)
    pkm = "mode_specific" if city.mobility.mode_specific_trip_length else "centroid"
    ed  = run_energy_demand(city, mob, pkm_method=pkm)
    es  = run_energy_supply(city, ed)
    results[city.name] = dict(mob=mob, ed=ed, es=es, years=mob["years"])

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------
CITY_COLORS = {
    "Tallinn":    "#0077b6",
    "Granollers": "#d94f00",
    "Naples":     "#7b2d8b",
}
SECTOR_COLORS = {
    "Households":  "#f4a261",
    "Industry":    "#457b9d",
    "Services":    "#2a9d8f",
    "Transport":   "#e76f51",
}
MODAL_COLORS = {
    "Car":    "#e63946",
    "PT":     "#457b9d",
    "Active": "#2a9d8f",
}
SUPPLY_COLORS = {
    "PV":          "#f4d03f",
    "Other local": "#a8dadc",
    "Net imports": "#457b9d",
}
EMISSION_COLORS = {
    "Transport":   "#e76f51",
    "Buildings":   "#f4a261",
    "Electricity": "#457b9d",
    "DH":          "#a8dadc",
}

plt.rcParams.update({
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "legend.fontsize": 8,
    "figure.facecolor": "white",
})

fig, axes = plt.subplots(4, 3, figsize=(15, 18))
fig.suptitle(
    "KNOWING Integrated Model — PI=1 Scenario\nTallinn · Granollers · Naples",
    fontsize=13, fontweight="bold", y=0.995
)

ROW_LABELS = [
    "Modal split (%)",
    "Final energy demand (GWh)",
    "Electricity supply (GWh)",
    "Total emissions (kt CO₂-eq)",
]
for row, label in enumerate(ROW_LABELS):
    axes[row, 0].set_ylabel(label, fontsize=9)

# ---------------------------------------------------------------------------
# Row 1 — Modal split
# ---------------------------------------------------------------------------
for col, city in enumerate(CITIES):
    ax = axes[0, col]
    r = results[city.name]
    yrs = r["years"]
    ms = r["mob"]["centroid"]["modal_split"]

    car    = (ms["car"] + ms["car passenger"]) * 100
    pt     = ms["public transport"] * 100
    active = (ms["bicycle"] + ms["walk"]) * 100

    ax.stackplot(yrs, car, pt, active,
                 labels=["Car", "PT", "Active"],
                 colors=[MODAL_COLORS["Car"], MODAL_COLORS["PT"], MODAL_COLORS["Active"]],
                 alpha=0.85)
    ax.set_xlim(2019, 2050)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(xmax=100, decimals=0))
    ax.set_title(city.name, fontweight="bold")
    ax.grid(True, alpha=0.25, linewidth=0.5)
    if col == 0:
        ax.legend(loc="lower left", framealpha=0.7, fontsize=8)
    # Annotate 2019 starting values on the right margin
    cumsum = 0
    for val, color in zip([car[0], pt[0], active[0]],
                          [MODAL_COLORS["Car"], MODAL_COLORS["PT"], MODAL_COLORS["Active"]]):
        mid = cumsum + val / 2
        if val > 5:
            ax.text(2020, mid, f"{val:.0f}%", fontsize=7, color="white",
                    fontweight="bold", va="center")
        cumsum += val
    if city.name == "Naples":
        ax.text(0.97, 0.97, "⚠ uncalibrated\ndamping",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=7, color="#7b2d8b",
                bbox=dict(boxstyle="round,pad=0.2", fc="lavender", alpha=0.7))

# ---------------------------------------------------------------------------
# Row 2 — Final energy demand by sector
# ---------------------------------------------------------------------------
for col, city in enumerate(CITIES):
    ax = axes[1, col]
    r = results[city.name]
    yrs = r["years"]
    ed  = r["ed"]

    hh  = ed["total_households"]
    ind = ed["total_industry"]
    svc = ed["total_services"]
    tr  = ed["total_transport"]

    ax.stackplot(yrs, hh, ind, svc, tr,
                 labels=["Households", "Industry", "Services", "Transport"],
                 colors=[SECTOR_COLORS[k] for k in ["Households", "Industry", "Services", "Transport"]],
                 alpha=0.85)
    ax.set_xlim(2019, 2050)
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda x, _: f"{x:,.0f}"))
    ax.grid(True, alpha=0.25, linewidth=0.5)
    if col == 0:
        ax.legend(loc="upper right", framealpha=0.7, fontsize=8)
    # 2019 total annotation
    ax.annotate(f"{(hh+ind+svc+tr)[0]:,.0f}", xy=(2019.5, (hh+ind+svc+tr)[0]),
                xytext=(0, 4), textcoords="offset points",
                fontsize=7.5, ha="left", va="bottom", color="#333")

# ---------------------------------------------------------------------------
# Row 3 — Electricity supply breakdown
# ---------------------------------------------------------------------------
for col, city in enumerate(CITIES):
    ax = axes[2, col]
    r  = results[city.name]
    yrs = r["years"]
    es  = r["es"]

    pv        = es["power_pv"]
    other_loc = (es["power_biomass_chp_el"] + es["power_waste_chp_el"] + es["power_fossil"])
    net_imp   = np.maximum(es["net_imported_electricity"], 0)  # imports only (positive)
    total_dem = es["total_electricity_demand"]

    ax.stackplot(yrs, pv, other_loc, net_imp,
                 labels=["PV", "Other local", "Net imports"],
                 colors=[SUPPLY_COLORS["PV"], SUPPLY_COLORS["Other local"], SUPPLY_COLORS["Net imports"]],
                 alpha=0.85)
    ax.plot(yrs, total_dem, color="#1d3557", linewidth=1.4,
            linestyle="--", label="Total demand", zorder=5)
    ax.set_xlim(2019, 2050)
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda x, _: f"{x:,.0f}"))
    ax.grid(True, alpha=0.25, linewidth=0.5)
    if col == 0:
        ax.legend(loc="upper left", framealpha=0.7, fontsize=8)

# ---------------------------------------------------------------------------
# Row 4 — Emissions by component
# ---------------------------------------------------------------------------
for col, city in enumerate(CITIES):
    ax = axes[3, col]
    r  = results[city.name]
    yrs = r["years"]
    es  = r["es"]

    em_tr  = es["em_transport"]
    em_bld = es["em_other"]
    em_el  = es["em_elec_prod"] + es["em_elec_imp"]
    em_dh  = es["em_dh"]

    ax.stackplot(yrs, em_tr, em_bld, em_el, em_dh,
                 labels=["Transport", "Buildings/direct", "Electricity", "DH"],
                 colors=[EMISSION_COLORS["Transport"], EMISSION_COLORS["Buildings"],
                         EMISSION_COLORS["Electricity"], EMISSION_COLORS["DH"]],
                 alpha=0.85)
    ax.set_xlim(2019, 2050)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Year")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda x, _: f"{x:,.0f}"))
    ax.grid(True, alpha=0.25, linewidth=0.5)
    if col == 0:
        ax.legend(loc="upper right", framealpha=0.7, fontsize=8)

    # Annotate 2019 and 2050 totals
    total = em_tr + em_bld + em_el + em_dh
    ax.annotate(f"{total[0]:,.0f} kt",  xy=(2019.5, total[0]),  xytext=(2, 4),
                textcoords="offset points", fontsize=7.5, color="#333")
    ax.annotate(f"{total[-1]:,.0f} kt", xy=(2049, total[-1]), xytext=(-2, 4),
                textcoords="offset points", fontsize=7.5, color="#333", ha="right")

# ---------------------------------------------------------------------------
# Common x-tick formatting
# ---------------------------------------------------------------------------
for row in range(4):
    for col in range(3):
        ax = axes[row, col]
        ax.set_xticks([2019, 2030, 2040, 2050])
        if row < 3:
            ax.set_xticklabels([])
        else:
            ax.set_xticklabels(["2019", "2030", "2040", "2050"])

fig.tight_layout(rect=[0, 0, 1, 0.995])
fig.savefig(OUT, dpi=150, bbox_inches="tight")
print(f"Saved: {OUT}")
