# Granollers Integrated Model

Python integrated System Dynamics model for Granollers (Catalonia, Spain), developed for the [KNOWING](https://knowing-project.eu/) EU Horizon research project (Work Package 2).

## What it does

Couples three submodels into one annual Euler-integrated simulation, 2019–2050:

1. **Mobility** — logit-based generalised-cost mode choice (car / car-passenger / PT / bike / walk), calibrated against the Granollers PMUS 2009 travel survey
2. **Energy demand** — sector-level trajectories from `EN_MEADCityInput_0527_v6.xlsx`, with transport energy computed dynamically from the mobility submodel
3. **Energy supply & emissions** — local PV/CHP generation + declining Spanish grid emission factor (PNIEC) → net grid import and total GHG emissions

**Current version: v8 · Scenario: PI=1** (all policy interventions fully active by 2050)

## Key results (PI=1, 2019–2050)

| Metric | 2019 | 2030 | 2050 |
|---|---|---|---|
| Total emissions (kt CO₂-eq) | 310.8 | 176.4 | 22.4 |
| Accumulated emissions (Mt CO₂) | — | — | 4.83 |
| Car km share | 67% | 64% | 16% |
| Total final energy demand (GWh) | 1 374 | ~1 420 | 1 394 |
| Electricity demand (GWh) | 644 | 749 | 930 |
| PV generation (GWh) | ~3 | 44.5 | 119.9 |
| Grid import (GWh) | 612 | 684 | 816 |

**Emission reduction 2019→2050: 93%**

## Scenario configuration

Scenarios are controlled via `config.json` in the project root — no code changes needed.

```json
{
  "scenario_name": "PI=1",
  "policies": {
    "parking":      1,
    "area_toll":    1,
    "road_pricing": 1,
    "pt_time":      1,
    "ev":           1,
    "cycling":      1,
    "car_pass":     1,
    "capacity":     1,
    "street_green": 1
  },
  "pv_capacity_2050_mwp": 79.9
}
```

**Policy values** range from `0` (intervention inactive, BAU) to `1` (fully active by 2050). Intermediate values (e.g. `0.5`) represent partial implementation. Each policy scales the ramp trajectory `RP = [0, 0.5, 0.75, 1.0]` at years `[2019, 2030, 2040, 2050]`.

| Policy key | Description |
|---|---|
| `parking` | Parking cost reform |
| `area_toll` | Area/congestion toll |
| `road_pricing` | Road pricing per km |
| `pt_time` | PT travel time improvement |
| `ev` | EV fleet uptake support |
| `cycling` | Cycling infrastructure |
| `car_pass` | Car-passenger incentives |
| `capacity` | Road capacity management |
| `street_green` | Street greening (active mode attractiveness) |

**`pv_capacity_2050_mwp`** sets the local PV installed capacity target for 2050 (linearly interpolated from 2 MWp in 2019). The current value of 79.9 MWp follows the Catalonia PLATER plan.

Each run saves its output chart as `granollers_integrated_v8_results_<scenario_name>.png`, so multiple scenarios can be compared without overwriting.

## Requirements

```
pip install numpy matplotlib openpyxl
```

## Usage

```bash
python granollers_integrated_model.py
```

Requires `EN_MEADCityInput_0527_v6.xlsx` in the same directory.  
Outputs: console summary table + `granollers_integrated_v8_results.png`.

## PV capacity assumption (PLATER)

PV capacity is set to **79.9 MWp by 2050**, aligned with the Catalonia PLATER territorial renewable energy plan (7.7 MWp non-urbanised land + 4.4 MWp infrastructure + 67.8 MWp buildings). This replaces an earlier 250 MWp assumption.

## Project context

Part of the KNOWING project (Grant Agreement No. 101037293), funded by the European Union's Horizon Europe research and innovation programme.
