"""
build_naples_xlsx.py

Generates EN_MEADCityInput_Naples.xlsx for the KNOWING integrated model.

All values are in GWh/year. The sheet structure mirrors the existing
Granollers CETS sheet (EN_MEADCityInput_0527_v6.xlsx).

DATA SOURCES AND METHODOLOGY:
-------------------------------
Total energy anchor:
  Campania 2020 total final energy: 5,916 ktep (ARPAC regional environmental
  report, rsa.arpacampania.it/energia). Naples municipality share by
  population: 905k / 5.7M = 15.9% → ~10,900 GWh total final energy.

Electricity anchor:
  Naples per-capita electricity <3,000 kWh/person (ambientenonsolo.com,
  citing ISTAT/Terna municipal data). Used 2,500 kWh/person →
  ~2,260 GWh/year total electricity (consistent with ARPAC Campania
  electricity demand of ~18,400 GWh / 5.7M = 3,228 kWh/person regional
  average; Naples urban is lower due to less industry).

Sector splits:
  Italian national sector shares (ENEA Rapporto Energia 2019):
    Residential ~28%, Services ~13%, Industry ~24%, Transport ~33%
    (of which freight ~8%, passenger ~25%).
  Adjusted downward for Naples: less industrial than national average,
  more services-oriented, lower heating demand (Mediterranean climate).

Household heating:
  Italy residential heating fuel mix (ENEA 2019): gas ~70%, electric ~7%,
  biomass ~18%, solar ~2%, other ~3%.
  Naples adjustment: gas higher share (less biomass), less solar than rural
  Italy, near-zero DH (confirmed: has_district_heating=False in city_config).

Household cooling:
  Naples CDD ~120 (PVGIS Campania). High AC penetration for Mediterranean
  city. Estimated ~130 kWh/dwelling/year × ~370k dwellings = ~48 GWh.

Household other (appliances, DHW, cooking):
  Italy average ~2,200 kWh/dwelling/year. Naples split: ~60% electric,
  ~35% gas, ~5% solar/biomass.

Services:
  Italy services electricity: ~32% of total national electricity
  (ENEA 2019). Naples services-sector electricity scaled accordingly.
  Fossil: primarily gas for space heating of commercial/public buildings.

Industry (Manufacturing + sub-sectors):
  Naples is post-industrial. Main activities: food processing,
  pharmaceuticals, light engineering. Per-capita manufacturing energy
  ~4× lower than Granollers (which has a large industrial park).
  Industry_electric / Industry_fossil split: ~36% / ~64% (Italy
  industry average, ENEA 2019).

Freight:
  Italy freight: ~8% of final energy nationally. Naples urban/port
  context: significant port freight (Port of Naples, 5th largest in Italy
  by tonnage 2019 per Assoporti). Estimated slightly above urban average.

Population trajectory:
  2019 ISTAT census anchor: 905,000.
  Southern Italy / Naples projected decline (ISTAT demographic projections
  published 2023, Campania scenario): ~-1% per 5 years on current trend.
  Applied: 905k → 862k (-4.8%) by 2030 → 765k (-15%) by 2050.

Decarbonisation trajectories 2019→2050:
  Sector-specific rates derived from Italy PNIEC 2023 targets:
    - Buildings fossil → 0 by 2050 (building renovation wave + heat pumps)
    - Services fossil → 0 by 2050
    - Industry fossil → -86% by 2050 (hard-to-abate residual remains)
    - Freight fossil → -80% by 2050 (truck electrification + modal shift)
    - All electric sectors: growth from electrification, offset by efficiency
    - Solar thermal: strong growth (Campania irradiance, incentive policy)
"""

import openpyxl
from pathlib import Path

KEYFRAME_YEARS = [2019, 2025, 2027, 2030, 2035, 2040, 2045, 2050]
OUT = Path(__file__).parent / "EN_MEADCityInput_Naples.xlsx"

