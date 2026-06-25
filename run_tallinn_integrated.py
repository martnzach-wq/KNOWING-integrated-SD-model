"""
run_tallinn_integrated.py

Runs the full Tallinn integrated model (Mobility -> Energy Demand ->
Energy Supply, 2019-2050) for both BAU and PI=1 scenarios, under both PKM
methods (centroid vs. mode-specific), and prints/exports a comparison
against the known Granollers v8 PI=1 reference checkpoints.

IMPORTANT SCOPE NOTE on the Granollers comparison:
    The actual Granollers v8 script (granollers_integrated_model.py) could
    not be executed here because its dependencies (config.json,
    EN_MEADCityInput_0527_v6.xlsx) were not available. The Granollers
    numbers used below are the script's own EMBEDDED reference checkpoints
    (REF_MOB, V4_EM), i.e. genuine v8 output values quoted verbatim from
    the uploaded script's cross-check assertions -- not independently
    re-derived. The "V4_EM" emissions figures are explicitly
    ELECTRICITY-ONLY scope (the v4 supply submodel cross-check), NOT the
    full 5-component total used elsewhere in the v8 script. Tallinn's
    "total_emissions_kt" (electricity/DH + direct combustion) is therefore
    NOT directly comparable to V4_EM without separating out the
    electricity/DH-only component first -- this script does that
    separation explicitly to avoid an apples-to-oranges comparison.
"""

import numpy as np
from city_config import TALLINN
from mobility import run_mobility
from energy_demand import run_energy_demand
from energy_supply import run_energy_supply

YEARS_CHK = [2019, 2025, 2030, 2040, 2050]
IDX_CHK = [int(y - 2019) for y in YEARS_CHK]

GRANOLLERS_V8_REF = {
    # Genuine embedded reference checkpoints from the uploaded
    # granollers_integrated_model.py (REF_MOB / V4_EM dicts), PI=1 scenario
    "km_car_fos": [4112, 3350, 2587, 773, 111],
    "km_pt": [1330, 855, 766, 1083, 1419],
    "km_active": [681, 802, 906, 1185, 1453],
    "elec_emissions_kt": [129.4, 83.4, 45.0, 29.1, 13.3],  # ELECTRICITY-ONLY scope
}


def run_city_scenario(city, pi_scenario, pkm_method):
    mob = run_mobility(city, pi_scenario=pi_scenario)
    ed = run_energy_demand(city, mob, pkm_method=pkm_method)
    es = run_energy_supply(city, ed)
    return mob, ed, es


