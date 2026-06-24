# Granollers Integrated Model — Context Handoff for Claude Code

This note summarises the current state of `granollers_integrated_model.py` so a fresh
Claude Code session has the context normally carried in chat history.

## What this is

A Python integrated System Dynamics model for Granollers (Catalonia, Spain), built for
the KNOWING EU research project. It couples three submodels into one annual,
Euler-integrated simulation, 2019–2050:

1. **Mobility** — logit-based generalised-cost mode choice model (car/car-passenger/PT/
   bike/walk), calibrated against the Granollers PMUS 2009 travel survey.
2. **Energy Demand** — reads sector-level demand trajectories from
   `EN_MEADCityInput_0527_v6.xlsx` (8 time nodes, linearly interpolated), except
   transport energy, which is computed dynamically from the Mobility submodel's output.
3. **Energy Supply & Emissions** — combines demand with local PV/CHP generation and a
   declining Spanish grid emission factor to compute net import and total emissions.

**Current version: v8.** **Scenario: PI=1** (all policy interventions fully active by
2050) is the only scenario this script runs — there is no BAU/PI=0 path in this file.

## Running it

```bash
pip install numpy matplotlib openpyxl
python granollers_integrated_model.py
```

Requires `EN_MEADCityInput_0527_v6.xlsx` in the same directory (already included in
this handoff). Output: console summary table + `granollers_integrated_v8_results.png`
(a 4×3 grid of charts) saved next to the script.

The `OUTPUT_DIR` path has been changed from a hardcoded `/mnt/user-data/outputs` to
`Path(__file__).parent` so it runs standalone — this is the only edit made for the
handoff; no model logic was changed.

## Key results at v8 (for sanity-checking after any edit)

| Metric | 2019 | 2030 | 2050 |
|---|---|---|---|
| Total emissions (kt CO₂-eq) | 310.8 | 176.4 | 22.4 |
| Accumulated emissions (Mt CO₂, 2019→) | — | — | 4.83 |
| Car km share | 67% | 64% | 16% |
| Total final energy demand (GWh) | 1,374 | ~1,420 | 1,394 |
| Electricity demand (GWh) | 644 | 749 | 930 |
| PV generation (GWh) | ~3 | 44.5 | 119.9 |
| Grid import (GWh) | 612 | 684 | 816 |

Emission reduction 2019→2050: **93%**.

## The one assumption most likely to come up again: PV capacity (PLATER)

This is the most recent and most consequential change to the model. **As of v8, PV
capacity is set to 79.9 MWp by 2050** (`IC_PV` interpolates 2 → 79.9 MWp), aligned with
the Catalonia PLATER territorial renewable energy plan (pending approval ~2027):
non-urbanised land 7.7 MWp + infrastructure 4.4 MWp + buildings 67.8 MWp.

This **replaced an earlier 250 MWp assumption** (an internally generated "ambitious
technical potential" scenario, ~3.1× higher than PLATER, with no equivalent planning
mandate). If you see references elsewhere (old slides, earlier chat history, or if
someone asks you to "restore the old PV assumption") — 250 MWp is the **superseded**
value; 79.9 MWp is current and correct unless explicitly told otherwise.

Effect of the correction at 2050: PV generation 375→120 GWh, PV self-sufficiency
~40%→~13%, grid import 555→816 GWh, grid import emissions 2.8→4.1 kt CO₂. Net effect on
total 2050 emissions is small (+1.3 kt) because the Spanish grid is itself
near-decarbonised by 2050 — the correction matters much more for energy
self-sufficiency and grid infrastructure planning than for the emissions headline.

If asked about grid infrastructure implications of this PV change: import capacity
(substation/feeder capacity to deliver power in) *increases* under the lower-PV
scenario (+49 MW by 2050 at an assumed 0.60 load factor), while hosting capacity
(feeder/transformer capacity to absorb PV export) *decreases substantially* (−148 MW by
2050 at a 1.15 DC/AC inverter ratio). These move in opposite directions and should not
be netted against each other — they're different infrastructure assets. Battery storage
sizing (using a blended 0.86 kWh/kWp ratio: 60% residential at 1.0 kWh/kWp + 40%
commercial/industrial at 0.65 kWh/kWp) falls from 215 MWh to 69 MWh by 2050 under the
same correction.

## Known open items / things not yet implemented

- **Industrial process heat residual** (~35 GWh / ~9.5 kt CO₂ in 2050) has no PI lever
  in the model. Heat pumps (low-to-mid temperature) and green hydrogen (high
  temperature, imported via the Enagás backbone, no local electrolysis) are the two
  candidate technologies if this is to be addressed — not yet implemented.
- **Services-sector fossil demand** declines steeply 2025→2030 in the XLSX trajectory
  with no clearly documented driving policy — flagged as weakly justified, not yet
  corrected.
- **Heat-pump electricity feedback loop** (Energy Supply → Energy Demand) is not
  closed — would need a one-year lag/delay to avoid a simultaneous-equation problem if
  implemented.
- **Services/industry cooling demand** cannot be separated from aggregate electricity
  rows in the XLSX — limits climate-sensitivity (CDD) analysis for those sectors.
- A Vensim-native skeleton (`Granollers_Integrated_v1.mdl`, not included in this
  handoff) exists in parallel but is not at calibration parity with this Python model;
  three of its lookup tables (EV share, floor area, electricity capacity) are
  unpopulated placeholders.

## Companion documentation

A full 19-page methodology deliverable (design, assumptions, calibration, results for
all three submodels) exists as `granollers_integrated_methodology.docx`, generated from
this same model state. Not included in this handoff bundle, but worth requesting if you
need the full narrative — this note only covers what's needed to keep editing the code
without losing the PLATER context.
