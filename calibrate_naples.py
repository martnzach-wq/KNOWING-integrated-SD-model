"""
Bisection calibration: find mode_change_damping for Naples so that
car distance share (fossil + electric) is ~35% in 2050 under PI=1.
"""
import numpy as np
from city_config import NAPLES
from mobility import run_mobility

TARGET = 0.35   # 35% car distance share in 2050
TOL    = 0.001  # stop when within 0.1 pp


def car_share_2050(damping):
    NAPLES.mobility.mode_change_damping = damping
    mob = run_mobility(NAPLES, pi_scenario=1.0)
    ms  = mob["centroid"]
    car = ms["dist_car_fossil_km_cap_yr"][-1] + ms["dist_car_electric_km_cap_yr"][-1]
    tot = car + ms["dist_pt_km_cap_yr"][-1] + ms["dist_active_km_cap_yr"][-1]
    return car / tot if tot > 0 else 0.0


# car share is DECREASING in damping: high damping → low car share
# So we need lo (high car share) and hi (low car share) where:
#   car_share_2050(lo) > TARGET > car_share_2050(hi)
lo, hi = 0.01, 0.15

print(f"Brackets: damping={lo}  car={car_share_2050(lo):.1%}")
print(f"          damping={hi}  car={car_share_2050(hi):.1%}")
print(f"\nBisecting for {TARGET:.0%} target ...")

for _ in range(40):
    mid = (lo + hi) / 2
    s   = car_share_2050(mid)
    print(f"  damping={mid:.4f}  car_2050={s:.2%}")
    if s > TARGET:
        lo = mid   # too little mode change, increase damping
    else:
        hi = mid   # too much mode change, decrease damping
    if (hi - lo) < TOL:
        break

best = (lo + hi) / 2
final = car_share_2050(best)
print(f"\nCalibrated mode_change_damping = {best:.4f}")
print(f"Car distance share 2050        = {final:.2%}  (target {TARGET:.0%}")