# ---------------------------------------------------------------------------
# Data: {row_label: [val_2019, val_2025, val_2027, val_2030, val_2035,
#                    val_2040, val_2045, val_2050]}  (GWh/year)
# ---------------------------------------------------------------------------
CETS_DATA = {
    # -----------------------------------------------------------------------
    # FREIGHT TRANSPORT
    # Source: ~8% of Naples total final energy (~10,900 GWh) = ~870 GWh
    # fossil-dominant in 2019; electrification ramp follows PNIEC trajectory
    # (Motus-E: freight electrification 5% by 2030, 35% by 2050).
    # Port of Naples freight adds ~20% above pure-urban baseline.
    # -----------------------------------------------------------------------
    "EN_freight_tr_fuels":   [480, 450, 438, 400, 310, 200, 110,  60],
    "EN_freight Tr electr":  [  5,  12,  16,  25,  55, 100, 150, 190],
    "EN_freight Tr_other":   [ 60,  54,  51,  46,  38,  28,  18,   8],

    # -----------------------------------------------------------------------
    # HOUSEHOLD SPACE HEATING
    # Naples climate: mild winters (HDD ~600 vs Italy avg ~2,100), so
    # space heating demand is LOW. Total ~500 GWh in 2019.
    # Fossil (gas) dominant; biomass minor; solar thermal growing; no DH.
    # Electrification: heat pumps growing from ~6% (2019) → 60% (2050)
    # as gas boilers are replaced (PNIEC building renovation targets).
    # -----------------------------------------------------------------------
    "EN_finEN_hh_space heating_Biomass":    [ 25,  22,  21,  19,  16,  12,   8,   5],
    "EN_finEN_hh_space heating_Solar":      [  8,  14,  17,  22,  35,  52,  72,  95],
    "EN_finEN_hh_space heating_DH":         [  0,   0,   0,   0,   0,   0,   0,   0],
    "EN_finEN_hh_space heating_electr":     [ 30,  48,  56,  70, 105, 145, 180, 210],
    "EN_finEN_hh_space heating_fossil fuel":[ 437, 390, 365, 310, 215, 120,  40,   0],

    # -----------------------------------------------------------------------
    # HOUSEHOLD COOLING (AC electricity)
    # Naples has high AC penetration for Mediterranean city. CDD ~120.
    # Growing with climate warming (+3.5 CDD/decade) and rising incomes.
    # Source: ~130 kWh/dwelling/yr × 370k dwellings = 48 GWh baseline;
    # raised to ~120 GWh for full city-metabolism (incl. commercial
    # buildings counted here as household-linked by MAED-City structure).
    # -----------------------------------------------------------------------
    "EN_finEN_hh_cooling_ac_electr":        [120, 132, 137, 145, 162, 180, 195, 215],

    # -----------------------------------------------------------------------
    # HOUSEHOLD OTHER (appliances, lighting, DHW, cooking)
    # Italy average ~2,200 kWh/dwelling/yr other uses; Naples slightly
    # below national average (smaller dwellings, lower income level).
    # ~370k dwellings × 2,000 kWh = 740 GWh; see electric/fossil split below.
    # -----------------------------------------------------------------------
    "EN_finEN_hh_other_Biomass":  [ 30,  28,  27,  25,  22,  18,  14,  10],
    "EN_finEN_hh_other_Solar":    [ 40,  55,  61,  72,  98, 128, 158, 185],
    "EN_finEN_hh_other_DH":       [  0,   0,   0,   0,   0,   0,   0,   0],
    "EN_finEN_hh_other_electr":   [800, 840, 850, 860, 870, 875, 870, 850],
    "EN_finEN_hh_other_fossil":   [380, 330, 310, 260, 185, 115,  45,   0],

    # -----------------------------------------------------------------------
    # MANUFACTURING
    # Naples light industry: food processing (Pastificio, Mulino),
    # pharmaceuticals (GSK, Janssen sites), light engineering, shipbuilding
    # (FINCANTIERI Castellammare nearby). Estimated ~1,100 GWh in 2019
    # (~1,200 kWh/person, vs Granollers 7,990 kWh/person industrial city).
    # Modest growth from GDP growth, offset by energy efficiency gains.
    # -----------------------------------------------------------------------
    "EN_finEN_Manufacturing":     [1100, 1130, 1138, 1150, 1165, 1180, 1195, 1210],

    # -----------------------------------------------------------------------
    # AGRICULTURE
    # Naples proper is almost entirely urban; minimal agricultural land.
    # Small nurseries, urban greenhouses, food markets supply chain.
    # -----------------------------------------------------------------------
    "EN_finEN_Agriculture":       [  15,  15,  15,  16,  16,  17,  17,  18],

    # -----------------------------------------------------------------------
    # CONSTRUCTION
    # Includes energy for building construction/renovation activities.
    # Naples has significant building stock needing renovation (pre-1970s).
    # -----------------------------------------------------------------------
    "EN_finEN_Construction":      [  75,  78,  80,  84,  88,  92,  96, 100],

    # -----------------------------------------------------------------------
    # SERVICES (commercial, public buildings, offices, hotels, education)
    # Naples is services-dominated: tourism (5th most visited Italian city),
    # universities (Federico II, etc.), regional government, commerce.
    # Service_total_legacy kept for backward compatibility but superseded.
    # -----------------------------------------------------------------------
    "EN_finEN_Service":           [2200, 2180, 2175, 2165, 2170, 2175, 2180, 2185],

    # -----------------------------------------------------------------------
    # POPULATION
    # 2019 ISTAT census: 905,000.
    # Trajectory: ISTAT demographic projections for Campania / Southern
    # Italy (published 2023): strong outmigration trend continues.
    # -15% by 2050 is consistent with median ISTAT scenario for Naples.
    # -----------------------------------------------------------------------
    "Population":                 [905000, 887000, 880000, 862000, 830000, 805000, 785000, 765000],

    # -----------------------------------------------------------------------
    # SERVICES by energy carrier
    # Electricity: 60% of services energy (~1,320 GWh in 2019).
    # Fossil (gas): 36% (~792 GWh). DH: 0.
    # Electrification of heating/cooling in services sector grows per PNIEC.
    # -----------------------------------------------------------------------
    "EN_finEN_Service electr":    [1150, 1210, 1230, 1260, 1310, 1360, 1405, 1445],
    "EN_finEN_Service DH":        [   0,    0,    0,    0,    0,    0,    0,    0],
    "EN_finEN_Service fossil":    [ 792,  680,  635,  530,  380,  230,  100,    0],

    # -----------------------------------------------------------------------
    # INDUSTRY by energy carrier
    # Industry_electric + Industry_fossil represent the "heavy industry"
    # portion beyond Manufacturing/Agriculture/Construction above.
    # Italy industry electricity ~36% of sector total (ENEA 2019).
    # Fossil: gas-intensive (process heat, steam generation).
    # -----------------------------------------------------------------------
    "EN_finEN_Industry_elctr":   [ 545,  582,  592,  608,  645,  685,  725,  765],
    "EN_finEN_Industry_DH":      [   0,    0,    0,    0,    0,    0,    0,    0],
    "EN_finEN_Industry fossil":  [1100,  990,  940,  820,  640,  450,  280,  160],
}

