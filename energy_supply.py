"""
energy_supply.py

Python translation of Submodel_EnergySupply_v4.mdl, parametrized by
CityConfig. Reads city-specific capacity/supply XLSX (2019 & 2050
keyframes, linearly interpolated -- matching Vensim's :INTERPOLATE:
behaviour and the explicit "(2050-2019)/31 per year" build-out formulas
found in the .mdl for new biomass/heatpump/electric-boiler capacity).

Key structural facts (verified against the .mdl):
    - Electricity & heat CAPACITY and SUPPLY are linearly interpolated
      between 2019 and 2050 keyframes (ES xxx Capacity / ES xxx Supply
      rows in the XLSX).
    - Fossil power production fills the residual gap between demand and
      renewable/CHP production, capped by installed fossil capacity, with
      a built-in assumption that it goes to zero after ~10 years
      ("Assumption: Preference over importing; but anyway zero after
      10y").
    - Net imported electricity = TotalElectricityDemand - TotalProduction.
    - Grid emission factor: the ORIGINAL .mdl has a simplified built-in
      "Average for Estonia: 0.4, going linear towards zero until 2050"
      assumption (ES ImportedElectricityMixFactor). By explicit decision,
      this is REPLACED with the evidence-based Ember/EEA-anchored
      trajectory in CityConfig.energy_supply.grid_emission_factor
      (0.78 in 2019 -> 0.02 in 2050), the same way Granollers replaced
      the Vensim default with a Spain-specific REE/PNIEC/PROENCAT path.
    - Heat: dispatch order is Biomass CHP + Waste CHP (capped at their
      installed capacity-scaled output) -> Gas/Oil boilers phasing out
      -> Heat Pump + Electric Boiler covering any residual gap
      ("ES HeatSupplyGap").
"""

from __future__ import annotations
import numpy as np
import openpyxl
from city_config import CityConfig, YEARS

FOSSIL_ELECTRICITY_TYPES = ["Fuel Oil PP", "Biogas PP", "Natural Gas CHP el", "Peat CHP el"]


