"""
build_southwestphalia_xlsx.py

Generates the two data files for the South Westphalia (SWF) demonstrator
from the published KNOWING Deliverable D3.5 (South Westphalia, final, PU):

    EN_MEADCityInput_SouthWestphalia.xlsx   (sheet CETS, GWh/year)
    Supply_Data_SouthWestphalia.xlsx        (sheet ES_inputs, MW / GWh)

Both mirror the structure of the existing city files (CETS sheet of
EN_MEADCityInput*.xlsx; ES_inputs sheet of Supply_Data_Tallinn.xlsx) and
carry a "provenance" sheet listing the source of every input value.

The deliverable reports MAED-City results as a base-year energy balance
(sector x fuel), key indicators for 2030-2050 and end-use tables for 2050,
not as the full CETS keyframe table. The CETS rows are therefore
RECONSTRUCTED from the published values with the rules below; the file
should be replaced by the MAED-City CETS export for SWF when available.

SOURCES (D3.5 page numbers of the report):
  T9   Table 9  Energy balance of SWF 2019, sector x fuel (p. 31)
  T11  Table 11 Key measures BAU/CETS 2019/2050 (pp. 40-41)
  T12  Table 12 KPIs of the CETS 2019-2050: population, FE/cap, EL/cap,
                HH-FE/cap, HH-EL/cap (p. 42)
  T13  Table 13 CDD/HDD base year, CETS 2050, CETS-HW 2050 (p. 43)
  F22  Figure 22 CETS final energy by sector (labelled shares) (p. 39)
  T15  Table 15 Installed capacity and generation 2019 (p. 47)
  T16  Table 16 Core electricity demand by end use, 2019 and 2050 (p. 49)
  T17  Table 17 Core district heating demand by end use (p. 50)
  T18  Table 18 Hydrogen demand 2050 (p. 51)
  T20  Table 20 Electricity demand, generation, capacity 2019/2050 NY (p. 55)
  T21  Table 21 District heating demand, generation, capacity (p. 57)
  TXT  Section 5.3.3.3 text: 2050 carrier shares within sectors

RECONSTRUCTION RULES (CETS):
  1. 2019 values are taken from T9; mining is added to manufacturing
     (F22 shows no separate mining sector).
  2. Household end-use split 2019: space-heating electricity from T16
     (220 GWh), space-heating district heat from T17 (442 GWh, consistent
     with the 6.7 % DH share of space heating in T11), cooling from T16
     (7.9 GWh); firewood entirely space heating; solar thermal 30 % space
     heating; remaining fossil fuels (hot water, cooking) to "other".
     T17's residential hot-water DH (510 GWh) exceeds the household DH
     total of T9 (450 GWh) and is not used.
  3. 2050 values: electricity by end use from T16, district heat from
     T17, hydrogen from T18; household totals from T12; biofuel and DH
     shares of manufacturing, households and services from TXT; fossil
     fuels zero (TXT: phase-out of thermal fossil fuels by 2050).
  4. Keyframe years 2030, 2035, 2040, 2045: total final energy and
     household final energy and electricity from T12 (exact). Sector
     totals of services and manufacturing follow the F22 shares
     (2030, 2040, 2050; 2035 and 2045 interpolated). Freight and
     agriculture + construction are read from the bar heights of F22.
     Carrier shares within a sector are interpolated linearly between
     2019 and 2050, except fossil fuels, which follow the aggregate
     fossil share of F22 (41 % -> 30 % -> 14 % -> 0.2 % (2046) -> 0 %).
  5. 2025 and 2027 are interpolated between 2022 (F22 ~ 2019 level) and
     2030.
  6. Rows that the current energy_demand.py does not read (biofuel and
     hydrogen of industry and services) are written as additional rows
     so that the sector totals are complete.

SUPPLY (ES_inputs): 2019 from T15 / T20 "Base Year", 2050 from T20 / T21
"NY 2050". Two capacity/generation pairs in T15 are inconsistent with
their capacities (gas CHP 375 GWhe from 10 MWe; biomethane CHP 333 GWhe
from 13.9 MWe); the T20 values (38 and 33 GWhe) are used.
"""

from __future__ import annotations

