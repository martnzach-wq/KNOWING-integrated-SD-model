# Tallinn + Granollers Integrated Model — Context Handoff

KNOWING EU project. Generic, multi-city integrated urban simulation
(Mobility → Energy Demand → Energy Supply, 2019–2050). Both Tallinn AND
Granollers now run through the SAME codebase via `CityConfig` — this was
completed this session (previously Granollers only existed as a separate
standalone script).

## What's here

- `city_config.py` — `CityConfig` dataclass structure. Both `TALLINN` and
  `GRANOLLERS` instances are fully populated. **Naples is not migrated.**
- `mobility.py`, `energy_demand.py`, `energy_supply.py` — the three
  submodels, generic across cities via `CityConfig`.
- `granollers_integrated_model.py` — the ORIGINAL standalone Granollers
  script, kept for audit/reference (this is what `GRANOLLERS` was migrated
  from; its embedded `REF_MOB`/`V4_EM` checkpoints are the validation
  target used throughout this session).
- `run_tallinn_integrated.py`, `export_dashboard_data.py`,
  `make_static_chart.py` — runner/export scripts (currently Tallinn-only
  by name/default; trivial to point at `GRANOLLERS` instead — see "How to
  run for a different city" below).
- Source data: `Submodel_Mobility_v10.mdl`, `Submodel_EnergySupply_v4.mdl`,
  `mob_inputs.csv`, `mob_inp10.xlsx`, `EN_MEADCityInput.xlsx`,
  `Supply_Data_Tallinn.xlsx` (Tallinn), `EN_MEADCityInput_0527_v6.xlsx`
  (Granollers — read at runtime, same as Tallinn's energy-demand XLSX;
  only the MOBILITY raw data files are audit-only / not read at runtime
  for either city, since those values are transcribed into city_config.py).
- All XLSX paths resolve via `Path(__file__).parent` in `city_config.py`.

## How to run for a different city

There's no city-selection flag — you pass the `CityConfig` object directly:

```python
from city_config import TALLINN, GRANOLLERS
from mobility import run_mobility
from energy_demand import run_energy_demand
from energy_supply import run_energy_supply

city = GRANOLLERS  # or TALLINN
mob = run_mobility(city, pi_scenario=1.0)
ed = run_energy_demand(city, mob, pkm_method="mode_specific")
es = run_energy_supply(city, ed)
```

To change INPUT DATA: edit `city_config.py` directly (mobility constants
are Python literals there) or point `xlsx_path` at a different file for
energy demand/supply (those XLSX are read fresh every run).

## Session summary: three real bugs found and fixed while migrating Granollers

Migrating Granollers into the generic architecture required actually
validating against its known checkpoints (`REF_MOB`, `V4_EM` in
`granollers_integrated_model.py`), which surfaced bugs that had been
silently present in the Tallinn-only code all along:

1. **Population doubling bug** (`mobility.py _build_inputs`): population
   was being added twice (once as a flat base, once inside
   `_cumulative_pop_increase`, which already starts at the base value).
   This canceled out exactly in per-capita distance RATIOS (so all
   previously-reported km/cap/yr figures were actually correct) but NOT
   in the absolute trip volumes feeding the mode-change dynamics --
   meaning `mode_change_damping` had been calibrated against a doubled
   population. Fixed, and damping re-calibrated (Tallinn: 0.245 -> 0.264).

2. **Congestion speed factor (Granollers-only code path)**: was computed
   globally instead of per-zone, used car+car_passenger trip counts
   instead of car-only, and used a fixed network capacity instead of the
   time-varying CapacityAdaptation-policy-scaled value. Fixed in
   _generalised_cost/run().

3. **TR_AccessTime mode mapping (Granollers-only code path)**: public
   transport and car access times were swapped relative to the original
   script's [car=0.15, car_passenger=0.10, PT=0.20] array -- PT was
   getting the SHORTER access time, making it artificially more
   attractive. Fixed via the new access_time_by_mode config field.

4. **THE BIG ONE -- BaseAttr calibration applied unconditionally**: the
   GC-neutral BaseAttr calibration built for Tallinn (see
   _compute_baseattr_calibration) was running for EVERY city regardless
   of whether it needed it. Granollers' own TR_BaseAttr values are
   already hand-tuned in the original script and do NOT need this
   correction -- applying it anyway gave Granollers' public-transport
   mode a spurious +2.49 attractiveness boost, which was the dominant
   cause of PT share being wildly overestimated (60%+ too high) even
   after fixes 1-3 above were in place. Fixed: gated behind
   MobilityConfig.apply_cdd_baseattr_compensation (Tallinn=True,
   Granollers=False), which existed as a field already but had never
   actually been wired into the code (it silently no-op'd before).

   Side-effect of fixing this: discovered Tallinn's own flag had been
   left at False (a placeholder value, never flipped after the
   calibration was originally built and validated). Flipped to True
   (verified: produces stable near-2019-equilibrium behavior, vs.
   monotonic drift when off) and mode_change_damping re-confirmed at
   0.264 under the corrected setting.

## Current validation status

**Tallinn**: PI=1 lands at exactly ~20.0% car mode-share by 2050 (matching
an earlier Vensim run's reported value), stable near its real 2019
baseline through ~2023 before policy-driven divergence. BAU drifts
slowly toward higher car share, as expected.

**Granollers**: validated against REF_MOB/V4_EM checkpoints
(mode_change_damping=0.84, found by grid search minimizing squared error
across all 5 checkpoint years x 3 modes):

| Year | car_fos (mine / target) | PT (mine / target) | active (mine / target) |
|------|--------------------------|---------------------|--------------------------|
| 2019 | 4217 / 4112 | 1368 / 1330 | 684 / 681 |
| 2030 | 2588 / 2587 | 929 / 766 | 922 / 906 |
| 2050 | 109 / 111 | 1489 / 1419 | 1508 / 1453 |

Car and active modes fit within ~0-9% throughout. PT still runs somewhat
high mid-period (2030: +21%) -- this residual gap is NOT yet resolved and
is the most promising next debugging thread (see below). Electricity-only
emissions (em_elec_prod + em_elec_imp) match V4_EM within 0.3% at the
2019 anchor; gap widens to a still-small absolute difference (~7 kt) by
2050.

## Known gaps / open items, in priority order

1. **Granollers PT mid-period overshoot** (~20% too high around
   2025-2040, converging back to ~5% by 2050). All three structural bugs
   (csf, access time, BaseAttr double-correction) are fixed; this is a
   smaller, second-order remaining gap. Worth checking: whether
   config.json (genuinely missing -- never available this session) sets
   some PI flags to OFF rather than the assumed all-1 ("PI=1 scenario
   only... all policy interventions active" per the script's own header
   comment, which is what was assumed) -- if e.g. street_green or
   capacity was actually flagged off in the real run, that would shift
   PT's trajectory.
2. **Naples**: not started.
3. The Tallinn/Granollers dashboard (outputs/tallinn_dashboard.html) and
   its export script are still Tallinn-only in framing -- they show
   Granollers only via the OLD embedded reference checkpoints, not a
   live run of the now-working GRANOLLERS config. Re-running
   export_dashboard_data.py for both cities and updating the dashboard to
   do a true side-by-side live comparison is a natural next step now
   that Granollers actually runs correctly.
4. run_tallinn_integrated.py is still named/scoped for Tallinn only;
   consider generalizing to take a city argument.

## Calibration constants reference (for future re-tuning)

- mode_change_damping: Tallinn=0.264, Granollers=0.84 (in MobilityConfig,
  per-city field). Re-calibrate via grid search / bisection against known
  mode-share checkpoints if mobility inputs change.
- apply_cdd_baseattr_compensation: Tallinn=True, Granollers=False.
  Controls whether _compute_baseattr_calibration()'s empirical
  equilibrium correction is applied. Only enable for a city if its own
  base attractiveness values are NOT already separately calibrated to
  reproduce the real mode split.
- Tallinn EV trajectory: evidence-anchored (elektriauto.ee/EAFO), PI=1
  reaches 85% by 2050, BAU damps to ~half from a 2026 pivot
  (ev_bau_damping_pivot_year). Granollers EV trajectory: transcribed
  verbatim from the original script's EV_PI array (PI=1 reaches 80% by
  2050; no separate BAU damping in the original, so
  ev_bau_damping_pivot_year=None for Granollers -- same curve both
  scenarios).
