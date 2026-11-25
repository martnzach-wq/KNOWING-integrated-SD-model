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


# OD / internal mean trip length per mode in Tallinn (mob_inputs.csv: rates x centroids,
# internal 7.8/7.7/7.8/4.1/1.7 km, OD 24.4/24.2/23.3/18.7/4.5 km), used as structural prior
OD_LENGTH_RATIO = np.array([3.13, 3.16, 2.97, 4.51, 2.67])


def estimate(city: str, pop_internal: float, pop_od: float, od_ratio=OD_LENGTH_RATIO) -> dict:
    """Rates and centroids per zone: residents and the OD zone make trips at the same rate
    per person; OD trips are longer by the Tallinn ratio per mode, with the trip-weighted
    mean per mode equal to the ABM light mean."""
    trips, pkm = (np.array(v) * 1e6 for v in ABM[city])
    s = pop_od / (pop_internal + pop_od)
    mean = pkm / trips
    mean_int = mean / (1 - s + s * od_ratio)
    out = {}
    for zone, zmean, share, pop in (("internal", mean_int, 1 - s, pop_internal), ("od", mean_int * od_ratio, s, pop_od)):
        shares, means = zip(*(class_shares(m) for m in zmean), strict=True)
        shares, means = np.array(shares), np.array(means)
        class_trips = shares * trips[:, None] * share
        out[f"centroid_{zone}"] = (class_trips * means).sum(0) / class_trips.sum(0)
        out[f"rate_{zone}"] = class_trips.T / pop
        out[f"pkm_{zone}"] = (class_trips * out[f"centroid_{zone}"][None, :]).sum(1)
    out["pkm_fit"] = (out["pkm_internal"] + out["pkm_od"]) / pkm
    out["od_pkm_share"] = out["pkm_od"].sum() / (out["pkm_internal"] + out["pkm_od"]).sum()
    return out


if __name__ == "__main__":
    for city, pops in {"NAPLES": (954_318, 2_050_000), "SOUTH_WESTPHALIA": (1_381_751, 1_738_000)}.items():
        r = estimate(city, *pops)
        print(city, "centroids internal", np.round(r["centroid_internal"], 2), "od", np.round(r["centroid_od"], 2),
              "pkm fit", np.round(r["pkm_fit"], 2), "OD pkm share %.2f" % r["od_pkm_share"])  # fmt: skip