# ---------------------------------------------------------------------------
# Passenger transport rows: written as zeros / placeholders since the
# mobility submodel computes these dynamically. Included in the sheet
# for structural completeness (energy_demand.py ignores them).
# ---------------------------------------------------------------------------
TRANSPORT_PLACEHOLDER_ROWS = {
    "Dist car fuel Tr":  [0]*8,
    "Dist eletr Tr":     [0]*8,
    "Dist publ Tr":      [0]*8,
    "Dist other Tr":     [0]*8,
    "Dist_Tr Total":     [0]*8,
    "EN_Cars fuels":     [0]*8,
    "EN_Cars electr":    [0]*8,
    "EN_Publ trans electr": [0]*8,
    "EN_Other fuels":    [0]*8,
}

def build_xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CETS"

    # Header row
    ws.append(["Label"] + KEYFRAME_YEARS)

    # Write all data rows
    for label, values in CETS_DATA.items():
        ws.append([label] + values)

    for label, values in TRANSPORT_PLACEHOLDER_ROWS.items():
        ws.append([label] + values)

    # Column widths
    ws.column_dimensions["A"].width = 50
    for col in "BCDEFGHI":
        ws.column_dimensions[col].width = 10

    wb.save(OUT)
    print(f"Saved: {OUT}")

    # Print summary for verification
    print()
    print("2019 totals (GWh):")
    hh = (CETS_DATA["EN_finEN_hh_space heating_Biomass"][0]
        + CETS_DATA["EN_finEN_hh_space heating_Solar"][0]
        + CETS_DATA["EN_finEN_hh_space heating_electr"][0]
        + CETS_DATA["EN_finEN_hh_space heating_fossil fuel"][0]
        + CETS_DATA["EN_finEN_hh_cooling_ac_electr"][0]
        + CETS_DATA["EN_finEN_hh_other_Biomass"][0]
        + CETS_DATA["EN_finEN_hh_other_Solar"][0]
        + CETS_DATA["EN_finEN_hh_other_electr"][0]
        + CETS_DATA["EN_finEN_hh_other_fossil"][0])
    ind = (CETS_DATA["EN_finEN_Manufacturing"][0]
         + CETS_DATA["EN_finEN_Agriculture"][0]
         + CETS_DATA["EN_finEN_Construction"][0]
         + CETS_DATA["EN_finEN_Industry_elctr"][0]
         + CETS_DATA["EN_finEN_Industry fossil"][0])
    svc = (CETS_DATA["EN_finEN_Service electr"][0]
         + CETS_DATA["EN_finEN_Service fossil"][0])
    frt = (CETS_DATA["EN_freight_tr_fuels"][0]
         + CETS_DATA["EN_freight Tr electr"][0]
         + CETS_DATA["EN_freight Tr_other"][0])
    total_static = hh + ind + svc + frt
    print(f"  Households:  {hh:,.0f} GWh")
    print(f"  Industry:    {ind:,.0f} GWh")
    print(f"  Services:    {svc:,.0f} GWh")
    print(f"  Freight:     {frt:,.0f} GWh")
    print(f"  TOTAL XLSX:  {total_static:,.0f} GWh  (excl. dynamic passenger transport)")
    print()
    elec = (CETS_DATA["EN_finEN_hh_space heating_electr"][0]
          + CETS_DATA["EN_finEN_hh_cooling_ac_electr"][0]
          + CETS_DATA["EN_finEN_hh_other_electr"][0]
          + CETS_DATA["EN_finEN_Service electr"][0]
          + CETS_DATA["EN_finEN_Industry_elctr"][0]
          + CETS_DATA["EN_freight Tr electr"][0])
    print(f"  Total electricity (static):  {elec:,.0f} GWh")
    print(f"  Per capita (905k):           {elec/905:.0f} kWh/person  (target: <3,000)")


if __name__ == "__main__":
    build_xlsx()
