"""
estimate_trip_classes.py

Trip rates by length class and class centroids for cities without a travel
survey table, derived from the ABM light base year of the KNOWING deliverables
(trips and passenger-km by mode, internal + OD traffic).

Method: the trip length of each mode follows an exponential distribution with
the ABM mean (pkm / trips). Classes: short < 3 km, medium 3-15 km, long > 15 km.
The share of a mode's trips in each class and the conditional mean length per
class follow from the distribution; the class centroid (shared by all modes,
as in the SD model) is the trip-weighted conditional mean. Trips are split
between residents and the OD zone by the OD share of the population.

Sources: D3.4a Fig. A-87/A-88 (Naples), D3.5 Fig. 47/48 (South Westphalia).
"""

from __future__ import annotations

import numpy as np

BOUNDS = (3.0, 15.0)
MODES = ["car", "car passenger", "public transport", "bicycle", "walk"]

ABM = {  # Mio trips/day, Mio pkm/day (2019)
    "NAPLES": ([1.187, 0.376, 1.072, 0.156, 0.337], [17.6, 5.1, 13.2, 0.8, 0.5]),
    "SOUTH_WESTPHALIA": ([2.917, 0.595, 0.872, 0.460, 0.759], [75.3, 13.0, 16.9, 5.1, 0.7]),
}


def class_shares(mean: float) -> tuple[np.ndarray, np.ndarray]:
    """Trip shares and conditional mean lengths of the three classes for an exponential distribution."""
    a, b = BOUNDS
    cdf = lambda x: 1 - np.exp(-x / mean)  # noqa: E731

    def cond_mean(lo, hi):
        # E[X | lo < X < hi] for an exponential distribution
        num = (lo + mean) * np.exp(-lo / mean) - ((hi + mean) * np.exp(-hi / mean) if np.isfinite(hi) else 0.0)
        return num / (np.exp(-lo / mean) - (np.exp(-hi / mean) if np.isfinite(hi) else 0.0))

    shares = np.array([cdf(a), cdf(b) - cdf(a), 1 - cdf(b)])
    means = np.array([cond_mean(0, a), cond_mean(a, b), cond_mean(b, np.inf)])
    return shares, means


def estimate(city: str, pop_internal: float, pop_od: float) -> dict:
    trips, pkm = (np.array(v) * 1e6 for v in ABM[city])
    shares, means = zip(*(class_shares(p / t) for t, p in zip(trips, pkm, strict=True)), strict=True)
    shares, means = np.array(shares), np.array(means)  # [mode, class]
    class_trips = shares * trips[:, None]
    centroid = (class_trips * means).sum(0) / class_trips.sum(0)
    od_share = pop_od / (pop_internal + pop_od)
    rate_int = class_trips.T * (1 - od_share) / pop_internal  # [class, mode]
    rate_od = class_trips.T * od_share / pop_od
    fit = (class_trips * centroid[None, :]).sum(1) / pkm
    return {"centroid": centroid, "rate_internal": rate_int, "rate_od": rate_od, "pkm_fit": fit}


if __name__ == "__main__":
    for city, pops in {"NAPLES": (954_318, 250_000), "SOUTH_WESTPHALIA": (1_381_751, 437_000)}.items():
        r = estimate(city, *pops)
        print(city, "centroids (km)", np.round(r["centroid"], 2), "pkm fit by mode", np.round(r["pkm_fit"], 2))
        for name in ("rate_internal", "rate_od"):
            print(" ", name)
            for cl, row in zip(("short", "medium", "long"), r[name], strict=True):
                print("   ", cl, np.round(row, 5).tolist())