def _read_supply_xlsx(xlsx_path: str, sheet_name: str = "ES_inputs") -> dict:
    """Read {category: {item: (val_2019, val_2050)}} from the supply XLSX."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb[sheet_name]
    data = {}
    for row in ws.iter_rows(values_only=True):
        category, item, v2019, v2050 = row[0], row[1], row[2], row[3]
        if category is None or category == "Time":
            continue
        data.setdefault(category, {})
        key = item if item is not None else "_scalar"
        data[category][key] = (v2019, v2050)
    return data


def _lin_interp_2pt(v2019, v2050, years=YEARS):
    return np.interp(years, [2019, 2050], [v2019, v2050])


def run_energy_supply(city: CityConfig, energy_demand_results: dict):
    """
    energy_demand_results: output of energy_demand.run_energy_demand(...)
    Returns a dict of annual supply-side series.
    """
    esc = city.energy_supply
    if esc.synthetic_supply_data is not None:
        # City without a real multi-technology capacity XLSX (e.g.
        # Granollers) -- use the synthetic data generator instead, which
        # returns the exact same {category: {item: (v2019, v2050)}} shape
        # _read_supply_xlsx() would, so no further branching is needed.
        raw = esc.synthetic_supply_data()
    else:
        raw = _read_supply_xlsx(esc.xlsx_path)
    n = len(YEARS)
    years = np.array(YEARS)

    # --- Capacity & supply trajectories (linear interpolation 2019->2050) ---
    elec_capacity = {}
    elec_supply = {}
    for item, (v19, v50) in raw.get("ES ElectricityCapacity", {}).items():
        elec_capacity[item] = _lin_interp_2pt(v19, v50)
    for item, (v19, v50) in raw.get("ES ElectrictitySupply", {}).items():
        elec_supply[item] = _lin_interp_2pt(v19, v50)

    heat_capacity = {}
    heat_supply = {}
    for item, (v19, v50) in raw.get("ES HeatCapacity", {}).items():
        heat_capacity[item] = _lin_interp_2pt(v19, v50)
    for item, (v19, v50) in raw.get("ES HeatSupply", {}).items():
        heat_supply[item] = _lin_interp_2pt(v19, v50)

    # --- Electricity demand from the energy demand submodel ---
    ed_core_elec = energy_demand_results["ED_CoreElectricityDemand"]
    ed_core_heat = energy_demand_results["ED_CoreHeatDemand"]

    # --- Heat dispatch: Biomass CHP + Waste CHP capped by capacity-scaled output ---
    def capacity_scaled(item_supply_2019, item_capacity_2019, capacity_now):
        # ES xxx = InstalledCapacity_now * Supply_2019 / Capacity_2019 (per .mdl)
        if item_capacity_2019 == 0:
            return np.zeros(n)
        return capacity_now * item_supply_2019 / item_capacity_2019

    heat_biomass_chp = np.minimum(
        capacity_scaled(
            raw["ES HeatSupply"].get("Biomass CHP", (0, 0))[0],
            raw["ES HeatCapacity"].get("Biomass CHP", (0, 0))[0],
            heat_capacity.get("Biomass CHP", np.zeros(n)),
        ),
        heat_supply.get("Biomass CHP", np.zeros(n)),
    )
    heat_waste_chp = np.minimum(
        capacity_scaled(
            raw["ES HeatSupply"].get("Waste CHP", (0, 0))[0],
            raw["ES HeatCapacity"].get("Waste CHP", (0, 0))[0],
            heat_capacity.get("Waste CHP", np.zeros(n)),
        ),
        heat_supply.get("Waste CHP", np.zeros(n)),
    )
    # Gas boiler: uses 2019 scaling (phasing toward 0 as capacity declines)
    heat_gas = capacity_scaled(
        raw["ES HeatSupply"].get("DH Natural Gas Boiler", (0, 0))[0],
        raw["ES HeatCapacity"].get("DH Natural Gas Boiler", (0, 0))[0],
        heat_capacity.get("DH Natural Gas Boiler", np.zeros(n)),
    )
    heat_oil = capacity_scaled(
        raw["ES HeatSupply"].get("DH Fuel Oil Boiler", (0, 0))[0],
        raw["ES HeatCapacity"].get("DH Fuel Oil Boiler", (0, 0))[0],
        heat_capacity.get("DH Fuel Oil Boiler", np.zeros(n)),
    )

    heat_supply_so_far = heat_biomass_chp + heat_waste_chp + heat_gas + heat_oil
    heat_supply_gap = np.maximum(ed_core_heat - heat_supply_so_far, 0)

    # Heat pump + electric boiler cover the gap, scaled toward their 2050 capacity
    hp_2050_supply = raw["ES HeatSupply"].get("DH Heat Pump", (0, 0))[1]
    hp_2050_capacity = raw["ES HeatCapacity"].get("DH Heat Pump", (0, 0))[1]
    eb_2050_supply = raw["ES HeatSupply"].get("DH Electric Boiler", (0, 0))[1]
    eb_2050_capacity = raw["ES HeatCapacity"].get("DH Electric Boiler", (0, 0))[1]

    hp_capacity_now = heat_capacity.get("DH Heat Pump", np.zeros(n))
    eb_capacity_now = heat_capacity.get("DH Electric Boiler", np.zeros(n))

    heat_hp = (hp_capacity_now * hp_2050_supply / hp_2050_capacity
               if hp_2050_capacity else np.zeros(n))
    heat_eb = (eb_capacity_now * eb_2050_supply / eb_2050_capacity
               if eb_2050_capacity else np.zeros(n))
    # electric boiler explicitly absorbs any residual gap per .mdl comment
    # ("Assumption: scaled against data, but gap covered by electric boilers")
    heat_eb = heat_eb + heat_supply_gap

    total_heat_supply = heat_biomass_chp + heat_waste_chp + heat_gas + heat_oil + heat_hp + heat_eb

    # --- DH electricity demand (heat pump + electric boiler consumption) ---
    el_demand_dh_hp_2050 = raw.get("ES ElDemand DH HP", {}).get("_scalar", (0, 0))[1]
    el_demand_dh_eb_2050 = raw.get("ES ElDemand DH EB", {}).get("_scalar", (0, 0))[1]
    dh_elec_demand = (
        heat_hp * (el_demand_dh_hp_2050 / hp_2050_supply if hp_2050_supply else 0)
        + heat_eb * (el_demand_dh_eb_2050 / eb_2050_supply if eb_2050_supply else 0)
    )

    total_elec_demand = ed_core_elec + dh_elec_demand

    # --- Electricity production ---
    pv_capacity_now = elec_capacity.get("PV", np.zeros(n))
    pv_2019_supply, pv_2019_capacity = raw["ES ElectrictitySupply"].get("PV", (0, 0))[0], raw["ES ElectricityCapacity"].get("PV", (0, 0))[0]
    pv_productivity = pv_2019_supply / pv_2019_capacity if pv_2019_capacity else 0
    power_pv = pv_capacity_now * pv_productivity

    power_biomass_chp_el = elec_supply.get("Biomass CHP el", np.zeros(n))
    power_waste_chp_el = elec_supply.get("Waste CHP el", np.zeros(n))

    # wind/hydro: not present in Tallinn capacity table -> zero
    power_wind = np.zeros(n)
    power_hydro = np.zeros(n)

    # Fossil: fills residual gap up to installed-capacity-scaled max output,
    # with the model's built-in assumption that it phases to ~0 after 10 years
    fossil_capacity_now = sum(elec_capacity.get(t, np.zeros(n)) for t in FOSSIL_ELECTRICITY_TYPES)
    fossil_capacity_2019 = sum(raw["ES ElectricityCapacity"].get(t, (0, 0))[0] for t in FOSSIL_ELECTRICITY_TYPES)
    fossil_supply_2019 = sum(raw["ES ElectrictitySupply"].get(t, (0, 0))[0] for t in FOSSIL_ELECTRICITY_TYPES)
    fossil_max_output = (fossil_capacity_now * fossil_supply_2019 / fossil_capacity_2019
                          if fossil_capacity_2019 else np.zeros(n))

    if esc.fossil_power_dispatch_mode == "fixed_schedule":
        # Granollers-style: local fossil generation runs at its own fixed,
        # capacity-determined output (e.g. PP_CHP = IC_GasCHP * 2.0),
        # independent of demand. Grid import then absorbs any mismatch.
        power_fossil = fossil_max_output.copy()
    else:
        # Tallinn-style: fills the residual gap between demand and other
        # local sources, capped by installed capacity.
        residual_for_fossil = total_elec_demand - power_pv - power_wind - power_hydro
        power_fossil = np.minimum(np.maximum(residual_for_fossil, 0), fossil_max_output)
        # 10-year phase-out: Tallinn's .mdl assumption ("Assumption:
        # Preference over importing; but anyway zero after 10y",
        # appropriate for peaker plants filling a temporary gap).
        if esc.fossil_power_phases_out_after_10y:
            power_fossil = np.where(years - years[0] > 10, 0.0, power_fossil)

    power_total = power_fossil + power_wind + power_pv + power_hydro + power_biomass_chp_el + power_waste_chp_el

    net_imported_elec = total_elec_demand - power_total

    # --- EMISSIONS ----------------------------------------------------
    # Structured to match the Granollers v8 ParentModel_Energy_corrected.mdl
    # 5-component breakdown exactly (em_transport, em_other, em_elec_prod,
    # em_elec_imp, em_dh), so the two cities are directly comparable
    # component-by-component. Tallinn-specific extensions are added on top
    # where the original Granollers structure doesn't apply (Granollers has
    # no district heating network at all, and only one local generation
    # technology -- Gas CHP -- vs. Tallinn's four).
    #
    # FUEL_EF = 270 t CO2/GWh: identical factor to granollers_integrated_
    # model.py, used for ALL direct fossil-fuel combustion (transport fuel,
    # building fossil fuel, AND -- Tallinn-specific -- DH gas/oil boilers).
    FUEL_EF_T_PER_GWH = 270.0
    CHP_EF_KT_PER_GWH = 0.45  # kt CO2/GWh, identical factor to Granollers' Gas CHP

    grid_ef = np.interp(years, sorted(city.energy_supply.grid_emission_factor.keys()),
                         [city.energy_supply.grid_emission_factor[y]
                          for y in sorted(city.energy_supply.grid_emission_factor.keys())])

    ed = energy_demand_results

    # 1) em_transport -- direct combustion, transport fossil fuel
    #    (car fossil + "other" pax + freight fossil), matching Granollers exactly
    em_transport = (
        ed.get("transport_car_fossil", np.zeros(n))
        + ed.get("transport_other", np.zeros(n))
        + ed.get("freight_fossil", np.zeros(n))
    ) * FUEL_EF_T_PER_GWH / 1000.0

    # 2) em_other -- direct combustion, buildings + industry + services fossil
    #    (household heating fossil + household other fossil + industry fossil
    #    + services fossil), matching Granollers exactly
    em_other = (
        ed.get("hh_heating_fossil", np.zeros(n))
        + ed.get("hh_other_fossil", np.zeros(n))
        + ed.get("industry_fossil", np.zeros(n))
        + ed.get("service_fossil", np.zeros(n))
    ) * FUEL_EF_T_PER_GWH / 1000.0

    # 3) em_elec_prod -- LOCAL fossil-fuelled electricity production.
    #    Granollers has one technology (Gas CHP, flat 0.45 kt/GWh factor).
    #    Tallinn's XLSX lists four local generation technologies; only the
    #    FOSSIL ones (Fuel Oil PP, Biogas PP, Natural Gas CHP el, Peat CHP
    #    el -- i.e. "power_fossil" computed above) are emitting. Biomass CHP
    #    and Waste CHP electricity are treated as zero-fossil-emission by
    #    convention, the same way Granollers treats its biomass+HP DH as
    #    em_dh=0 -- this is a TALLINN-SPECIFIC EXTENSION POINT: unlike
    #    Granollers' single CHP_EF, Tallinn's local fossil power mix
    #    (oil/gas/peat/biogas) is approximated with the .mdl's own blended
    #    "ES ElectricityGenTotalEmissions" factor (0.55 kg/kWh) rather than
    #    Granollers' gas-CHP-specific 0.45 kt/GWh, since Tallinn's local
    #    fossil capacity is a mix of plant types, not gas CHP alone.
    em_elec_prod = power_fossil * esc.fossil_power_emission_factor

    # 4) em_elec_imp -- grid import emissions, matching Granollers exactly
    #    (NetImport x GridEF; Tallinn uses its own evidence-based grid
    #    emission factor trajectory, 0.78->0.02 kg/kWh, in place of
    #    Granollers' Spain PNIEC path)
    em_elec_imp = net_imported_elec * grid_ef

    # 5) em_dh -- district heating fossil combustion. Granollers sets this
    #    to EXACTLY ZERO ("biomass+HP DH -> zero fossil emissions") because
    #    it has no DH network with fossil boilers at all. TALLINN-SPECIFIC:
    #    Tallinn has a REAL district heating network with actual gas and
    #    oil boilers (DH Natural Gas Boiler, DH Fuel Oil Boiler) that ARE
    #    still operating, phasing out over the projection -- this is the
    #    main genuinely Tallinn-specific emissions component with no
    #    Granollers equivalent.
    em_dh = (heat_gas + heat_oil) * FUEL_EF_T_PER_GWH / 1000.0

    # --- TALLINN-SPECIFIC EXTENSION: biomass/waste CHP heat & power are
    # reported separately as an explicit zero-emission line (rather than
    # silently omitted), since Tallinn's biomass/waste CHP capacity is
    # large enough that "where did this energy's emissions go" is a fair
    # question a reader could ask when comparing component totals.
    em_biomass_waste_chp = np.zeros(n)  # explicit zero, by convention (matches Granollers' DH treatment)

    total_emissions_kt = em_transport + em_other + em_elec_prod + em_elec_imp + em_dh

    # Backward-compatible aliases used elsewhere in this codebase / the dashboard
    emissions_electricity_dh = em_elec_prod + em_elec_imp + em_dh
    emissions_direct_combustion_kt = em_transport + em_other
    emissions_fossil_power = em_elec_prod
    emissions_import = em_elec_imp

    # --- Battery storage (informational, capacity trajectory only) ---
    battery_capacity_mwh = elec_capacity.get("Battery", np.zeros(n))

    # --- Grid connection / hosting capacity ---
    grid_connection_capacity = elec_capacity.get("Grid Connection", np.zeros(n))

    return {
        "years": years,
        "power_pv": power_pv,
        "power_biomass_chp_el": power_biomass_chp_el,
        "power_waste_chp_el": power_waste_chp_el,
        "power_fossil": power_fossil,
        "power_total": power_total,
        "net_imported_electricity": net_imported_elec,
        "total_electricity_demand": total_elec_demand,
        "total_heat_supply": total_heat_supply,
        "heat_biomass_chp": heat_biomass_chp,
        "heat_waste_chp": heat_waste_chp,
        "heat_gas": heat_gas,
        "heat_oil": heat_oil,
        "heat_pump": heat_hp,
        "heat_electric_boiler": heat_eb,
        "dh_electricity_demand": dh_elec_demand,
        "grid_emission_factor": grid_ef,
        # Granollers-matched 5-component breakdown (directly comparable)
        "em_transport": em_transport,
        "em_other": em_other,
        "em_elec_prod": em_elec_prod,
        "em_elec_imp": em_elec_imp,
        "em_dh": em_dh,
        "em_biomass_waste_chp_zero": em_biomass_waste_chp,
        "total_emissions_kt": total_emissions_kt,
        # Backward-compatible aliases (used by existing dashboard/scripts)
        "emissions_fossil_power_kt": emissions_fossil_power,
        "emissions_import_kt": emissions_import,
        "emissions_electricity_dh_kt": emissions_electricity_dh,
        "emissions_direct_combustion_kt": emissions_direct_combustion_kt,
        "battery_capacity_mwh": battery_capacity_mwh,
        "grid_connection_capacity_mw": grid_connection_capacity,
        "pv_capacity_mwp": pv_capacity_now,
    }


if __name__ == "__main__":
    from city_config import TALLINN
    from mobility import run_mobility
    from energy_demand import run_energy_demand

    mob = run_mobility(TALLINN, pi_scenario=1.0)
    ed = run_energy_demand(TALLINN, mob, pkm_method="centroid")
    es = run_energy_supply(TALLINN, ed)

    idx = [0, 11, 21, 31]
    print("Years:", es["years"][idx])
    print("Total electricity demand (GWh):", np.round(es["total_electricity_demand"][idx], 1))
    print("Net imported electricity (GWh):", np.round(es["net_imported_electricity"][idx], 1))
    print("PV power (GWh):", np.round(es["power_pv"][idx], 1))
    print("Fossil power (GWh):", np.round(es["power_fossil"][idx], 1))
    print("Grid emission factor (kg/kWh):", np.round(es["grid_emission_factor"][idx], 3))
    print("\n--- Emissions breakdown (Granollers-matched 5 components + Tallinn extension) ---")
    print("1) em_transport (direct, transport fossil):", np.round(es["em_transport"][idx], 1))
    print("2) em_other (direct, buildings/industry/services fossil):", np.round(es["em_other"][idx], 1))
    print("3) em_elec_prod (local fossil power):", np.round(es["em_elec_prod"][idx], 1))
    print("4) em_elec_imp (grid import):", np.round(es["em_elec_imp"][idx], 1))
    print("5) em_dh (district heating fossil -- TALLINN ONLY, =0 for Granollers):", np.round(es["em_dh"][idx], 1))
    print("   em_biomass_waste_chp (explicit zero, TALLINN ONLY):", np.round(es["em_biomass_waste_chp_zero"][idx], 1))
    print("TOTAL emissions (kt CO2):", np.round(es["total_emissions_kt"][idx], 1))
    print("PV capacity (MWp):", np.round(es["pv_capacity_mwp"][idx], 1))
    print("Battery capacity (MWh):", np.round(es["battery_capacity_mwh"][idx], 1))