import numpy as np
import openpyxl

KEYFRAMES = [2019, 2025, 2027, 2030, 2035, 2040, 2045, 2050]

# --- T12: KPIs of the CETS ----------------------------------------------------
T12_YEARS = [2019, 2030, 2035, 2040, 2045, 2050]
POP = [1.382, 1.331, 1.308, 1.287, 1.276, 1.265]  # million
FE_CAP = [35.70, 31.36, 28.76, 26.45, 24.52, 23.60]  # MWh/cap
EL_CAP = [5.79, 8.19, 9.78, 11.38, 12.97, 13.35]
HH_FE_CAP = [8.20, 7.01, 6.30, 5.60, 4.60, 4.13]
HH_EL_CAP = [1.82, 2.31, 2.44, 2.50, 2.54, 2.39]

# --- F22: aggregate fossil-thermal share and sector shares (CETS) ------------
FOSSIL_SHARE = {2019: 0.41, 2022: 0.40, 2030: 0.30, 2040: 0.14, 2046: 0.002, 2050: 0.0}
SERVICE_SHARE = {2019: 0.099, 2030: 0.11, 2040: 0.13, 2050: 0.15}
MANUF_SHARE = {2019: 0.316, 2030: 0.33, 2040: 0.39, 2050: 0.46}  # incl. mining
FREIGHT_GWH = {2019: 2120.0, 2030: 1800.0, 2040: 1200.0, 2050: 800.0}  # bar heights, +-200
AGRI_GWH = {2019: 580.3, 2030: 750.0, 2040: 1000.0, 2050: 1300.0}  # bar heights, +-300
CONSTR_GWH = {2019: 169.0, 2030: 450.0, 2040: 750.0, 2050: 1050.0}  # bar heights, +-300

# --- T9: 2019 balance (GWh) ---------------------------------------------------
HH_2019 = {"fossil": 5673.2 + 1982.2 + 24.6, "dh": 450.1, "el": 2517.5, "solar": 67.1, "bio": 618.1}
SERV_2019 = {"fossil": 1409.9 + 989.6 + 0.7 + 431.5 + 16.5, "dh": 596.0, "el": 1298.8, "solar": 2.2, "bio": 143.6}
MANUF_2019 = {  # manufacturing + mining
    "fossil": 5278.2 + 157.8 + 847.2 + 3548.1 + 201.6 + 317.7 + 18.4,
    "dh": 1142.5,
    "el": 3890.7 + 20.3,
    "bio": 35.6 + 141.3 + 2.5,
    "h2": 0.0,
}

# --- 2050 targets (T16, T17, T18, T12, TXT) ----------------------------------
HH_2050_TOTAL = HH_FE_CAP[-1] * POP[-1] * 1000  # GWh
HH_2050 = {"el": HH_EL_CAP[-1] * POP[-1] * 1000, "dh": 0.21 * HH_2050_TOTAL, "bio": 0.20 * HH_2050_TOTAL, "fossil": 0.0}
HH_2050["solar"] = HH_2050_TOTAL - sum(HH_2050.values())
SERV_2050_TOTAL = SERVICE_SHARE[2050] * FE_CAP[-1] * POP[-1] * 1000
SERV_2050 = {"bio": 0.25 * SERV_2050_TOTAL, "dh": 0.17 * SERV_2050_TOTAL, "fossil": 0.0, "solar": 0.0}
SERV_2050["el"] = SERV_2050_TOTAL - sum(SERV_2050.values())
MANUF_2050 = {"el": 7213.0, "dh": 1467.0, "h2": 1048.0, "fossil": 0.0}
MANUF_2050["bio"] = 0.29 * MANUF_SHARE[2050] * FE_CAP[-1] * POP[-1] * 1000

# household end-use split (fractions of each carrier going to space heating)
HH_SH_FRACTION_2019 = {"el": 220 / HH_2019["el"], "dh": 442 / HH_2019["dh"], "bio": 1.0, "solar": 0.3}
HH_COOLING_2019, HH_COOLING_2050 = 7.9, 12.0  # T16
HH_SH_EL_2050 = 686.0  # T16
HH_SH_DH_2050 = 915.0  # T17


