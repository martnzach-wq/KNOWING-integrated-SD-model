"""
build_naples_d34a_xlsx.py

Generates the Naples data files from the published KNOWING Deliverable D3.4a
(CIC2a Naples, final, PU), replacing the estimates of build_naples_xlsx.py:

    EN_MEADCityInput_Naples_D34a.xlsx   (sheet CETS, GWh/year)
    Supply_Data_Naples.xlsx             (sheet ES_inputs, MW / GWh)

The CETS rows are reconstructed with the rules of build_southwestphalia_xlsx.py
(see there); Naples-specific inputs:

  A13  Table A-13 Energy balance 2019, sector x fuel
  A15  Table A-15 Key measures 2019/2050 (end-use shares, load factor)
  A16  Table A-16 KPIs 2019-2050: population, FE/cap, EL/cap, HH-FE/cap, HH-EL/cap
  A62  Figure A-62 CETS final energy by sector, labelled shares for every keyframe
  A20  Table A-20 Core electricity demand by end use, 2019 and 2050
  A21  Table A-21 Core district heating demand, 2050
  A22  Table A-22 Hydrogen demand, 2050
  A19, A24, A25, A26  IESopt capacities and generation, 2019 and NY 2050

Household end uses 2019: space-heating electricity (201 GWh) and cooling
(35 GWh) from A20; firewood entirely space heating; 70 % of fossil fuels and
30 % of solar thermal to space heating (rule of build_southwestphalia_xlsx.py).
Agriculture, construction and mining (A13 one row) are split 50/50.

A draft MAED-City CETS export for Naples (not final) was used only to check
the reconstruction (docs/causal/demonstrator_calibration_targets.md in the
regsim repository).
"""

from __future__ import annotations

import numpy as np
import openpyxl

from build_southwestphalia_xlsx import KEYFRAMES, ROW_LABELS, _mix

POP = {2019: 0.9543, 2030: 0.8988, 2035: 0.8895, 2040: 0.8804, 2045: 0.8714, 2050: 0.8625}
FE_CAP = {2019: 9.59, 2030: 8.80, 2035: 8.31, 2040: 7.71, 2045: 7.32, 2050: 6.82}
EL_CAP = {2019: 2.63, 2030: 3.42, 2035: 3.72, 2040: 4.01, 2045: 4.24, 2050: 4.39}
HH_FE_CAP = {2019: 3.32, 2030: 3.09, 2035: 2.93, 2040: 2.73, 2045: 2.58, 2050: 2.32}
HH_EL_CAP = {2019: 0.965, 2030: 1.300, 2035: 1.368, 2040: 1.407, 2045: 1.446, 2050: 1.390}
# A62 labelled sector shares (passenger, freight, household, service, manufacturing, construction & mining, agriculture)
A62 = {
    2019: (0.39, 0.015, 0.35, 0.19, 0.044, 0.004, 0.004),
    2025: (0.37, 0.02, 0.35, 0.21, 0.05, 0.005, 0.005),
    2027: (0.35, 0.02, 0.35, 0.22, 0.05, 0.005, 0.005),
    2030: (0.34, 0.02, 0.35, 0.22, 0.05, 0.01, 0.01),
    2035: (0.31, 0.01, 0.35, 0.25, 0.06, 0.01, 0.01),
    2040: (0.27, 0.01, 0.35, 0.28, 0.07, 0.01, 0.01),
    2045: (0.24, 0.01, 0.35, 0.31, 0.07, 0.01, 0.01),
    2050: (0.20, 0.01, 0.34, 0.35, 0.08, 0.01, 0.01),
}
FE_BARS = {2025: 8350.0, 2027: 8100.0}  # A62 bar heights (GWh)
# aggregate fossil-thermal share (A60 by fuel): 22 % -> 15 % (2030) -> 8 % (2040) -> 4 % (2045) -> ~1 % (2050)
FOSSIL_SHARE_NAPLES = {2019: 0.22, 2025: 0.20, 2027: 0.19, 2030: 0.15, 2035: 0.12, 2040: 0.08, 2045: 0.04, 2050: 0.0}

HH_2019 = {"fossil": 1295.4 + 72.7, "dh": 0.0, "el": 920.8, "solar": 2.1, "bio": 839.9 + 42.5}
SERV_2019 = {"fossil": 498.0, "dh": 0.0, "el": 1269.2, "solar": 1.16, "bio": 10.06 + 2.5}
MANUF_2019 = {"fossil": 151.5 + 4.3, "dh": 0.0, "el": 224.7, "bio": 8.2 + 3.4, "h2": 0.0}
ACM_2019 = 15.4 + 3.6 + 30 + 24.9 + 1.77 + 0.9  # agriculture, construction, mining


