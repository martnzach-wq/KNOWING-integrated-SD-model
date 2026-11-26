"""
abm_base_year.py

Base-year mobility inputs from an ABM light export ("SD_model_results_baseyear" sheet):
trips, mean door-to-door travel time (min) and mean distance (km) per zone (internal / origin
destination), length class (short 0-2 km, medium 2-10 km, long > 10 km) and mode, for a working
day. The SD model takes, per zone, class and mode:

- trip rate = trips / zone population,
- trip length (km) and travel time (h),
- speed = length / time (for the mode-specific pkm method),
- class centroid = trip-weighted mean length over all modes.

Cells with fewer than ``min_trips`` trips (walking > 10 km) are set to zero trips; their length
and time follow the car length of the class at the walking speed of the medium class.

Usage: python abm_base_year.py <xlsx> <population internal> <population od> <out.json>
"""

from __future__ import annotations

import json
import sys

import numpy as np
import openpyxl

SD_MODES = ["car", "car passenger", "public transport", "bicycle", "walk"]
ABM_MODES = ["Car", "CarP", "PT", "Bike", "Walk"]
ZONES = {"internal traffic": "internal", "origin & destination traffic": "origin destination"}
CLASSES = {"short": "short", "medium": "medium", "long": "long"}


def read_abm_base_year(path: str, pop_internal: float, pop_od: float, min_trips: float = 1.0) -> dict:
    ws = openpyxl.load_workbook(path, data_only=True, read_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header = next(r for r in rows if r and "Mode" in r)
    # column blocks: trips, time, distance, each with the five ABM modes
    cols = {}
    for block, start in zip(("trips", "time", "dist"), (2, 7, 12), strict=True):
        cols[block] = {header[start + k]: start + k for k in range(5)}
    pops = {"internal": pop_internal, "origin destination": pop_od}
    out = {key: {z: {} for z in pops} for key in ("trips", "rate", "length_km", "time_h", "speed_kmh")}
    zone = None
    for r in rows:
        if not r or len(r) < 17:
            continue
        if isinstance(r[0], str) and r[0].strip().lower() in ZONES:
            zone = ZONES[r[0].strip().lower()]
        cls = r[1].split()[0].lower() if isinstance(r[1], str) else None
        if zone is None or cls not in CLASSES:
            continue
        trips = np.array([float(r[cols["trips"][m]] or 0.0) for m in ABM_MODES])
        time_h = np.array([np.nan if r[cols["time"][m]] is None else float(r[cols["time"][m]]) / 60 for m in ABM_MODES])
        dist = np.array([np.nan if r[cols["dist"][m]] is None else float(r[cols["dist"][m]]) for m in ABM_MODES])
        out["trips"][zone][cls] = trips
        out["time_h"][zone][cls] = time_h
        out["length_km"][zone][cls] = dist
    return _finish(out, pops, min_trips)


def read_abm_csv(path: str, pop_internal: float, pop_od: float, year: str = "base",
                 measure: str = "baseyear", min_trips: float = 1.0) -> dict:
    """As `read_abm_base_year`, from the long ABM light scenario export (one row per year, measure,
    zone, length class and mode)."""
    import pandas as pd

    d = pd.read_csv(path)
    d = d[(d["year"].astype(str) == year) & (d["measure"] == measure) & d["mode"].isin(ABM_MODES)]
    pops = {"internal": pop_internal, "origin destination": pop_od}
    out = {key: {z: {} for z in pops} for key in ("trips", "rate", "length_km", "time_h", "speed_kmh")}
    for (agg, cls), g in d.groupby(["aggregation", "distance_category"]):
        z, c = ZONES[agg.strip().lower()], cls.split()[0].lower()
        g = g.set_index("mode").reindex(ABM_MODES)
        out["trips"][z][c] = g["trips"].fillna(0).to_numpy(float).copy()
        out["time_h"][z][c] = g["avg_travel_time_min"].to_numpy(float).copy() / 60
        out["length_km"][z][c] = g["avg_travel_distance_km"].to_numpy(float).copy()
    return _finish(out, pops, min_trips)


def _finish(out: dict, pops: dict, min_trips: float) -> dict:
    walk = SD_MODES.index("walk")
    # classes without trips (e.g. short OD trips) take length and time of the internal class;
    # missing mode cells take the car values of the class
    for z in pops:
        for cls in CLASSES:
            if cls not in out["trips"][z]:
                out["trips"][z][cls] = np.zeros(len(SD_MODES))
                out["length_km"][z][cls] = np.full(len(SD_MODES), np.nan)
                out["time_h"][z][cls] = np.full(len(SD_MODES), np.nan)
            for key in ("length_km", "time_h"):
                v = out[key][z][cls]
                if np.isnan(v).all():
                    v[:] = out[key]["internal"][cls]
                v[np.isnan(v)] = v[0]
    for z in pops:
        walk_speed = out["length_km"][z]["medium"][walk] / out["time_h"][z]["medium"][walk]
        for cls in CLASSES:
            t, d, h = out["trips"][z][cls], out["length_km"][z][cls], out["time_h"][z][cls]
            sparse = t < min_trips
            t[sparse] = 0.0
            d[sparse] = d[0]
            h[sparse] = d[0] / walk_speed
            out["rate"][z][cls] = t / pops[z]
            out["speed_kmh"][z][cls] = d / h
    def centroid(z, cls):
        t, d = out["trips"][z][cls], out["length_km"][z][cls]
        return float((t * d).sum() / t.sum()) if t.sum() > 0 else centroid("internal", cls)

    out["centroid_km"] = {z: {cls: centroid(z, cls) for cls in CLASSES} for z in pops}
    out["population"] = pops
    return _jsonable(out)


def _jsonable(x):
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, np.ndarray):
        return [float(v) for v in x]
    return x


if __name__ == "__main__":
    src, pi, po, dst = sys.argv[1:5]
    reader = read_abm_csv if src.endswith(".csv") else read_abm_base_year
    data = reader(src, float(pi), float(po))
    with open(dst, "w") as f:
        json.dump(data, f, indent=1)
    for z, c in data["centroid_km"].items():
        print(z, {k: round(v, 2) for k, v in c.items()})