def print_section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main():
    print_section("TALLINN INTEGRATED MODEL -- Mobility + Energy Demand + Energy Supply")
    print("Years: 2019-2050 | Scenarios: BAU (PI=0) and PI=1 | PKM methods: centroid, mode_specific")

    results = {}
    for pi_label, pi_val in [("BAU", 0.0), ("PI=1", 1.0)]:
        for pkm_method in ("centroid", "mode_specific"):
            key = (pi_label, pkm_method)
            results[key] = run_city_scenario(TALLINN, pi_val, pkm_method)

    # ------------------------------------------------------------------
    print_section("1. MOBILITY -- PKM method comparison (PI=1), Tallinn")
    print(f"{'Year':>6}  {'CarFos(centroid)':>17}  {'CarFos(mode-sp)':>16}  "
          f"{'PT(centroid)':>13}  {'PT(mode-sp)':>12}  {'Active(centroid)':>17}  {'Active(mode-sp)':>16}")
    mob_c = results[("PI=1", "centroid")][0]
    mob_m = results[("PI=1", "mode_specific")][0]
    for yr, i in zip(YEARS_CHK, IDX_CHK):
        rc = mob_c["centroid"]
        rm = mob_m["mode_specific"]
        print(f"{yr:>6}  {rc['dist_car_fossil_km_cap_yr'][i]:>17.0f}  {rm['dist_car_fossil_km_cap_yr'][i]:>16.0f}  "
              f"{rc['dist_pt_km_cap_yr'][i]:>13.0f}  {rm['dist_pt_km_cap_yr'][i]:>12.0f}  "
              f"{rc['dist_active_km_cap_yr'][i]:>17.0f}  {rm['dist_active_km_cap_yr'][i]:>16.0f}")

    # ------------------------------------------------------------------
    print_section("2. MOBILITY -- Tallinn (PI=1, centroid method) vs. Granollers v8 (PI=1) reference")
    print("NOTE: different cities, different calibration data -- shown for context, not as a validation target")
    print(f"{'Year':>6}  {'Tallinn CarFos':>14}  {'Granollers CarFos':>17}  "
          f"{'Tallinn PT':>10}  {'Granollers PT':>13}  {'Tallinn Active':>14}  {'Granollers Active':>17}")
    rc = results[("PI=1", "centroid")][0]["centroid"]
    for j, (yr, i) in enumerate(zip(YEARS_CHK, IDX_CHK)):
        print(f"{yr:>6}  {rc['dist_car_fossil_km_cap_yr'][i]:>14.0f}  {GRANOLLERS_V8_REF['km_car_fos'][j]:>17.0f}  "
              f"{rc['dist_pt_km_cap_yr'][i]:>10.0f}  {GRANOLLERS_V8_REF['km_pt'][j]:>13.0f}  "
              f"{rc['dist_active_km_cap_yr'][i]:>14.0f}  {GRANOLLERS_V8_REF['km_active'][j]:>17.0f}")

    # ------------------------------------------------------------------
    print_section("3. ENERGY DEMAND -- Tallinn BAU vs PI=1 (centroid method)")
    ed_bau = results[("BAU", "centroid")][1]
    ed_pi1 = results[("PI=1", "centroid")][1]
    print(f"{'Year':>6}  {'BAU total (GWh)':>16}  {'PI=1 total (GWh)':>17}  {'BAU transport':>14}  {'PI=1 transport':>15}")
    for yr, i in zip(YEARS_CHK, IDX_CHK):
        print(f"{yr:>6}  {ed_bau['total_final_energy'][i]:>16.0f}  {ed_pi1['total_final_energy'][i]:>17.0f}  "
              f"{ed_bau['total_transport'][i]:>14.0f}  {ed_pi1['total_transport'][i]:>15.0f}")

    # ------------------------------------------------------------------
    print_section("4. ENERGY SUPPLY & EMISSIONS -- Tallinn PI=1 (centroid method), full breakdown")
    es_pi1 = results[("PI=1", "centroid")][2]
    print(f"{'Year':>6}  {'1.Transport':>12}  {'2.Bldg/ind/svc':>15}  {'3.LocalFossil':>14}  {'4.GridImport':>13}  {'5.DHfossil(TLN)':>16}  {'TOTAL':>10}  {'GridEF':>8}")
    for yr, i in zip(YEARS_CHK, IDX_CHK):
        total = (es_pi1['em_transport'][i] + es_pi1['em_other'][i] + es_pi1['em_elec_prod'][i]
                 + es_pi1['em_elec_imp'][i] + es_pi1['em_dh'][i])
        print(f"{yr:>6}  {es_pi1['em_transport'][i]:>12.1f}  {es_pi1['em_other'][i]:>15.1f}  "
              f"{es_pi1['em_elec_prod'][i]:>14.1f}  {es_pi1['em_elec_imp'][i]:>13.1f}  "
              f"{es_pi1['em_dh'][i]:>16.1f}  {total:>10.1f}  {es_pi1['grid_emission_factor'][i]:>8.3f}")

    print_section("5. ELECTRICITY-ONLY EMISSIONS -- Tallinn vs Granollers v8 (PI=1)")
    print("(Scope-matched comparison: both numbers are electricity-sector-only (local fossil power +")
    print(" grid import), excluding direct transport/building combustion AND Tallinn's DH fossil --")
    print(" matching exactly the V4_EM reference scope)")
    print(f"{'Year':>6}  {'Tallinn elec-only (kt)':>22}  {'Granollers elec-only (kt)':>25}")
    for j, (yr, i) in enumerate(zip(YEARS_CHK, IDX_CHK)):
        tallinn_elec_only = es_pi1['em_elec_prod'][i] + es_pi1['em_elec_imp'][i]
        print(f"{yr:>6}  {tallinn_elec_only:>22.1f}  {GRANOLLERS_V8_REF['elec_emissions_kt'][j]:>25.1f}")
    print("\nInterpretation: Tallinn's electricity/DH emissions are far higher than Granollers'")
    print("throughout, driven by (a) Tallinn's oil-shale-dominated grid emission factor")
    print("(0.78 kg/kWh in 2019 vs Granollers' Spain-grid 0.19 kg/kWh) and (b) Tallinn's much")
    print("larger absolute electricity demand (a city of ~440k+113k vs ~60-76k population).")

    return results


if __name__ == "__main__":
    main()