def _interp(points: dict, year: float) -> float:
    xs = sorted(points)
    return float(np.interp(year, xs, [points[x] for x in xs]))


def build_cets():
    import build_southwestphalia_xlsx as swf

    swf.FOSSIL_SHARE = FOSSIL_SHARE_NAPLES  # the shared mix rule follows Naples' fossil index
    pop = {y: _interp(POP, y) * 1e6 for y in KEYFRAMES}
    fe = {y: FE_BARS.get(y, _interp(FE_CAP, y) * pop[y] / 1000) for y in KEYFRAMES}
    hh_fe = {y: _interp(HH_FE_CAP, y) * pop[y] / 1000 for y in KEYFRAMES}
    hh_el = {y: _interp(HH_EL_CAP, y) * pop[y] / 1000 for y in KEYFRAMES}
    hh_2050_total, hh_2050_el = hh_fe[2050], hh_el[2050]
    hh_2050 = {"el": hh_2050_el, "dh": 246 + 20, "solar": 18.0, "fossil": 0.0}  # DH: A21; solar ~ 2019 level
    hh_2050["bio"] = hh_2050_total - sum(hh_2050.values())  # firewood and biofuel take the remainder
    serv_2050_total = A62[2050][3] * fe[2050]
    serv_2050 = {"dh": 80 + 27, "bio": 0.05 * serv_2050_total, "fossil": 0.0, "solar": 0.0}
    serv_2050["el"] = serv_2050_total - sum(serv_2050.values())
    manuf_2050_total = A62[2050][4] * fe[2050]
    manuf_2050 = {"el": 319.0, "dh": 2.0, "h2": 95.0, "fossil": 0.0}
    manuf_2050["bio"] = max(manuf_2050_total - sum(manuf_2050.values()), 0.0)
    rows = {k: [] for k in ROW_LABELS}
    for y in KEYFRAMES:
        sh = A62[y]
        serv, manuf, freight = sh[3] * fe[y], sh[4] * fe[y], sh[1] * fe[y]
        hh_mix = _mix({k: v for k, v in HH_2019.items() if k != "el"}, {k: v for k, v in hh_2050.items() if k != "el"}, y)
        nonel = {k: s * (hh_fe[y] - hh_el[y]) for k, s in hh_mix.items()}
        w = (y - 2019) / 31
        cool = (1 - w) * 35 + w * 32
        sh_el = (1 - w) * 201 + w * 439
        dh_sh_frac = 246 / 266  # A21: space heating share of household district heat
        sp = {"el": sh_el, "dh": nonel["dh"] * dh_sh_frac, "bio": nonel["bio"] * ((1 - w) * 0.952 + w * 0.9),
              "solar": nonel["solar"] * 0.3, "fossil": nonel["fossil"] * 0.70}  # fmt: skip
        other = {k: nonel[k] - sp[k] for k in ("dh", "bio", "solar", "fossil")}
        other["el"] = hh_el[y] - sh_el - cool
        sm, mm = _mix(SERV_2019, serv_2050, y), _mix(MANUF_2019, manuf_2050, y)
        vals = {
            "EN_freight_tr_fuels": freight * _interp({2019: 0.90, 2050: 0.15}, y),
            "EN_freight Tr electr": freight * _interp({2019: 0.01, 2050: 0.60}, y),
            "EN_freight Tr_other": freight * _interp({2019: 0.09, 2050: 0.25}, y),
            "EN_finEN_hh_space heating_Biomass": sp["bio"],
            "EN_finEN_hh_space heating_Solar": sp["solar"],
            "EN_finEN_hh_space heating_DH": sp["dh"],
            "EN_finEN_hh_space heating_electr": sp["el"],
            "EN_finEN_hh_space heating_fossil fuel": sp["fossil"],
            "EN_finEN_hh_cooling_ac_electr": cool,
            "EN_finEN_hh_other_Biomass": other["bio"],
            "EN_finEN_hh_other_Solar": other["solar"],
            "EN_finEN_hh_other_DH": other["dh"],
            "EN_finEN_hh_other_electr": other["el"],
            "EN_finEN_hh_other_fossil fuel": other["fossil"],
            "EN_finEN_Manufacturing": manuf,
            "EN_finEN_Agriculture": sh[6] * fe[y] if y > 2019 else ACM_2019 / 2,
            "EN_finEN_Construction": sh[5] * fe[y] if y > 2019 else ACM_2019 / 2,
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
            "EN_finEN_Passenger transport (residual)": sh[0] * fe[y],
            "Electricity total (T12)": _interp(EL_CAP, y) * pop[y] / 1000,
            "Cooling Degree Days": _interp({2019: 326, 2050: 610}, y),
            "Heating Degree Days": _interp({2019: 544, 2050: 540}, y),
        }
        for k in ROW_LABELS:
            rows[k].append(vals[k])
    return rows, KEYFRAMES


