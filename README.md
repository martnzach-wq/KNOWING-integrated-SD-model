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