def _interp(points: dict, year: float) -> float:
    xs = sorted(points)
    return float(np.interp(year, xs, [points[x] for x in xs]))


def _fossil_ratio(year: float) -> float:
    return _interp(FOSSIL_SHARE, year) / FOSSIL_SHARE[2019]


def _mix(start: dict, end: dict, year: int) -> dict:
    """Carrier shares in a year: fossil follows the aggregate fossil index,
    the non-fossil carriers share the rest in linearly interpolated proportions."""
    s0 = {k: v / sum(start.values()) for k, v in start.items()}
    s1 = {k: v / sum(end.values()) for k, v in end.items()}
    w = (year - 2019) / (2050 - 2019)
    fossil = s0.get("fossil", 0.0) * _fossil_ratio(year)
    rest = {k: (1 - w) * s0.get(k, 0.0) + w * s1.get(k, 0.0) for k in set(s0) | set(s1) if k != "fossil"}
    scale = (1 - fossil) / sum(rest.values())
    return {"fossil": fossil, **{k: v * scale for k, v in rest.items()}}


def build_cets() -> tuple[dict, list]:
    pop = {y: _interp(dict(zip(T12_YEARS, POP, strict=True)), y) * 1e6 for y in KEYFRAMES}
    fe = {y: _interp(dict(zip(T12_YEARS, FE_CAP, strict=True)), y) * pop[y] / 1000 for y in KEYFRAMES}
    hh_fe = {y: _interp(dict(zip(T12_YEARS, HH_FE_CAP, strict=True)), y) * pop[y] / 1000 for y in KEYFRAMES}
    hh_el = {y: _interp(dict(zip(T12_YEARS, HH_EL_CAP, strict=True)), y) * pop[y] / 1000 for y in KEYFRAMES}
    for y in (2025, 2027):  # rule 5: 2022 at about the 2019 level (F22)
        w = (y - 2022) / 8
        fe[y] = (1 - w) * fe[2019] * 1.01 + w * fe[2030]
    rows = {k: [] for k in ROW_LABELS}
    for y in KEYFRAMES:
        serv = _interp(SERVICE_SHARE, y) * fe[y]
        manuf = _interp(MANUF_SHARE, y) * fe[y]
        # households: electricity exact (T12), other carriers by the mix rule
        hh_mix = _mix({k: v for k, v in HH_2019.items() if k != "el"}, {k: v for k, v in HH_2050.items() if k != "el"}, y)
        hh_other_carriers = {k: s * (hh_fe[y] - hh_el[y]) for k, s in hh_mix.items()}
        w = (y - 2019) / 31
        cool = (1 - w) * HH_COOLING_2019 + w * HH_COOLING_2050
        sh_el = (1 - w) * 220 + w * HH_SH_EL_2050
        sh_dh_frac = (1 - w) * HH_SH_FRACTION_2019["dh"] + w * HH_SH_DH_2050 / HH_2050["dh"]
        sh = {
            "el": sh_el,
            "dh": hh_other_carriers["dh"] * sh_dh_frac,
            "bio": hh_other_carriers["bio"] * ((1 - w) * 1.0 + w * 0.9),
            "solar": hh_other_carriers["solar"] * 0.3,
            "fossil": hh_other_carriers["fossil"] * 0.69,  # 2019 split of rule 2, kept constant
        }
        other = {k: hh_other_carriers[k] - sh[k] for k in ("dh", "bio", "solar", "fossil")}
        other["el"] = hh_el[y] - sh_el - cool
        sm = _mix(SERV_2019, SERV_2050, y)
        mm = _mix(MANUF_2019, MANUF_2050, y)
        vals = {
            "EN_freight_tr_fuels": _interp(FREIGHT_GWH, y) * _interp({2019: 0.95, 2050: 0.03}, y),
            "EN_freight Tr electr": _interp(FREIGHT_GWH, y) * _interp({2019: 0.01, 2050: 0.56}, y),
            "EN_freight Tr_other": _interp(FREIGHT_GWH, y) * _interp({2019: 0.04, 2050: 0.41}, y),
            "EN_finEN_hh_space heating_Biomass": sh["bio"],
            "EN_finEN_hh_space heating_Solar": sh["solar"],
            "EN_finEN_hh_space heating_DH": sh["dh"],
            "EN_finEN_hh_space heating_electr": sh["el"],
            "EN_finEN_hh_space heating_fossil fuel": sh["fossil"],
            "EN_finEN_hh_cooling_ac_electr": cool,
            "EN_finEN_hh_other_Biomass": other["bio"],
            "EN_finEN_hh_other_Solar": other["solar"],
            "EN_finEN_hh_other_DH": other["dh"],
            "EN_finEN_hh_other_electr": other["el"],
            "EN_finEN_hh_other_fossil fuel": other["fossil"],
            "EN_finEN_Manufacturing": manuf,
            "EN_finEN_Agriculture": _interp(AGRI_GWH, y),
            "EN_finEN_Construction": _interp(CONSTR_GWH, y),
            "EN_finEN_Service": serv,
            "Population": pop[y],
            "EN_finEN_Service electr": sm["el"] * serv,
            "EN_finEN_Service DH": sm["dh"] * serv,
            "EN_finEN_Service fossil": sm["fossil"] * serv,
            "EN_finEN_Service biofuel": sm["bio"] * serv,
            "EN_finEN_Service solar": sm.get("solar", 0.0) * serv,
            "EN_finEN_Industry_elctr": mm["el"] * manuf,
            "EN_finEN_Industry_DH": mm["dh"] * manuf,
            "EN_finEN_Industry fossil": mm["fossil"] * manuf,
            "EN_finEN_Industry biofuel": mm["bio"] * manuf,
            "EN_finEN_Industry H2": mm["h2"] * manuf,
            "EN_finEN_Total (T12)": fe[y],
            "EN_finEN_Passenger transport (residual)": fe[y]
            - serv
            - manuf
            - hh_fe[y]
            - _interp(FREIGHT_GWH, y)
            - _interp(AGRI_GWH, y)
            - _interp(CONSTR_GWH, y),
            "Electricity total (T12)": _interp(dict(zip(T12_YEARS, EL_CAP, strict=True)), y) * pop[y] / 1000,
            "Cooling Degree Days": _interp({2019: 21, 2050: 37}, y),
            "Heating Degree Days": _interp({2019: 2881, 2050: 2600}, y),
        }
        for k in ROW_LABELS:
            rows[k].append(vals[k])
    return rows, KEYFRAMES


