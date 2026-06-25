"""
export_dashboard_data.py

Runs the Tallinn integrated model (both scenarios, both PKM methods) and
exports a single JSON payload for the comparison dashboard, alongside the
embedded Granollers v8 reference checkpoints.
"""

import json
import numpy as np
from city_config import TALLINN
from mobility import run_mobility
from energy_demand import run_energy_demand
from energy_supply import run_energy_supply

YEARS = list(range(2019, 2051))

GRANOLLERS_V8_REF = {
    "years_checkpoints": [2019, 2025, 2030, 2040, 2050],
    "km_car_fos": [4112, 3350, 2587, 773, 111],
    "km_pt": [1330, 855, 766, 1083, 1419],
    "km_active": [681, 802, 906, 1185, 1453],
    "elec_emissions_kt": [129.4, 83.4, 45.0, 29.1, 13.3],
    # PLATER-related context figures (from project memory, not re-derived here)
    "pv_target_2050_mwp": 79.9,
    "population_2019": 60108,
    "population_2050": 76500,
}


def arr(x):
    return [round(float(v), 3) for v in np.asarray(x)]


def main():
    payload = {"years": YEARS, "tallinn": {}, "granollers_v8_reference": GRANOLLERS_V8_REF}

    for pi_label, pi_val in [("BAU", 0.0), ("PI1", 1.0)]:
        payload["tallinn"][pi_label] = {}
        for pkm_method in ("centroid", "mode_specific"):
            mob = run_mobility(TALLINN, pi_scenario=pi_val)
            ed = run_energy_demand(TALLINN, mob, pkm_method=pkm_method)
            es = run_energy_supply(TALLINN, ed)

            r = mob[pkm_method]
            entry = {
                "mobility": {
                    "car_fossil_km_cap": arr(r["dist_car_fossil_km_cap_yr"]),
                    "car_electric_km_cap": arr(r["dist_car_electric_km_cap_yr"]),
                    "pt_km_cap": arr(r["dist_pt_km_cap_yr"]),
                    "active_km_cap": arr(r["dist_active_km_cap_yr"]),
                    "ev_share_pct": arr(mob["ev_share"]),
                    "modal_split_car": arr(r["modal_split"]["car"]),
                    "modal_split_car_passenger": arr(r["modal_split"]["car passenger"]),
                    "modal_split_pt": arr(r["modal_split"]["public transport"]),
                    "modal_split_bicycle": arr(r["modal_split"]["bicycle"]),
                    "modal_split_walk": arr(r["modal_split"]["walk"]),
                },
                "energy_demand": {
                    "total_final_energy": arr(ed["total_final_energy"]),
                    "total_households": arr(ed["total_households"]),
                    "total_industry": arr(ed["total_industry"]),
                    "total_services": arr(ed["total_services"]),
                    "total_transport": arr(ed["total_transport"]),
                    "transport_car_fossil": arr(ed["transport_car_fossil"]),
                    "transport_car_electric": arr(ed["transport_car_electric"]),
                    "transport_pt_electric": arr(ed["transport_pt_electric"]),
                    "ED_CoreElectricityDemand": arr(ed["ED_CoreElectricityDemand"]),
                    "ED_CoreHeatDemand": arr(ed["ED_CoreHeatDemand"]),
                },
                "energy_supply": {
                    "power_pv": arr(es["power_pv"]),
                    "power_biomass_chp_el": arr(es["power_biomass_chp_el"]),
                    "power_waste_chp_el": arr(es["power_waste_chp_el"]),
                    "power_fossil": arr(es["power_fossil"]),
                    "net_imported_electricity": arr(es["net_imported_electricity"]),
                    "total_electricity_demand": arr(es["total_electricity_demand"]),
                    "total_heat_supply": arr(es["total_heat_supply"]),
                    "heat_biomass_chp": arr(es["heat_biomass_chp"]),
                    "heat_waste_chp": arr(es["heat_waste_chp"]),
                    "heat_pump": arr(es["heat_pump"]),
                    "heat_electric_boiler": arr(es["heat_electric_boiler"]),
                    "grid_emission_factor": arr(es["grid_emission_factor"]),
                    "em_transport": arr(es["em_transport"]),
                    "em_other": arr(es["em_other"]),
                    "em_elec_prod": arr(es["em_elec_prod"]),
                    "em_elec_imp": arr(es["em_elec_imp"]),
                    "em_dh": arr(es["em_dh"]),
                    "total_emissions_kt": arr(es["total_emissions_kt"]),
                    "pv_capacity_mwp": arr(es["pv_capacity_mwp"]),
                    "battery_capacity_mwh": arr(es["battery_capacity_mwh"]),
                },
            }
            payload["tallinn"][pi_label][pkm_method] = entry

    with open("/home/claude/work/output/dashboard_data.json", "w") as f:
        json.dump(payload, f)
    print("Exported dashboard_data.json")
    print("Size:", len(json.dumps(payload)), "bytes")


if __name__ == "__main__":
    main()
