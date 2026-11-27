"""
microclimate.py

Python translation of Submodel_MicroClimate_v4.mdl, calibrated against the
PALM-4U results for Tallinn (mc4_cal_tallinn.csv) and coupled to the cooling
degree days (CDD) used by the mobility and energy demand submodels.

Structure (D2.4, section 4.2.4): the city area is divided into Corine Land
Cover classes c; for each class four urban features UF[f, c] are given:

    Sealed area percentage   = sealed %                                (mdl)
    Buildings height         = buildings area % x building height / 10 (mdl)
    Young Trees              = young trees / city-area % of the class  (mdl)
    Mature Trees             = mature trees / city-area % / 100        (mdl)

and the 2 m air temperature of a hot day (tmax, tmin) per class is linear in
the features:

    T[o, c, t] = T_met[o](t) + shift[o, c] + sum_f lambda[o, f] * UF[f, c, t]

Calibration (mdl: CL Lambda UF = 0, CL TempShift = 1 as placeholders):
    - lambda from the WITHIN-class changes 2019 -> 2030/2040/2050 of the
      PALM-4U scenario runs (class fixed effects), weighted by the class
      share of the city area (CL CalibrationWeight). The within estimator
      targets the response to interventions, which is what the SD model is
      used for; a pooled cross-section fit reproduces the class levels
      (weighted R2 0.72 tmax, 0.91 tmin) but only about a quarter of the
      temporal response.
    - shift[o, c] reproduces each class level in 2019 exactly.
    The within fit reproduces about 70 % of the PALM-4U city-average cooling
    by 2050 (tmax -0.16 of -0.23 K, tmin -0.14 of -0.21 K).

Time: the mdl runs monthly from 2009 (Time 0) to 2050 (Time 492); the
calibration file gives values at Time 120/252/372/492 = 2019/2030/2040/2050.
This translation runs on the annual YEARS grid of the integrated model.

Meteorological trend: CL PeakSummerTemp rises by 1.6 K over the 492 months
(mdl); applied to both outputs.

Levers (D60): tree planting (young and mature trees) and unsealing (sealed
area) are levers of their own, D2.4 Table 15 "PI LU PlantTrees" and
"PI LU Unseal"; building heights follow the PI. Each lever scales the PALM-4U
pathway with its own intensity s_f(t):

    UF[f, c, t] = UF[f, c, 2019] + PI * s_f(t) * (UF_pathway[f, c, t] - UF[f, c, 2019])

or is given in natural units (trees planted, ha unsealed), placed on the
classes in the proportions of the pathway. The pathway design of D2.4
Table 14 links greening and unsealing to traffic calming; this coupling is
available as coupling="traffic_calming" (all features follow the PI and drop
out when the traffic-calming lever is removed or held).

The mobility effect of greening is already contained in those mobility
levers; the microclimate submodel therefore acts on mobility only through
the CDD.

CDD coupling: MAED-City's CETS CDD trajectory already contains the cooling
of the full pathway (D3.3: CDD -0.8/-1.0/-1.2 % in 2030/2040/2050). With the
city-average cooling dT_PI(t) (mean of tmax and tmin, area weighted):

    CDD(t) = CDD_CETS(t) * (1 + beta * dT_PI(t)) / (1 + beta * dT_1(t))

beta is cross-calibrated so that the full pathway reproduces the D3.3 CDD
reductions from the modelled city-average cooling (beta = 0.09, i.e. 9 % per K).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from city_config import YEARS

FEATURES = ["Sealed area percentage", "Buildings height", "Young Trees", "Mature Trees"]
OUTPUTS = ["tmax", "tmin"]
CAL_YEARS = [2019, 2030, 2040, 2050]
PEAK_TREND_K = 1.6  # CL PeakSummerTemp: + 1.6 * Time / 492 (2009-2050)

# D3.3 section 5.5.7.6: CDD reduction by the PALM-4U measures (full pathway)
TALLINN_CDD_REDUCTION = {2030: 0.008, 2040: 0.010, 2050: 0.012}


@dataclass
class MicroclimateData:
    classes: list[str]
    area: np.ndarray  # % of city area per class
    uf: np.ndarray  # [class, feature, cal_year]
    temp: dict[str, np.ndarray] = field(default_factory=dict)  # output -> [class, cal_year]


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def load_calibration(path: str | Path) -> MicroclimateData:
    """Read the PALM-4U calibration table (semicolon-separated, decimal comma)."""
    raw = {}
    with open(path, encoding="utf-8") as fh:
        rows = [line.rstrip("\n").split(";") for line in fh]
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        if r[0] == "CL TempOutput":
            key = (r[0], r[1].strip(), " ".join(r[2].split()).lower())
        else:
            key = (r[0], " ".join(r[1].split()).lower())
        raw[key] = np.array([_num(v) for v in r[7:11]])
    classes = [k[1] for k in raw if k[0] == "LU Percentage of city area"]
    area = np.array([raw[("LU Percentage of city area", c)][0] for c in classes])
    uf = np.zeros((len(classes), len(FEATURES), len(CAL_YEARS)))
    for i, c in enumerate(classes):
        share = raw[("LU Percentage of city area", c)]
        uf[i, 0] = raw[("LU Sealed area percentage", c)]
        uf[i, 1] = raw[("LU Buildings area percentage", c)] * raw[("LU Buildings height", c)] / 10
        uf[i, 2] = raw[("LU Young Trees", c)] / share
        uf[i, 3] = raw[("LU Mature Trees", c)] / share / 100
    temp = {o: np.array([raw[("CL TempOutput", o, c)] for c in classes]) for o in OUTPUTS}
    return MicroclimateData(classes, area, uf, temp)


@dataclass
class MicroclimateFit:
    data: MicroclimateData
    lam: dict[str, np.ndarray]  # output -> [feature]
    shift: dict[str, np.ndarray]  # output -> [class] (incl. 2019 meteorology)


def calibrate(data: MicroclimateData) -> MicroclimateFit:
    """Within-class weighted least squares for lambda; class shifts from 2019."""
    lam, shift = {}, {}
    w = np.repeat(data.area, len(CAL_YEARS) - 1)
    du = (data.uf - data.uf[:, :, :1])[:, :, 1:].transpose(0, 2, 1).reshape(-1, len(FEATURES))
    for o in OUTPUTS:
        t = data.temp[o]
        dt = (t - t[:, :1])[:, 1:].ravel()
        sw = np.sqrt(w)
        lam[o], *_ = np.linalg.lstsq(du * sw[:, None], dt * sw, rcond=None)
        shift[o] = t[:, 0] - data.uf[:, :, 0] @ lam[o]
    return MicroclimateFit(data, lam, shift)


def _feature_path(data: MicroclimateData, intensity, years=YEARS, delta=None) -> np.ndarray:
    """UF[class, feature, year] on the annual grid: the PALM-4U pathway scaled by the policy intensity (a number,
    or an array [feature, year]), plus ``delta`` [class, feature, year] for interventions given in natural
    units (D60)."""
    inten = np.broadcast_to(np.asarray(intensity, dtype=float), (len(FEATURES), len(years)))
    out = np.empty((len(data.classes), len(FEATURES), len(years)))
    for i in range(len(data.classes)):
        for f in range(len(FEATURES)):
            path = np.interp(years, CAL_YEARS, data.uf[i, f])
            out[i, f] = data.uf[i, f, 0] + inten[f] * (path - data.uf[i, f, 0])
    return out if delta is None else out + delta


SEALED, YOUNG, MATURE = (FEATURES.index(f) for f in ("Sealed area percentage", "Young Trees", "Mature Trees"))
TREE_MATURITY_YEARS = 10  # young trees of the PALM-4U 2030 run appear as mature trees in 2040


def pathway_quantities(data: MicroclimateData, city_area_km2: float | None = None) -> dict:
    """Interventions of the PALM-4U pathway against 2019 at the calibration years: trees planted (cumulative
    count, young plus additional mature trees), unsealed area in ha (needs ``city_area_km2``), and the class
    distribution of both in 2050, used to place interventions given in natural units (D60)."""
    young = data.uf[:, YOUNG, :] * data.area[:, None]
    mature = data.uf[:, MATURE, :] * data.area[:, None] * 100
    planted = young + mature - mature[:, :1]
    out = {"years": CAL_YEARS, "trees_planted": planted.sum(axis=0)}
    out["tree_weights"] = np.clip(planted[:, -1], 0, None) / np.clip(planted[:, -1], 0, None).sum()
    if city_area_km2:
        class_ha = city_area_km2 * 100 * data.area / 100
        unsealed = class_ha[:, None] * (data.uf[:, SEALED, :1] - data.uf[:, SEALED, :]) / 100
        out["unsealed_ha"] = unsealed.sum(axis=0)
        out["unseal_weights"] = np.clip(unsealed[:, -1], 0, None) / np.clip(unsealed[:, -1], 0, None).sum()
    return out


def _series(points: dict, years=YEARS) -> np.ndarray:
    pts = sorted(points.items())
    return np.interp(years, [a for a, _ in pts], [b for _, b in pts])


def natural_unit_delta(data: MicroclimateData, mc, pi_scenario: float, removed=(), years=YEARS) -> np.ndarray:
    """Feature changes [class, feature, year] of interventions in natural units: ``unseal_ha`` (sealed area
    removed against 2019) and ``plant_trees`` (cumulative trees planted against 2019), placed on the classes
    in the proportions of the PALM-4U pathway in 2050; planted trees count as young trees for
    TREE_MATURITY_YEARS and as mature trees afterwards."""
    years = np.asarray(years)
    delta = np.zeros((len(data.classes), len(FEATURES), len(years)))
    q = pathway_quantities(data, mc.city_area_km2)
    if mc.unseal_ha and "policy_unseal" not in removed:
        if not mc.city_area_km2:
            raise ValueError("city_area_km2 is needed for unseal_ha")
        class_ha = mc.city_area_km2 * data.area  # km2 x % = ha
        u = pi_scenario * _series(mc.unseal_ha, years)
        share = np.divide(q["unseal_weights"], class_ha, out=np.zeros(len(class_ha)), where=class_ha > 0)
        delta[:, SEALED] = -100 * share[:, None] * u[None, :]
    if mc.plant_trees and "policy_plant_trees" not in removed:
        n = pi_scenario * _series(mc.plant_trees, years)
        lagged = pi_scenario * _series(mc.plant_trees, years - TREE_MATURITY_YEARS)
        lagged[years - TREE_MATURITY_YEARS < min(mc.plant_trees)] = 0.0
        w = np.divide(q["tree_weights"], data.area, out=np.zeros(len(data.area)), where=data.area > 0)
        delta[:, YOUNG] = w[:, None] * (n - lagged)[None, :]
        delta[:, MATURE] = w[:, None] * lagged[None, :] / 100
    return delta


def lever_intensity(city, pi_scenario: float, removed=(), years=YEARS) -> np.ndarray:
    """Intensity [feature, year] of the microclimate levers on the PALM-4U pathway (D60).

    Decoupled (default): tree planting and unsealing follow their own series as share of the pathway
    (policy_plant_trees, policy_unseal; empty: full pathway, given in natural units: none), building heights
    follow the PI. Coupled (coupling="traffic_calming"): all features follow the PI and drop out with the
    traffic-calming lever and its companions."""
    mc = city.microclimate
    n = len(years)
    inten = np.full((len(FEATURES), n), float(pi_scenario))
    if mc.coupling == "traffic_calming":
        coupled = {"policy_capacity_adaptation", "policy_cycling_attractiveness", "policy_street_green"}
        capacity = city.mobility.policy_capacity_adaptation
        if coupled & set(removed) or len(set(capacity.values())) <= 1:
            inten[:] = 0.0
        return inten
    if mc.coupling is not None:
        raise ValueError(f"unknown microclimate coupling {mc.coupling!r}")

    def share(points: dict, natural: dict, lever: str) -> np.ndarray:
        if lever in removed or natural:
            return np.zeros(n)
        return _series(points, years) if points else np.ones(n)

    trees = share(mc.policy_plant_trees, mc.plant_trees, "policy_plant_trees")
    inten[YOUNG] = inten[MATURE] = pi_scenario * trees
    inten[SEALED] = pi_scenario * share(mc.policy_unseal, mc.unseal_ha, "policy_unseal")
    return inten


def city_temperatures(fit: MicroclimateFit, intensity, years=YEARS, delta=None) -> dict:
    """Area-weighted city temperatures of a hot day per year, without the
    meteorological trend (feature effect only) and with it."""
    uf = _feature_path(fit.data, intensity, years, delta)
    met = PEAK_TREND_K * (np.asarray(years) - 2019) / 41.0
    out = {}
    for o in OUTPUTS:
        per_class = fit.shift[o][:, None] + np.einsum("cft,f->ct", uf, fit.lam[o])
        feat = np.average(per_class, axis=0, weights=fit.data.area)
        out[f"{o}_features"] = feat
        out[o] = feat + met
    out["dT_mean"] = 0.5 * (
        out["tmax_features"] - out["tmax_features"][0] + out["tmin_features"] - out["tmin_features"][0]
    )
    return out


def cross_calibrate_beta(fit: MicroclimateFit, reductions: dict = TALLINN_CDD_REDUCTION) -> float:
    """Relative CDD change per K of city-average cooling (least squares through
    the origin), matching the DM-reported CDD reductions of the full pathway."""
    t = city_temperatures(fit, 1.0)
    x = np.array([-t["dT_mean"][YEARS.index(y)] for y in reductions])
    y = np.array(list(reductions.values()))
    return float((x * y).sum() / (x * x).sum())


def cdd_series(cdd_cets: dict, fit: MicroclimateFit | None, intensity, beta: float, years=YEARS, delta=None) -> dict:
    """CDD per year for a policy intensity; CDD_CETS contains the full pathway."""
    ys = sorted(cdd_cets)
    base = np.interp(years, ys, [cdd_cets[y] for y in ys])
    if fit is None:
        return {"cdd": base, "cdd_cets": base, "dT_mean": np.zeros(len(years))}
    d_pi = city_temperatures(fit, intensity, years, delta)["dT_mean"]
    d_1 = city_temperatures(fit, 1.0, years)["dT_mean"]
    return {"cdd": base * (1 + beta * d_pi) / (1 + beta * d_1), "cdd_cets": base, "dT_mean": d_pi}


def run_microclimate(city, pi_scenario: float = 1.0, removed=()) -> dict:
    """Microclimate outputs for a city: CDD per year and, where calibrated,
    city-average hot-day temperatures. The coupled levers (capacity
    tree-planting and unsealing levers set the intensity (D60); with
    coupling="traffic_calming" the traffic-calming levers do."""
    mc = getattr(city, "microclimate", None)
    cdd_cets = city.mobility.cooling_degree_days_trajectory or {2019: city.mobility.cooling_degree_days}
    if mc is None or mc.calibration_csv is None:
        out = cdd_series(cdd_cets, None, 0.0, 0.0)
        out["years"] = np.array(YEARS)
        return out
    fit = calibrate(load_calibration(mc.calibration_csv))
    intensity = lever_intensity(city, pi_scenario, removed)
    delta = natural_unit_delta(fit.data, mc, pi_scenario, removed) if mc.coupling is None else None
    beta = mc.beta if mc.beta is not None else cross_calibrate_beta(fit)
    out = cdd_series(cdd_cets, fit, intensity, beta, delta=delta)
    out.update({k: v for k, v in city_temperatures(fit, intensity, delta=delta).items() if k in OUTPUTS})
    out.update(years=np.array(YEARS), beta=beta, lam=fit.lam, intensity=intensity)
    return out


if __name__ == "__main__":
    data = load_calibration(Path(__file__).with_name("mc4_cal_tallinn.csv"))
    fit = calibrate(data)
    for o in OUTPUTS:
        print(o, dict(zip(FEATURES, np.round(fit.lam[o], 4), strict=True)))
    beta = cross_calibrate_beta(fit)
    print("beta (relative CDD change per K):", round(beta, 2))
    for pi in (0.0, 1.0):
        t = city_temperatures(fit, pi)
        idx = [YEARS.index(y) for y in CAL_YEARS]
        print(f"PI={pi}: tmax", np.round(t["tmax"][idx], 2), "dT_mean", np.round(t["dT_mean"][idx], 3))
    for i, y in enumerate(CAL_YEARS):
        obs = {o: np.average(data.temp[o][:, i] - data.temp[o][:, 0], weights=data.area) for o in OUTPUTS}
        print(y, "PALM-4U city mean change tmax %.3f tmin %.3f" % (obs["tmax"], obs["tmin"]))