ROW_LABELS = [
    "EN_freight_tr_fuels",
    "EN_freight Tr electr",
    "EN_freight Tr_other",
    "EN_finEN_hh_space heating_Biomass",
    "EN_finEN_hh_space heating_Solar",
    "EN_finEN_hh_space heating_DH",
    "EN_finEN_hh_space heating_electr",
    "EN_finEN_hh_space heating_fossil fuel",
    "EN_finEN_hh_cooling_ac_electr",
    "EN_finEN_hh_other_Biomass",
    "EN_finEN_hh_other_Solar",
    "EN_finEN_hh_other_DH",
    "EN_finEN_hh_other_electr",
    "EN_finEN_hh_other_fossil fuel",
    "EN_finEN_Manufacturing",
    "EN_finEN_Agriculture",
    "EN_finEN_Construction",
    "EN_finEN_Service",
    "Population",
    "EN_finEN_Service electr",
    "EN_finEN_Service DH",
    "EN_finEN_Service fossil",
    "EN_finEN_Service biofuel",
    "EN_finEN_Service solar",
    "EN_finEN_Industry_elctr",
    "EN_finEN_Industry_DH",
    "EN_finEN_Industry fossil",
    "EN_finEN_Industry biofuel",
    "EN_finEN_Industry H2",
    "EN_finEN_Total (T12)",
    "EN_finEN_Passenger transport (residual)",
    "Electricity total (T12)",
    "Cooling Degree Days",
    "Heating Degree Days",
]

