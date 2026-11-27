"""Heat-health submodel on synthetic data: base-year identity with the DLNM, direction of the levers, and the
demonstrator cities unchanged (no heat_health configuration). Run: python -m pytest tests/test_heat_health.py"""

import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import city_config as cc  # noqa: E402
import heat_health as H  # noqa: E402

GROUPS = {"0-64": ("d0", "sh0"), "65-74": ("d6574", "sh6574"), "75+": ("d75", "sh75")}
CLASSES = ["dense", "medium", "road"]


def _config(tmp: Path, **kw) -> cc.HeatHealthConfig:
    T = np.arange(10.0, 32.0, 0.1)
    rr = pd.concat([pd.DataFrame({"age": lab, "T": T, "logRR": k * np.clip(T - 20.0, 0, None) ** 1.5 / 100})
                    for lab, k in (("d0", 0.5), ("d6574", 1.0), ("d75", 2.0))])
    rr.to_csv(tmp / "rr.csv", index=False)
    pd.DataFrame({"isoweek": range(1, 53), **{c: 1 / 52 for c in ("sh0", "sh6574", "sh75")}}).to_csv(
        tmp / "wp.csv", index=False)
    pd.DataFrame({"rate_per_person": [0.002, 0.017, 0.07]}, index=pd.Index(list(GROUPS), name="ag")).to_csv(
        tmp / "rates.csv")
    years = range(2025, 2036)
    pd.DataFrame({g: [1e5, 2e4, 2e4][i] for i, g in enumerate(GROUPS)}, index=pd.Index(years, name="year")).to_csv(
        tmp / "pop.csv")
    bins = np.arange(10.0, 30.0, 0.5)
    rows = []
    for y in years:
        w = np.exp(-0.5 * ((bins - (18 + 0.1 * (y - 2025))) / 4) ** 2)
        rows.append({"gcm": "g", "ssp": "s", "year": y, "heat_days": 30.0, "tropical_nights": 10.0,
                     "jja_tmax_mean": 27.0, "jja_tmin_mean": 17.0, **{f"wk_{b}": v for b, v in zip(bins, 52 * w / w.sum())}})
    pd.DataFrame(rows).to_csv(tmp / "clim.csv", index=False)
    pd.DataFrame({"area_km2": [10.0, 20.0, 5.0], "pct_area": [28.6, 57.1, 14.3], "sealed_pct": [70.0, 40.0, 90.0],
                  "bldg_area_pct": [50.0, 25.0, 0.0], "bldg_height": [15.0, 8.0, 0.0],
                  "young_trees_raw": [500, 1000, 800], "mature_trees_raw": [2000, 5000, 1500],
                  "pop_0_14": [1e4, 2e4, 0.0], "pop_15_64": [5e4, 8e4, 0.0], "pop_65p": [1e4, 3e4, 0.0]},
                 index=pd.Index(CLASSES, name="cls")).to_csv(tmp / "cs.csv")
    lam = {"tmax": {"sealed": 0.01, "height": 0.002, "canopy": -0.015},
           "tmin": {"sealed": 0.02, "height": 0.015, "canopy": -0.012}}
    (tmp / "lam.json").write_text(json.dumps({"posterior_mean": lam}))
    return cc.HeatHealthConfig(
        rr_csv=str(tmp / "rr.csv"), week_profile_csv=str(tmp / "wp.csv"), rates_csv=str(tmp / "rates.csv"),
        population_csv=str(tmp / "pop.csv"), climate_file=str(tmp / "clim.csv"), class_state_csv=str(tmp / "cs.csv"),
        lambda_json=str(tmp / "lam.json"), ac0=0.1, ac_r0=0.15, hd_ref=30.0, crown_m2={"young": 6.0, "mature": 50.0},
        crown_growth=(1.5, 0.25, 50.0), climate_gcm="g", climate_ssp="s", end_year=2035,
        street_classes=("road",), dense_classes=("dense",), **kw)


@dataclasses.dataclass
class _City:
    name: str
    heat_health: cc.HeatHealthConfig


def test_base_year_reproduces_the_dlnm(tmp_path):
    hh = _config(tmp_path)
    inp = H.load_inputs(hh)
    r = H.run_heat_health(_City("x", hh), inputs=inp)
    clim = inp["clim"].loc[2025]
    bins = [c for c in clim.index if str(c).startswith("wk_")]
    Tb = np.array([float(c[3:]) + 0.25 for c in bins])
    expected = 0.0
    for g in GROUPS:
        base = inp["pop"].loc[2025, g] * inp["rates"][g] * inp["week_share"][g]
        lr = H._logrr(inp["T"], inp["curves"][g][0], Tb)
        expected += base * float(((1 - np.exp(-lr)) * clim[bins].to_numpy(float)).sum())
    assert abs(r.loc[2025, "heat_deaths"] - expected) < 1e-9
    assert r.loc[2035, "heat_deaths"] > r.loc[2025, "heat_deaths"]  # warming driver


def test_levers_lower_heat_deaths_and_ac_restraint_raises_them(tmp_path):
    base = _City("x", _config(tmp_path))
    inp = H.load_inputs(base.heat_health)
    ref = H.run_heat_health(base, inputs=inp).heat_deaths
    for kw in ({"street_trees": {2025: 0, 2026: 20000}}, {"unseal_dense_pp": {2025: 0, 2026: 1.0}},
               {"hap_target": {2025: 0.5, 2026: 1.0}}, {"shading_rate": {2025: 0.003, 2026: 0.05}},
               {"dc_share": {2025: 0, 2035: 0.2}}):
        r = H.run_heat_health(_City("x", dataclasses.replace(base.heat_health, **kw)), inputs=inp).heat_deaths
        assert r[2025] == ref[2025] and r[2035] < ref[2035], kw
    r = H.run_heat_health(_City("x", dataclasses.replace(base.heat_health, ac_growth_mult={2025: 1, 2026: 0.25})),
                          inputs=inp).heat_deaths
    assert r[2035] > ref[2035]


def test_demonstrators_have_no_heat_health():
    for name in ("TALLINN", "NAPLES"):
        city = getattr(cc, name, None)
        if city is not None:
            assert city.heat_health is None


def test_cooling_electricity_follows_ac_share_and_cdd(tmp_path):
    hh = _config(tmp_path, ac_kwh_per_household=300.0, cdd_ref=200.0)
    city = _City("x", hh)
    years = np.arange(2019, 2036)
    pop = np.full(len(years), 1.4e5)
    cool = H.cooling_electricity(city, years, pop, np.full(len(years), 200.0))
    i25 = int(np.where(years == 2025)[0][0])
    assert abs(cool[i25] - hh.ac0 * 1.4e5 * 0.5 * 300.0 / 1e6) < 1e-12  # base year: ac0 x households x kWh
    assert np.all(np.diff(cool) > 0)  # logistic backcast before, diffusion after the base year
    hot = H.cooling_electricity(city, years, pop, np.full(len(years), 300.0))
    assert np.allclose(hot, cool * 1.5)
