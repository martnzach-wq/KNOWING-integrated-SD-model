"""
energy_demand.py

Reads the MAED-City CETS lookup table (EN_MEADCityInput.xlsx) and combines
it with the mobility submodel's transport distance output to produce final
energy demand by sector, 2019-2050.

Architecture decision (confirmed explicitly):
    - All non-transport CETS rows (household heating/cooling/other,
      manufacturing, agriculture, construction, services, industry) are
      read as-is from the XLSX via linear interpolation between keyframe
      years -- this mirrors Vensim's GET XLS LOOKUP behaviour.
    - The four transport distance rows (Dist car fuel Tr, Dist eletr Tr,
      Dist publ Tr, Dist other Tr) in the STATIC XLSX are NOT used for
      energy computation. They represent the standalone (pre-mobility-
      coupling) demand model's own placeholder assumptions (e.g. zero EV
      distance throughout) and are superseded by the mobility submodel's
      dynamic, PI-dependent output once the two submodels are integrated.
    - Transport final energy (EN_Cars fuels/electr, EN_Publ trans electr,
      EN_Other fuels) is RECOMPUTED from mobility output x city-specific
      conversion factors (kWh/km or kWh/pkm), evidence-based and sourced
      per city -- the XLSX's own EN_finE_conv_* rows are not used because
      they were found to be internally inconsistent with the XLSX's own
      EN_Cars fuels/electr rows (back-calculated circular dependency, the
      same issue flagged in project history for Granollers).
"""

from __future__ import annotations
import numpy as np
import openpyxl
from city_config import CityConfig, YEARS


CETS_ROWS = {
    "freight_fossil": "EN_freight_tr_fuels",
    "freight_electric": "EN_freight Tr electr",
    "freight_other": "EN_freight Tr_other",
    "hh_heating_biomass": "EN_finEN_hh_space heating_Biomass",
    "hh_heating_solar": "EN_finEN_hh_space heating_Solar",
    "hh_heating_dh": "EN_finEN_hh_space heating_DH",
    "hh_heating_electric": "EN_finEN_hh_space heating_electr",
    "hh_heating_fossil": "EN_finEN_hh_space heating_fossil fuel",
    "hh_cooling_electric": "EN_finEN_hh_cooling_ac_electr",
    "hh_other_biomass": "EN_finEN_hh_other_Biomass",
    "hh_other_solar": "EN_finEN_hh_other_Solar",
    "hh_other_dh": "EN_finEN_hh_other_DH",
    "hh_other_electric": "EN_finEN_hh_other_electr",
    "hh_other_fossil": "EN_finEN_hh_other_fossil fuel",
    "manufacturing": "EN_finEN_Manufacturing",
    "agriculture": "EN_finEN_Agriculture",
    "construction": "EN_finEN_Construction",
    "service_total_legacy": "EN_finEN_Service",  # superseded by split rows below where available
    "population": "Population",
    "service_electric": "EN_finEN_Service electr",
    "service_dh": "EN_finEN_Service DH",
    "industry_electric": "EN_finEN_Industry_elctr",
    "industry_dh": "EN_finEN_Industry_DH",
    "service_fossil": "EN_finEN_Service fossil",
    "industry_fossil": "EN_finEN_Industry fossil",
}

KEYFRAME_YEARS = [2019, 2025, 2027, 2030, 2035, 2040, 2045, 2050]