SUPPLY = [
    ("ES ElectricityCapacity", "PV", 226, 899, "A19 / A24"),
    ("ES ElectricityCapacity", "Wind", 0, 252, "A24 (near-offshore)"),
    ("ES ElectricityCapacity", "Biomass CHP el", 0, 2, "A24"),
    ("ES ElectricityCapacity", "Grid Connection", 1750, 1750, "A24"),
    ("ES ElectricityCapacity", "Battery", 43, 169, "A24"),
    ("ES ElectricityCapacity", "Fuel Oil PP", 143, 0, "A24"),
    ("ES ElectricityCapacity", "Natural Gas CHP el", 628, 0, "A24 natural gas PP (A19: CC 517 + steam 110 MW)"),
    ("ES ElectrictitySupply", "PV", 229, 860, "A24"),
    ("ES ElectrictitySupply", "Wind", 0, 787, "A24"),
    ("ES ElectrictitySupply", "Biomass CHP el", 0, 0, "A24 (~0)"),
    ("ES ElectrictitySupply", "Grid Connection", -571, 2442, "A24: net export 571 GWh in 2019, import 2442 GWh in 2050"),
    ("ES ElectrictitySupply", "Battery", 0, 106, "A24 discharge"),
    ("ES ElectrictitySupply", "Fuel Oil PP", 778, 0, "A24"),
    ("ES ElectrictitySupply", "Natural Gas CHP el", 2078, 0, "A24 (A19: 2032 + 465 GWh)"),
    ("ES HeatCapacity", "Biomass CHP", 0, 6, "A25"),
    ("ES HeatCapacity", "DH Electric Boiler", 0, 63, "A25"),
    ("ES HeatCapacity", "DH Heat Pump", 0, 169, "A25"),
    ("ES HeatCapacity", "DH Geothermal", 0, 62, "A25"),
    ("ES HeatCapacity", "Electrolyzer", 0, 33, "A26 (MW H2)"),
    ("ES HeatSupply", "Biomass CHP", 0, 0, "A25 (~0)"),
    ("ES HeatSupply", "DH Electric Boiler", 0, 36, "A25"),
    ("ES HeatSupply", "DH Heat Pump", 0, 81, "A25"),
    ("ES HeatSupply", "DH Geothermal", 0, 266, "A25"),
    ("ED CoreElectricityDemand", None, 2514, 3789, "A20"),
    ("ED CoreHeatDemand", None, 0, 383, "A21"),
    ("ES ElDemand DH EB", None, 0, 37, "A24"),
    ("ES ElDemand DH HP", None, 0, 21, "A24"),
    ("ES ElDemand Electrolyser", None, 0, 157, "A24"),
    ("ED CoreH2Demand", None, 0, 99, "A22"),
]


def write(cets_path="EN_MEADCityInput_Naples_D34a.xlsx", supply_path="Supply_Data_Naples.xlsx"):
    rows, years = build_cets()
    wb = openpyxl.Workbook()
    wb.active.title = "readMe"
    for line in __doc__.strip().splitlines():
        wb.active.append([line])
    ws = wb.create_sheet("CETS")
    ws.append(["Time", *years])
    for label in ROW_LABELS:
        ws.append([label, *[round(v, 3) for v in rows[label]]])
    wb.save(cets_path)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ES_inputs"
    ws.append(["Time", None, 2019, 2050])
    for cat, item, v19, v50, _ in SUPPLY:
        ws.append([cat, item, v19, v50])
    prov = wb.create_sheet("provenance")
    prov.append(["category", "item", "source (D3.4a)"])
    for cat, item, _, _, src in SUPPLY:
        prov.append([cat, item, src])
    wb.save(supply_path)


if __name__ == "__main__":
    write()