PROVENANCE_CETS = [
    ("EN_freight_*", "F22 bar heights (+-200 GWh); carrier split: 2019 transport fuel mix of T9, 2050 electric-truck share of T11 and H2/biofuel remainder"),
    ("EN_finEN_hh_*", "rule 2 (2019) and rule 3 (2050); households total and electricity per year from T12"),
    ("EN_finEN_Manufacturing / Industry_*", "T9 incl. mining (2019); T16 E-Industry, T17 DH-Others, T18 H2-Industry, TXT biofuel 29 % (2050); F22 shares"),
    ("EN_finEN_Service*", "T9 (2019); TXT biofuel 25 %, DH 17 %, fossil 0 (2050); F22 shares"),
    ("EN_finEN_Agriculture / Construction", "T9 (2019); F22 bar heights (+-300 GWh)"),
    ("Population", "T12, interpolated for 2025 and 2027"),
    ("EN_finEN_Total (T12), Electricity total (T12)", "check rows, not read by energy_demand.py"),
    ("EN_finEN_Passenger transport (residual)", "check row: total minus all other sectors; T9 2019 passenger transport 14,636 GWh"),
    ("Cooling/Heating Degree Days", "T13 (CETS); CETS-HW 2050: CDD 74, HDD 2975"),
]

SUPPLY = [
    # category, item, 2019, 2050, source
    ("ES ElectricityCapacity", "PV", 992, 7003, "T15 roof+facade+field / T20"),
    ("ES ElectricityCapacity", "Wind", 893, 3250, "T15 / T20"),
    ("ES ElectricityCapacity", "Hydro Run-Of-River", 44, 46, "T20"),
    ("ES ElectricityCapacity", "Hydro Reservoir", 38, 38, "T20"),
    ("ES ElectricityCapacity", "Biomass CHP el", 110, 118, "T20"),
    ("ES ElectricityCapacity", "Waste CHP el", 13, 20, "T20"),
    ("ES ElectricityCapacity", "Biomethane CHP el", 14, 14, "T20"),
    ("ES ElectricityCapacity", "Grid Connection", 10750, 10750, "T20"),
    ("ES ElectricityCapacity", "Battery", 269, 269, "T20 (MW); T15 538.8 MWh"),
    ("ES ElectricityCapacity", "Fuel Cell el", 0, 0, "T19"),
    ("ES ElectricityCapacity", "Fuel Oil PP", 212, 0, "T20 fuel-oil CHP"),
    ("ES ElectricityCapacity", "Biogas PP", 0, 0, "-"),
    ("ES ElectricityCapacity", "Natural Gas CHP el", 10, 0, "T20"),
    ("ES ElectricityCapacity", "Peat CHP el", 21, 0, "T20 coal/peat CHP"),
    ("ES ElectrictitySupply", "PV", 930, 6719, "T20"),
    ("ES ElectrictitySupply", "Wind", 2230, 12999, "T20"),
    ("ES ElectrictitySupply", "Hydro Run-Of-River", 169, 245, "T20"),
    ("ES ElectrictitySupply", "Hydro Reservoir", 64, 199, "T20"),
    ("ES ElectrictitySupply", "Biomass CHP el", 698, 49, "T20"),
    ("ES ElectrictitySupply", "Waste CHP el", 108, 148, "T20"),
    ("ES ElectrictitySupply", "Biomethane CHP el", 33, 7, "T20 (T15: 333, inconsistent with 13.9 MWe)"),
    ("ES ElectrictitySupply", "Grid Connection", 3560, 4202, "T20 import"),
    ("ES ElectrictitySupply", "Battery", 0, 143, "T20 discharge"),
    ("ES ElectrictitySupply", "Fuel Cell el", 0, 0, "-"),
    ("ES ElectrictitySupply", "Fuel Oil PP", 413, 0, "T20"),
    ("ES ElectrictitySupply", "Biogas PP", 0, 0, "-"),
    ("ES ElectrictitySupply", "Natural Gas CHP el", 38, 0, "T20 (T15: 375, inconsistent with 10 MWe)"),
    ("ES ElectrictitySupply", "Peat CHP el", 64, 0, "T20"),
    ("ES HeatCapacity", "Waste CHP", 37, 65, "T21"),
    ("ES HeatCapacity", "DH Biomass Boiler", 0, 0, "T21"),
    ("ES HeatCapacity", "DH Electric Boiler", 0, 283, "T21"),
    ("ES HeatCapacity", "Electrolyzer", 0, 645, "T22 (MW H2)"),
    ("ES HeatCapacity", "Biomass CHP", 233, 295, "T21"),
    ("ES HeatCapacity", "Fuel Cell", 0, 0, "-"),
    ("ES HeatCapacity", "DH Heat Pump", 0, 805, "T21"),
    ("ES HeatCapacity", "Heat Storage", 0, 0, "not reported"),
    ("ES HeatCapacity", "Natural Gas CHP", 5, 0, "T21"),
    ("ES HeatCapacity", "Peat CHP", 21, 0, "T21"),
    ("ES HeatCapacity", "DH Natural Gas Boiler", 0, 0, "-"),
    ("ES HeatCapacity", "Biomethane CHP", 5, 6, "T21"),
    ("ES HeatCapacity", "DH Fuel Oil Boiler", 159, 0, "T21 fuel-oil CHP heat"),
    ("ES HeatSupply", "Waste CHP", 305, 495, "T21"),
    ("ES HeatSupply", "DH Biomass Boiler", 0, 0, "T21"),
    ("ES HeatSupply", "DH Electric Boiler", 0, 234, "T21"),
    ("ES HeatSupply", "Electrolyzer", 0, 0, "-"),
    ("ES HeatSupply", "Biomass CHP", 1480, 1094, "T21"),
    ("ES HeatSupply", "Fuel Cell", 0, 0, "-"),
    ("ES HeatSupply", "DH Heat Pump", 0, 1519, "T21"),
    ("ES HeatSupply", "Heat Storage", 0, 0, "-"),
    ("ES HeatSupply", "Natural Gas CHP", 18, 0, "T21"),
    ("ES HeatSupply", "Peat CHP", 64, 0, "T21"),
    ("ES HeatSupply", "DH Natural Gas Boiler", 0, 0, "-"),
    ("ES HeatSupply", "Biomethane CHP", 13, 12, "T21"),
    ("ES HeatSupply", "DH Fuel Oil Boiler", 310, 0, "T21 fuel-oil CHP heat"),
    ("ED CoreElectricityDemand", None, 8005, 16888, "T16"),
    ("ED CoreHeatDemand", None, 2190, 3353, "T17"),
    ("ES ElDemand DH EB", None, 0, 236, "T20"),
    ("ES ElDemand DH HP", None, 0, 389, "T20"),
    ("ES ElDemand Electrolyser", None, 0, 2621, "T20"),
    ("ED CoreH2Demand", None, 0, 1662, "T18"),
]