def _read_cets_sheet(xlsx_path: str, sheet_name: str = "CETS") -> dict:
    """Read all labelled rows from the CETS sheet into {label: [values]}."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb[sheet_name]
    data = {}
    for row in ws.iter_rows(values_only=True):
        label = row[0]
        if label is None:
            continue
        values = [v for v in row[1:1 + len(KEYFRAME_YEARS)]]
        data[label] = values
    return data


def _interp_to_annual(keyframe_values, years=YEARS):
    return np.interp(years, KEYFRAME_YEARS, keyframe_values)


class TallinnConversionFactors:
    """
    Evidence-based transport energy conversion factors for Tallinn /
    Estonia, replacing the internally-inconsistent EN_finE_conv_* rows in
    the static XLSX.

    Sources (web research, documented inline):
      - car fossil: Estonia new-car fuel consumption is on the higher end
        of the EU (>6 l/100km, ODYSSEE-MURE 2023); fleet average (incl.
        older vehicles) assumed ~1.3x new-car figure -> 7.8 l/100km,
        blended petrol/diesel energy content ~9.6 kWh/l
        => ~0.75 kWh/km
      - car electric: cold-climate annual-average EV consumption (emobpy
        empirical study, Nordic-representative) 22.2 kWh/100km
        (20.7 summer / 23.6 winter) => 0.222 kWh/km
      - public transport internal (tram/trolleybus/bus, Tallinn fleet,
        fare-free since 2013): blended 0.040 kWh/pkm (tram 0.047,
        electric bus 0.033 kWh/km per passenger, generic urban-transport
        efficiency study)
      - public transport origin-destination (Elron commuter rail):
        0.050 kWh/pkm (modern electric train, generic efficiency study)
      - freight: NOT recomputed from mobility (freight has no submodel
        coupling in this framework); freight rows are read as-is from the
        CETS sheet, consistent with the Granollers precedent of treating
        freight electrification trajectories with separate fleet-stock
        logic rather than the same per-pkm conversion approach.
    """
    car_fossil_kwh_per_km = 0.749
    car_electric_kwh_per_km = 0.222
    pt_internal_kwh_per_pkm = 0.040
    pt_od_kwh_per_pkm = 0.050
    other_transport_kwh_per_km = 0.10  # placeholder for "other" (motorcycles etc.), low share


def run_energy_demand(city: CityConfig, mobility_results: dict,
                       pkm_method: str = "centroid",
                       conversion_factors=TallinnConversionFactors):
    """
    mobility_results: output of mobility.run_mobility(city, pi_scenario)
    Returns a dict of annual final-energy series (GWh) by category.
    """
    raw = _read_cets_sheet(city.energy_demand.xlsx_path, city.energy_demand.sheet_name)

    def series(key):
        label = CETS_ROWS[key]
        if label not in raw:
            return np.zeros(len(YEARS))
        return _interp_to_annual(raw[label])

    out = {"years": np.array(YEARS)}

    # --- Non-transport sectors: read as-is from XLSX ---
    out["hh_heating_biomass"] = series("hh_heating_biomass")
    out["hh_heating_solar"] = series("hh_heating_solar")
    out["hh_heating_dh"] = series("hh_heating_dh")
    out["hh_heating_electric"] = series("hh_heating_electric")
    out["hh_heating_fossil"] = series("hh_heating_fossil")
    out["hh_cooling_electric"] = series("hh_cooling_electric")
    out["hh_other_biomass"] = series("hh_other_biomass")
    out["hh_other_solar"] = series("hh_other_solar")
    out["hh_other_dh"] = series("hh_other_dh")
    out["hh_other_electric"] = series("hh_other_electric")
    out["hh_other_fossil"] = series("hh_other_fossil")
    out["manufacturing"] = series("manufacturing")
    out["agriculture"] = series("agriculture")
    out["construction"] = series("construction")
    out["service_electric"] = series("service_electric")
    out["service_dh"] = series("service_dh")
    out["service_fossil"] = series("service_fossil")
    out["industry_electric"] = series("industry_electric")
    out["industry_dh"] = series("industry_dh")
    out["industry_fossil"] = series("industry_fossil")
    out["population"] = series("population")

    # --- Freight: read as-is (no mobility-submodel coupling for freight) ---
    out["freight_fossil"] = series("freight_fossil")
    out["freight_electric"] = series("freight_electric")
    out["freight_other"] = series("freight_other")

    # --- Passenger transport: RECOMPUTED from mobility submodel output ---
    if pkm_method not in mobility_results:
        pkm_method = "centroid"
    mob = mobility_results[pkm_method]
    pop = out["population"]

    car_fossil_km_cap = mob["dist_car_fossil_km_cap_yr"]
    car_electric_km_cap = mob["dist_car_electric_km_cap_yr"]
    pt_km_cap = mob["dist_pt_km_cap_yr"]
    active_km_cap = mob["dist_active_km_cap_yr"]

    cf = conversion_factors
    out["transport_car_fossil"] = car_fossil_km_cap * pop * cf.car_fossil_kwh_per_km / 1e6  # GWh
    out["transport_car_electric"] = car_electric_km_cap * pop * cf.car_electric_kwh_per_km / 1e6
    # PT: approximate split internal/OD by the mobility model's own internal/OD
    # PT mode share -- using a single blended factor for simplicity here,
    # weighted toward the internal (tram/bus) rate since the bulk of
    # passenger-km in the aggregate dist_pt_km_cap_yr series is internal
    # trips (see mobility.py modal split output for the precise internal/OD
    # breakdown if a finer split is later required).
    pt_factor_blended = 0.6 * cf.pt_internal_kwh_per_pkm + 0.4 * cf.pt_od_kwh_per_pkm
    out["transport_pt_electric"] = pt_km_cap * pop * pt_factor_blended / 1e6
    out["transport_other"] = (out["freight_other"] * 0)  # placeholder, "other Tr" not separately modelled

    out["transport_active_km_cap"] = active_km_cap  # informational, zero energy

    # --- Totals ---
    out["total_hh_heating"] = (out["hh_heating_biomass"] + out["hh_heating_solar"]
                                + out["hh_heating_dh"] + out["hh_heating_electric"]
                                + out["hh_heating_fossil"])
    out["total_hh_other"] = (out["hh_other_biomass"] + out["hh_other_solar"]
                              + out["hh_other_dh"] + out["hh_other_electric"]
                              + out["hh_other_fossil"])
    out["total_households"] = out["total_hh_heating"] + out["total_hh_other"] + out["hh_cooling_electric"]
    out["total_industry"] = out["manufacturing"] + out["agriculture"] + out["construction"] \
        + out["industry_electric"] + out["industry_dh"] + out["industry_fossil"]
    out["total_services"] = out["service_electric"] + out["service_dh"] + out["service_fossil"]
    out["total_transport"] = (out["transport_car_fossil"] + out["transport_car_electric"]
                               + out["transport_pt_electric"] + out["transport_other"]
                               + out["freight_fossil"] + out["freight_electric"] + out["freight_other"])
    out["total_final_energy"] = (out["total_households"] + out["total_industry"]
                                  + out["total_services"] + out["total_transport"])

    # --- Aggregate by carrier (feeds ED CoreElectricityDemand / ED CoreHeatDemand
    # for the energy supply submodel) ---
    out["ED_CoreElectricityDemand"] = (
        out["hh_heating_electric"] + out["hh_cooling_electric"] + out["hh_other_electric"]
        + out["service_electric"] + out["industry_electric"]
        + out["transport_car_electric"] + out["transport_pt_electric"] + out["freight_electric"]
    )
    out["ED_CoreHeatDemand"] = out["hh_heating_dh"] + out["hh_other_dh"] + out["service_dh"] + out["industry_dh"]

    return out


if __name__ == "__main__":
    from city_config import TALLINN
    from mobility import run_mobility

    mob = run_mobility(TALLINN, pi_scenario=1.0)
    ed = run_energy_demand(TALLINN, mob, pkm_method="centroid")
    idx = [0, 11, 21, 31]
    print("Years:", ed["years"][idx])
    print("Total final energy (GWh):", np.round(ed["total_final_energy"][idx], 1))
    print("  households:", np.round(ed["total_households"][idx], 1))
    print("  industry:", np.round(ed["total_industry"][idx], 1))
    print("  services:", np.round(ed["total_services"][idx], 1))
    print("  transport:", np.round(ed["total_transport"][idx], 1))
    print("ED_CoreElectricityDemand:", np.round(ed["ED_CoreElectricityDemand"][idx], 1))
    print("ED_CoreHeatDemand:", np.round(ed["ED_CoreHeatDemand"][idx], 1))
