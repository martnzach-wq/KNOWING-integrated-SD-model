"""Heat-health submodel: heat-attributable deaths per year and age group.

Chain (annual step, base_year to end_year):
  climate driver: expected weeks per year in bins of weekly mean temperature (one GCM x SSP of the file)
  -> canopy microclimate per land-cover class: dT = lambda_sealed * sealed + lambda_height * height
      + lambda_canopy * canopy (pp of class area); planted trees grow along a crown-diameter line;
      only the change against the base year enters the exposure
  -> exposure per age group: class temperatures weighted by the residents of each class, with a share
      of the outdoor exposure in the adjacent street space
  -> age-specific DLNM (log-RR per weekly mean temperature), linear extrapolation in log-RR beyond the grid
  -> modifiers: cooled households (AC diffusion driven by heat days, district cooling), heat-action plan
      (explicit parts: cooled care and health facilities, cool zones; the rest as one implementation level),
      passive cooling (shading, building greening) as lower effective temperature, acclimatisation
  -> attributable deaths = baseline weekly deaths x (1 - exp(-modifier x logRR)) x weeks per bin.

In the base year without measures the module reproduces the DLNM: urban form enters only as the change of
the class temperatures against the base year. Stocks (AC share, heat-action-plan level, shaded share,
planted-tree cohorts, sealed share) are updated after each year with the lever values of the next year.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

TOUTS = ("tmax", "tmin")
FEATURES = ("sealed", "height", "canopy")


def series_value(points: dict, year: int, neutral: float) -> float:
    """Value of a lever series in a year: linear between keyframes, flat outside; empty = neutral."""
    if not points:
        return neutral
    ys = sorted(int(y) for y in points)
    return float(np.interp(year, ys, [float(points[y] if y in points else points[str(y)]) for y in ys]))


def _read(path: str) -> pd.DataFrame:
    return pd.read_parquet(path) if str(path).endswith(".parquet") else pd.read_csv(path)


def load_inputs(hh) -> dict:
    """Data of a HeatHealthConfig: DLNM curves, week profile, rates, population, climate member, class state,
    microclimate coefficients."""
    rr = pd.read_csv(hh.rr_csv)
    T = rr.loc[rr.age == rr.age.iloc[0], "T"].to_numpy(float)
    draws = [c for c in rr.columns if c.startswith("s") and c[1:].isdigit()]
    curves = {}
    for g, (label, _) in hh.age_curves.items():
        sub = rr[rr.age == label]
        if sub.empty:
            raise KeyError(f"DLNM curve {label!r} for age group {g!r} not in {hh.rr_csv}")
        curves[g] = (sub.logRR.to_numpy(float), sub[draws].to_numpy(float) if draws else None)
    wp = pd.read_csv(hh.week_profile_csv)
    warm = wp[wp.isoweek.between(*hh.warm_weeks)]
    week_share = {g: float(warm[col].mean()) for g, (_, col) in hh.age_curves.items()}
    rates = pd.read_csv(hh.rates_csv, index_col=0)["rate_per_person"].to_dict()
    pop = pd.read_csv(hh.population_csv, index_col=0)
    pop.index = pop.index.astype(int)
    clim = _read(hh.climate_file)
    if hh.climate_station is not None:
        clim = clim[clim.station == hh.climate_station]
    clim = clim[(clim.gcm == hh.climate_gcm) & (clim.ssp == hh.climate_ssp)].set_index("year").sort_index()
    if clim.empty:
        raise KeyError(f"no climate driver rows for {hh.climate_gcm} / {hh.climate_ssp}")
    cs = pd.read_csv(hh.class_state_csv, index_col=0)
    lam = json.load(open(hh.lambda_json, encoding="utf-8"))
    lam = lam.get("posterior_mean", lam)
    return {"T": T, "curves": curves, "week_share": week_share, "rates": rates, "pop": pop, "clim": clim,
            "cs": cs, "lam": lam}


def _logrr(T: np.ndarray, y: np.ndarray, Teff: np.ndarray) -> np.ndarray:
    Tc = np.clip(Teff, T[0], None)
    slope = (y[-1] - y[-11]) / (T[-1] - T[-11])
    return np.interp(Tc, T, y) + np.where(Tc > T[-1], slope * (Tc - T[-1]), 0.0)


def _crown_area(age, d0: float, growth: float, a_max: float) -> float:
    d = d0 + growth * float(age)
    return min(np.pi * d * d / 4.0, a_max)


def class_temperatures(hh, inp: dict, years) -> pd.DataFrame:
    """Change of the daily mean class temperature against the base year (K), years x classes, after the
    blend with the street space; columns are the classes of class_state_csv."""
    cs, lam = inp["cs"], inp["lam"]
    classes = list(cs.index)
    area = cs.area_km2.astype(float)
    sealed = cs.sealed_pct.astype(float).copy()
    height = cs.bldg_area_pct.astype(float) * cs.bldg_height.astype(float) / 10.0
    can0 = 100.0 * (cs.young_trees_raw * hh.crown_m2["young"] + cs.mature_trees_raw * hh.crown_m2["mature"]) / (
        area.replace(0, np.nan) * 1e6)
    can0 = can0.fillna(0.0)
    street = [c for c in hh.street_classes if c in classes]
    dense = [c for c in hh.dense_classes if c in classes]
    dense_w = cs.loc[dense, "pct_area"] / cs.loc[dense, "pct_area"].sum() if dense else pd.Series(dtype=float)
    d0, growth, a_max = hh.crown_growth
    cohorts: dict[int, pd.Series] = {}
    rows = []
    for y in years:
        add = pd.Series(0.0, index=classes)
        for k, n in cohorts.items():
            age = y - k
            add += n * (1.0 - hh.tree_mortality) ** age * _crown_area(age, d0, growth, a_max)
        canopy = can0 + (100.0 * add / (area.replace(0, np.nan) * 1e6)).fillna(0.0)
        uf = {"sealed": sealed, "height": height, "canopy": canopy}
        dT = sum(0.5 * sum(lam[t][f] * uf[f] for f in FEATURES) for t in TOUTS)
        rows.append(dT.rename(y))
        planted = pd.Series(0.0, index=classes)
        unseal = pd.Series(0.0, index=classes)
        for c in street:
            planted[c] += series_value(hh.street_trees, y, 0.0) / len(street)
            unseal[c] += series_value(hh.unseal_street_pp, y, 0.0)
        for c in dense:
            planted[c] += series_value(hh.courtyard_trees, y, 0.0) * dense_w[c]
            unseal[c] += series_value(hh.unseal_dense_pp, y, 0.0)
        cohorts[y] = planted
        sealed = (sealed - unseal).clip(lower=0.0)
    piv = pd.DataFrame(rows)
    ddT = piv - piv.iloc[0]
    if street:
        s = ddT[street].mean(axis=1)
        ddT = ddT.mul(1 - hh.street_exposure_share).add(s * hh.street_exposure_share, axis=0)
    return ddT


def run_heat_health(city, population: dict | None = None, inputs: dict | None = None) -> pd.DataFrame:
    """Heat-attributable deaths per year (index) of a city with a heat_health configuration.

    population: {year: residents} of the city model; used to scale the age groups when
    `population_from_city` is set. inputs: result of `load_inputs` (to avoid reloading in loops)."""
    hh = city.heat_health
    if hh is None:
        raise ValueError(f"{city.name}: no heat_health configuration")
    inp = inputs or load_inputs(hh)
    years = list(range(hh.base_year, hh.end_year + 1))
    ddT = class_temperatures(hh, inp, years)
    cs = inp["cs"]
    W = {}
    for g, cols in hh.class_population.items():
        w = cs[list(cols)].sum(axis=1).astype(float)
        W[g] = (w / w.sum()).to_numpy()
    clim = inp["clim"]
    jja = (clim.jja_tmax_mean + clim.jja_tmin_mean) / 2
    bins = [c for c in clim.columns if str(c).startswith("wk_")]
    Tb = np.array([float(c[3:]) + 0.25 for c in bins]) + hh.climate_shift_k
    groups = list(hh.age_curves)
    ac, hap, shade = hh.ac0, hh.hap0, 0.0
    rows = []
    for y in years:
        nw = clim.loc[y, bins].to_numpy(float)
        popy = inp["pop"].loc[y, groups].astype(float).to_dict()
        if hh.population_from_city and population is not None and y in population:
            f = float(population[y]) / sum(popy.values())
            popy = {g: v * f for g, v in popy.items()}
        dc = series_value(hh.dc_share, y, 0.0)
        cooled = ac + dc * (1 - ac)
        m_ac = max(0.0, 1.0 - hh.beta_ac * 100.0 * (cooled - hh.ac0))
        m_hap = (1.0 - hh.hap_eff * hap) / (1.0 - hh.hap_eff * hh.hap0)
        mod = m_ac * m_hap
        # explicit parts of a heat-action plan: cooled care and health facilities (residents' share of the group's
        # baseline deaths), cool zones (places x share of a hot day spent there / target population)
        eps = hh.beta_ac * 100.0  # heat-risk reduction of a cooled person
        care = series_value(hh.care_cooled, y, hh.care_cooled0)
        places = series_value(hh.cool_zone_places, y, hh.cool_zone_places0)
        target = sum(popy[g] for g in hh.cool_zone_groups) or 1.0
        u, u0 = places * hh.cool_zone_hours_share / target, hh.cool_zone_places0 * hh.cool_zone_hours_share / target
        mod_g = {}
        for g in groups:
            dg = hh.care_share.get(g, 0.0)
            m_care = (1.0 - eps * dg * care) / (1.0 - eps * dg * hh.care_cooled0)
            m_cz = (1.0 - eps * u) / (1.0 - eps * u0) if g in hh.cool_zone_groups else 1.0
            mod_g[g] = mod * m_care * m_cz
        shift = -hh.shade_dT * shade
        if hh.adapt_alpha:
            shift -= hh.adapt_alpha * float(jja.loc[y] - jja.loc[hh.adapt_ref_year])
        trend = (1 + hh.mortality_trend) ** (y - hh.base_year)
        d = ddT.loc[y].to_numpy()
        out = {}
        for g in groups:
            base = popy[g] * inp["rates"][g] * trend * inp["week_share"][g]
            Teff = Tb[None, :] + shift + d[:, None]
            curve, draws = inp["curves"][g]
            yv = curve if hh.draw is None else draws[:, hh.draw]
            af = 1.0 - np.exp(-mod_g[g] * _logrr(inp["T"], yv, Teff))
            out[g] = float(hh.ages_scale * base * (W[g][:, None] * af * nw[None, :]).sum())
        hd = float(clim.loc[y, "heat_days"]) + hh.heat_days_shift
        rows.append({"year": y, "heat_deaths": sum(out.values()),
                     **{f"heat_deaths_{g}": v for g, v in out.items()},
                     "heat_days": hd, "tropical_nights": float(clim.loc[y, "tropical_nights"]),
                     "ac_share": ac, "dc_share": dc, "cooled_share": cooled, "hap_level": hap,
                     "care_cooled_share": care, "cool_zone_places": places,
                     "shaded_share": shade, "population_heat": sum(popy.values()),
                     **{f"dT_exposure_{g}": float(W[g] @ d) for g in groups}})
        nxt = y + 1
        hap += (series_value(hh.hap_target, nxt, hh.hap0) - hap) / max(hh.hap_tau, 1e-6)
        r = hh.ac_r0 * series_value(hh.ac_growth_mult, nxt, 1.0) * (hd / hh.hd_ref)
        ac += r * ac * (1 - ac / hh.ac_max)
        shade = min(1.0, shade + series_value(hh.shading_rate, nxt, hh.shading_base_rate)
                    + hh.green_phi * series_value(hh.greening_rate, nxt, 0.0))
    return pd.DataFrame(rows).set_index("year")


def cooling_electricity(city, years, population, cdd, result: pd.DataFrame | None = None) -> np.ndarray:
    """Household cooling electricity (GWh per year): cooled share x households x kWh per AC household x
    CDD / cdd_ref, with district-cooled dwellings at dc_elec_factor. AC share from the submodel from its base
    year; before it the logistic diffusion backwards from ac0 at rate ac_r0 (no measures act before the base year).
    population and cdd: arrays over `years`."""
    hh = city.heat_health
    res = result if result is not None else run_heat_health(city, population=dict(zip(years, population)))
    years = np.asarray(years, int)
    ac = np.empty(len(years))
    dc = np.zeros(len(years))
    for i, y in enumerate(years):
        if y in res.index:
            ac[i], dc[i] = res.loc[y, "ac_share"], res.loc[y, "dc_share"]
        elif y < hh.base_year:
            k = hh.ac_max
            ac[i] = k / (1 + (k - hh.ac0) / hh.ac0 * np.exp(hh.ac_r0 * (hh.base_year - y)))
        else:
            ac[i], dc[i] = res.ac_share.iloc[-1], res.dc_share.iloc[-1]
    cooled = ac * (1 - dc) + hh.dc_elec_factor * dc
    households = np.asarray(population, float) * hh.households_per_person
    return cooled * households * hh.ac_kwh_per_household * np.asarray(cdd, float) / hh.cdd_ref / 1e6