def write_cets(path: str = "EN_MEADCityInput_SouthWestphalia.xlsx") -> None:
    rows, years = build_cets()
    wb = openpyxl.Workbook()
    readme = wb.active
    readme.title = "readMe"
    for line in __doc__.strip().splitlines():
        readme.append([line])
    ws = wb.create_sheet("CETS")
    ws.append(["Time", *years])
    for label in ROW_LABELS:
        ws.append([label, *[round(v, 3) for v in rows[label]]])
    prov = wb.create_sheet("provenance")
    prov.append(["rows", "source"])
    for r in PROVENANCE_CETS:
        prov.append(list(r))
    wb.save(path)


def write_supply(path: str = "Supply_Data_SouthWestphalia.xlsx") -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ES_inputs"
    ws.append(["Time", None, 2019, 2050])
    for cat, item, v19, v50, _ in SUPPLY:
        ws.append([cat, item, v19, v50])
    prov = wb.create_sheet("provenance")
    prov.append(["category", "item", "source (D3.5)"])
    for cat, item, _, _, src in SUPPLY:
        prov.append([cat, item, src])
    wb.save(path)


if __name__ == "__main__":
    write_cets()
    write_supply()
    rows, years = build_cets()
    print("year  total(T12)  passenger(residual)  manufacturing  households  services")
    for i, y in enumerate(years):
        hh = sum(rows[k][i] for k in ROW_LABELS if k.startswith("EN_finEN_hh"))
        print(y, round(rows["EN_finEN_Total (T12)"][i]), round(rows["EN_finEN_Passenger transport (residual)"][i]),
              round(rows["EN_finEN_Manufacturing"][i]), round(hh), round(rows["EN_finEN_Service"][i]))  # fmt: skip
