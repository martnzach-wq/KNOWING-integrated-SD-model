"""
mobility.py

Python (Euler, annual time step) translation of Submodel_Mobility_v10.mdl,
parametrized by a CityConfig so the same code runs for any city.

Faithful to the original Vensim equations:
    TR Trips[mode,trip length,traffic type,coping type] = INTEG(...)
    TR GeneralisedCost = Cost + TravelTime * ValueOfTime - Attractiveness
    TR DemandChangeRate = -DemandElasticity * dGC/10 * Trips
    TR ModeChangeRate = ModeChangeElasticity * (GC_mode - GC_mode2) * Trips[loser]

Two PKM methods are computed side by side for comparison (per explicit
request, not silently resolved):
    - "centroid": TR InitialTripLength[traffic type, trip length] -- the
      ORIGINAL Vensim approach, a single distance per trip-length class,
      shared across all modes. This is what mob_inputs.csv natively
      provides for Tallinn.
    - "mode_specific": empirical TR_TripLength[z, mode] derived (for
      Tallinn) from TR InitialTravelSpeed[mode, trip length, traffic type]
      x estimated travel time, OR taken directly from
      city.mobility.mode_specific_trip_length if supplied (as was done for
      Granollers v8).
"""

from __future__ import annotations
import numpy as np
from city_config import (
    CityConfig, MODES, CAR_MODES, ACTIVE_MODES, NON_CAR_MODES,
    TRIP_LENGTHS, TRAFFIC_TYPES, COPING_TYPES, YEARS,
)

N_MODE = len(MODES)
N_TL = len(TRIP_LENGTHS)
N_TT = len(TRAFFIC_TYPES)
N_CT = len(COPING_TYPES)

MODE_IDX = {m: i for i, m in enumerate(MODES)}
TL_IDX = {t: i for i, t in enumerate(TRIP_LENGTHS)}

# TR AttractivenessProfile[mode, coping type]: modes car, car passenger, PT, bicycle, walk
PROFILE_GENERIC = np.array([
    [3, 2, 1, -1, -2, -3],
    [3, 2, 1, -1, -2, -3],
    [3, 2, 1, 0, -1, -2],
    [-3, -2, -1, 1, 3, 2],
    [-3, -2, -1, 1, 3, 2],
])
PROFILE_TALLINN = np.array([
    [3, 2, 1, -1, -2, -3],
    [-3, -2, -1, 1, 3, 2],
    [3, 2, 1, 0, -1, -2],
    [-3, -2, -1, 0, 2, 3],
    [-3, -2, -1, 1, 3, 2],
])


_THETA_CACHE: dict = {}


def _rake(seed: np.ndarray, row_tot: np.ndarray, col_tot: np.ndarray, iters: int = 200) -> np.ndarray:
    """Iterative proportional fitting of ``seed`` (mode x coping type) to row and column totals."""
    x = seed.copy()
    for _ in range(iters):
        x *= (row_tot / np.maximum(x.sum(1), 1e-300))[:, None]
        x *= (col_tot / np.maximum(x.sum(0), 1e-300))[None, :]
    return x


def split_by_coping_type(init_trips: np.ndarray, dist: np.ndarray, profile: np.ndarray, theta: float) -> np.ndarray:
    """Initial trips [mode, length, zone, coping type]: per length class and zone, the mode totals
    of ``init_trips`` and the coping-type shares ``dist`` are kept, and the type deviations follow
    exp(theta * profile) (D45)."""
    out = np.zeros(init_trips.shape + (len(dist),))
    w = np.exp(theta * profile)
    for tl in range(init_trips.shape[1]):
        for tt in range(init_trips.shape[2]):
            rows = init_trips[:, tl, tt]
            if rows.sum() <= 0:
                continue
            seed = rows[:, None] * dist[None, :] * w
            out[:, tl, tt, :] = _rake(seed, rows, dist / dist.sum() * rows.sum())
    return out


def car_odds_ratio_type_a(trips0: np.ndarray) -> float:
    """Odds of car (driver) use of coping type A over the odds of the whole population."""
    a = trips0[..., 0].sum(axis=(1, 2))
    tot = trips0.sum(axis=(1, 2, 3))
    pa, p = a[0] / a.sum(), tot[0] / tot.sum()
    return (pa / (1 - pa)) / (p / (1 - p))
TT_IDX = {t: i for i, t in enumerate(TRAFFIC_TYPES)}


def _interp_series(policy_dict: dict, years=YEARS) -> np.ndarray:
    """Vensim GET XLS Lookup-style linear interpolation from sparse keyframes."""
    if not policy_dict:
        return np.zeros(len(years))
    xs = sorted(policy_dict.keys())
    ys = [policy_dict[x] for x in xs]
    return np.interp(years, xs, ys)


class MobilityModel:
    def __init__(self, city: CityConfig, pi_scenario: float = 1.0,
                 pkm_method: str = "centroid", mode_change_damping: float = None):
        """
        pi_scenario: 0.0 = BAU (no policy intervention), 1.0 = PI=1 (full activation)
        pkm_method: "centroid" or "mode_specific" -- see module docstring
        mode_change_damping: multiplier on TR ModeChangeElasticity. If None
            (default), uses city.mobility.mode_change_damping (per-city
            calibrated value: Tallinn=0.264, Granollers=0.84 -- see
            CityConfig field docstring and run() docstring for
            justification). Passing an explicit value here overrides the
            config default, mainly for re-calibration/sensitivity testing.
        """
        self.city = city
        self.m = city.mobility
        self.pi = pi_scenario
        self.pkm_method = pkm_method
        self.mode_change_damping = (
            mode_change_damping if mode_change_damping is not None
            else self.m.mode_change_damping
        )
        self.years = np.array(YEARS)
        self.n_years = len(YEARS)
        self._build_inputs()

    # ------------------------------------------------------------------
    def _build_inputs(self):
        m = self.m

        # Population by traffic type, with optional net increase
        pop_inc_int = _interp_series(m.pop_net_increase_internal)
        pop_inc_od = _interp_series(m.pop_net_increase_od)
        self.population = {
            "internal": self._cumulative_pop_increase(pop_inc_int, m.population_internal),
            "origin destination": self._cumulative_pop_increase(pop_inc_od, m.population_od),
        }

        # Centroid trip lengths [traffic_type][trip_length] (km) -- constant
        self.trip_length_centroid = {
            "internal": dict(zip(TRIP_LENGTHS, m.initial_trip_length_internal)),
            "origin destination": dict(zip(TRIP_LENGTHS, m.initial_trip_length_od)),
        }

        # Mode-specific trip lengths (km), if available/derivable
        self.trip_length_mode_specific = self._derive_mode_specific_trip_length()

        # Policy series
        self.car_costs_fuel = (
            np.full(self.n_years, m.car_cost_per_km_fuel_constant)
            if m.car_cost_per_km_fuel_constant is not None
            else _interp_series(m.policy_car_costs_fuel)
        )
        self.car_costs_ev = (
            np.full(self.n_years, m.car_cost_per_km_ev_constant)
            if m.car_cost_per_km_ev_constant is not None
            else _interp_series(m.policy_car_costs_ev)
        )
        self.street_green = _interp_series(m.policy_street_green)
        # coping-type distribution per year (static unless a 2050 behaviour scenario is given)
        d0 = np.asarray(m.coping_type_distribution, dtype=float)
        d1 = np.asarray(m.coping_type_distribution_2050, dtype=float) if m.coping_type_distribution_2050 else d0
        w = (np.asarray(YEARS) - 2019) / (2050 - 2019)
        self.coping_dist_t = (1 - w)[:, None] * d0[None, :] + w[:, None] * d1[None, :]
        self.cycling_resistance = (
            _interp_series(m.cycling_resistance_reduction) if m.cycling_resistance_reduction else None
        )
        self.calming_bonus = {mo: _interp_series(v) for mo, v in (m.traffic_calming_time_bonus or {}).items()}
        self.fifteen_bonus = {mo: _interp_series(v) for mo, v in (m.fifteen_minute_time_bonus or {}).items()}
        # cooling degree days per year (MAED-City trajectory, microclimate effect of greening)
        from microclimate import run_microclimate

        self.microclimate = run_microclimate(self.city, self.pi)
        self.cdd = self.microclimate["cdd"]
        self.capacity_adapt = _interp_series(m.policy_capacity_adaptation)
        self.parking_adapt = _interp_series(m.policy_parking_cost_adaptation)
        self.area_toll = _interp_series(m.policy_area_toll)
        self.road_pricing = _interp_series(m.policy_road_pricing)
        self.cycling_attr = _interp_series(m.policy_cycling_attractiveness)
        self.pt_traveltime_adapt = _interp_series(m.policy_pt_traveltime_adaptation)
        self.distance_adapt = _interp_series(m.policy_distance_adaptation)
        self.car_pass_attr = _interp_series(m.policy_car_passenger_attractiveness)
        self.ev_adopt_adapt = _interp_series(m.policy_ev_adoption_adaptation)

        # PI multipliers: 0 = BAU, 1 = full intervention (TR PI xxx)
        # NOTE: by explicit decision, Tallinn's policy intensity at PI=1 is
        # NOT software-capped (unlike the Granollers v8 workaround that
        # held several PIs constant from 2040 onward to prevent a runaway
        # car-stock drain). The full strength of the mob_inp10.xlsx policy
        # series is used as-is through 2050. If the resulting modal shift
        # is judged too aggressive, the correction belongs in the XLSX
        # policy time series themselves, not in this code.
        self.PI_Capacity = self.pi
        self.PI_Parking = self.pi
        self.PI_AreaToll = self.pi if m.area_toll_applicable else 0.0
        self.PI_RoadPricing = self.pi
        self.PI_Cycling = self.pi
        self.PI_PTTravelTime = self.pi
        self.PI_DistanceAdapt = self.pi
        self.PI_CarPassenger = self.pi
        self.PI_EVAdoption = self.pi

        # GC-neutral BaseAttr calibration (see _compute_baseattr_calibration
        # docstring): computed AFTER all the above inputs are ready, since it
        # needs car_costs_fuel[0] and the trip-length/rate tables.
        # GC-neutral BaseAttr calibration (see _compute_baseattr_calibration
        # docstring): only applied when the city explicitly opts in via
        # apply_cdd_baseattr_compensation. Tallinn needs this because its
        # GC formula (translated from Submodel_Mobility_v10.mdl) produces
        # an initial-condition mismatch against the REAL 2019 trip
        # distribution. Granollers' own TR_BaseAttr values were already
        # hand-tuned in the original script to reproduce the right
        # equilibrium WITHOUT this correction -- applying it on top would
        # double-correct and distort the calibration (this was exactly the
        # bug found when validating Granollers' migration: PT GC was
        # getting a +2.49 correction it should never have received).
        if m.apply_cdd_baseattr_compensation:
            self.baseattr_correction = self._compute_baseattr_calibration()
        else:
            self.baseattr_correction = {mo: 0.0 for mo in MODES}

    def _compute_baseattr_calibration(self):
        """
        GC-neutral BaseAttr calibration (same principle used for Granollers,
        documented in project history: "Mediterranean climate penalty
        requires GC-neutral BaseAttr calibration to compensate... otherwise
        BAU drifts without policy activation").

        Without this, Tallinn's modelled GC at t=0 already favours car over
        PT/active modes relative to the REAL, empirically-observed 2019 trip
        distribution (mob_inputs.csv) -- meaning the simulation would start
        drifting away from car immediately, regardless of any policy
        activation, simply because the GC formula's cost/time/attractiveness
        terms don't fully capture whatever non-modelled factors (PT being
        fare-free since 2013, established travel habits, etc.) keep real
        Tallinn residents on PT and walking at the rates they do.

        This computes, once, a per-mode additive attractiveness correction
        that brings each mode's trip-weighted average GC (using the REAL
        2019 trip distribution as weights) to the trip-share-weighted
        system average GC -- i.e. a mode that already carries its
        "natural" GC-implied share gets no correction; a mode whose real
        share is far from what its GC alone would imply gets pulled toward
        equilibrium. The correction is applied as a flat additive term to
        attractiveness for that mode, identical across all coping types
        (preserving the coping-type spread, shifting only the baseline).
        """
        m = self.m
        init_trips = np.zeros((N_MODE, N_TL, N_TT))
        for tt in TRAFFIC_TYPES:
            tti = TT_IDX[tt]
            pop0 = self.population[tt][0]
            for tl in TRIP_LENGTHS:
                tli = TL_IDX[tl]
                rates = np.array(m.initial_trip_rate[tt][tl])
                init_trips[:, tli, tti] = pop0 * rates

        total = init_trips.sum()
        empirical_share = {mode: init_trips[MODE_IDX[mode]].sum() / total for mode in MODES}

        gc0 = self._generalised_cost(0, self.car_costs_fuel[0], None, baseattr_correction=None)
        mode_gc = {}
        for mode in MODES:
            mi = MODE_IDX[mode]
            w = init_trips[mi]
            gc_slice = gc0[mi, :, :, :].mean(axis=2)
            mode_gc[mode] = (gc_slice * w).sum() / w.sum()

        system_avg_gc = sum(mode_gc[mode] * empirical_share[mode] for mode in MODES)
        return {mode: mode_gc[mode] - system_avg_gc for mode in MODES}

    def _cumulative_pop_increase(self, increase_series, initial_pop):
        """Vensim HB Population = INTEG(PopNetIncrease, InitialPopulation)."""
        pop = np.zeros(self.n_years)
        pop[0] = initial_pop
        for i in range(1, self.n_years):
            pop[i] = pop[i - 1] + increase_series[i]
        return pop

    def _derive_mode_specific_trip_length(self):
        """
        Derive empirical mode-specific trip lengths from
        TR InitialTravelSpeed[mode, trip length, traffic type] (mob_inputs.csv)
        combined with the centroid distance / centroid-implied travel time,
        following the same logic that produced TR_TripLength[z,m] for
        Granollers: distance = speed x travel_time, where travel_time is
        backed out from the centroid distance and an assumed "reference"
        mode's speed (here: car, the mode whose centroid distance is most
        directly observable).

        If the city supplies an explicit override (as Granollers v8 did),
        that is used directly instead.
        """
        if self.m.mode_specific_trip_length is not None:
            return self.m.mode_specific_trip_length

        if not self.m.initial_travel_speed:
            return None  # not derivable -- centroid-only city

        result = {}
        for tt in TRAFFIC_TYPES:
            result[tt] = {}
            speed_table = self.m.initial_travel_speed[tt]  # {trip_length: [5 mode speeds]}
            centroid = (self.m.initial_trip_length_internal if tt == "internal"
                        else self.m.initial_trip_length_od)
            # Reference travel time per trip-length class, backed out using
            # the car mode's speed and the centroid distance (car trips are
            # least likely to detour, making this the most stable anchor)
            car_i = MODE_IDX["car"]
            ref_travel_time = {
                tl: centroid[TL_IDX[tl]] / speed_table[tl][car_i]
                for tl in TRIP_LENGTHS
            }
            for mode in MODES:
                mi = MODE_IDX[mode]
                # weight by (approximate) trip share per trip-length class
                # using InitialTripRate as weights
                rates = self.m.initial_trip_rate[tt]
                weights = np.array([rates[tl][mi] for tl in TRIP_LENGTHS])
                if weights.sum() <= 0:
                    result[tt][mode] = float(np.mean(centroid))
                    continue
                dists = np.array([
                    speed_table[tl][mi] * ref_travel_time[tl] for tl in TRIP_LENGTHS
                ])
                result[tt][mode] = float(np.average(dists, weights=weights))
        return result

    def _ev_share_target_curve(self):
        """
        EV FLEET share trajectory (PI=1 / full-policy target).

        If the city supplies an explicit ev_pi_trajectory (e.g. Granollers'
        EV_PI = [2019:0.2%, 2022:1.5%, 2025:7%, 2028:14%, 2030:20%, 2040:55%,
        2050:80%], transcribed verbatim from granollers_integrated_model.py),
        that is used directly.

        Otherwise (Tallinn): an evidence-anchored trajectory replacing the
        original Vensim formula's "Time>10 years" gate-then-ramp logic
        (which, when run from a 2019 start, incorrectly held EV share at
        exactly 0% through 2028 -- not what's actually happened in Estonia).

        Historical anchors (fleet share = cumulative registered EVs /
        total Estonian vehicle fleet ~930k-1.17M, derived from elektriauto.ee,
        EAFO and Wikipedia "Electric car use by country" cumulative
        registration figures):
            2019: ~0.03%  (<1% of NEW sales that year; fleet stock minimal)
            2022: ~0.2%   (1,995 cumulative PEV registrations)
            2023: ~0.35%  (~3,700 cumulative, "over 2,000 by mid-2023" + 2023 subsidy cohort)
            2024: ~1.0%   (fleet exceeded 10,000 units)
            2026: ~1.1%   (>10,000, continued growth)

        Forward trajectory to 2050: anchored to Estonia's OWN stated policy
        ambition -- a proposed ban on new petrol/diesel car sales from
        2030 and hybrid sales from 2035, plus a "1 million green vehicles
        by 2030" target (EAFO, Dec 2025) -- tempered by the EU's December
        2025 dilution of the 2035 100% zero-emission mandate to a 90%
        reduction requirement (allowing hybrids/ICE with offsets beyond
        2035), which makes a literal 100% fleet outcome unlikely even if
        Estonia's own ban proceeds as proposed. 2050 fleet share is set at
        85% (high end of an explicitly "70-90%+" ambitious range) rather
        than the more conservative 41% the unmodified Vensim formula
        produced -- by explicit decision, reflecting Estonia's stated
        policy direction rather than a software default.

        This is fleet STOCK share (slow-moving, since the existing car
        stock turns over gradually), not new-registration share (which is
        already far higher today, e.g. ~9.7% in 2024) -- the two should
        not be confused.
        """
        if self.m.ev_pi_trajectory is not None:
            years_anchor = sorted(self.m.ev_pi_trajectory.keys())
            values_anchor = [self.m.ev_pi_trajectory[y] for y in years_anchor]
            return np.interp(self.years, years_anchor, values_anchor)
        anchor_years = [2019, 2022, 2023, 2024, 2026, 2030, 2035, 2040, 2050]
        anchor_values = [0.03, 0.2, 0.35, 1.0, 1.1, 8.0, 30.0, 55.0, 85.0]
        return np.interp(self.years, anchor_years, anchor_values)

    # ------------------------------------------------------------------
    def run(self):
        """Euler-integrate TR Trips over 2019-2050, annual step. Returns a
        dict of result arrays."""
        n = self.n_years
        shape = (n, N_MODE, N_TL, N_TT, N_CT)
        trips = np.zeros(shape)

        m = self.m
        coping_dist = np.array(m.coping_type_distribution)

        # TR InitialTrips[mode, trip length, traffic type] = InitPop[tt] * InitialTripRate
        init_trips = np.zeros((N_MODE, N_TL, N_TT))
        for tt in TRAFFIC_TYPES:
            tti = TT_IDX[tt]
            pop0 = self.population[tt][0]
            for tl in TRIP_LENGTHS:
                tli = TL_IDX[tl]
                rates = np.array(m.initial_trip_rate[tt][tl])  # 5 modes
                init_trips[:, tli, tti] = pop0 * rates

        # initial condition: TR Trips = InitialTrips * CopingTypesDistribution; with
        # initial_split_by_coping_type the types start from their own mode split (D45)
        if m.initial_split_by_coping_type:
            profile = PROFILE_GENERIC if m.base_attr_by_mode_and_zone is not None else PROFILE_TALLINN
            target = m.coping_car_odds_ratio_type_a
            key = (init_trips.tobytes(), coping_dist.tobytes(), profile.tobytes(), target)
            if key not in _THETA_CACHE:
                lo, hi = 0.0, 2.0
                for _ in range(40):
                    theta = (lo + hi) / 2
                    split = split_by_coping_type(init_trips, coping_dist, profile, theta)
                    lo, hi = (theta, hi) if car_odds_ratio_type_a(split) < target else (lo, theta)
                _THETA_CACHE[key] = (lo + hi) / 2
            self.coping_theta = _THETA_CACHE[key]
            trips[0] = split_by_coping_type(init_trips, coping_dist, profile, self.coping_theta)
        else:
            for ci in range(N_CT):
                trips[0, :, :, :, ci] = init_trips * coping_dist[ci]

        # --- EV adoption: evidence-anchored trajectory (see
        # _ev_share_target_curve docstring), replacing the original Vensim
        # gate-then-ramp formula which incorrectly produced exactly 0% EV
        # share through 2028 when run from a 2019 start -- contradicted by
        # Estonia's real, already-underway EV uptake (elektriauto.ee, EAFO).
        # PI=1 follows the full ambitious curve (anchored to Estonia's
        # proposed ICE sales ban, tempered by the EU's Dec-2025 mandate
        # dilution); BAU follows a damped version reaching roughly half the
        # PI=1 2050 value, since organic market growth without policy
        # reinforcement (charging infrastructure investment, purchase
        # incentives, etc.) plausibly undershoots the policy-driven case --
        # while both scenarios share the SAME historical anchors through
        # 2026 (already observed, not a policy outcome).
        ev_target_pi1 = self._ev_share_target_curve()
        if self.m.ev_bau_damping_pivot_year is not None:
            # Tallinn-specific: BAU follows a damped version of the PI=1
            # curve from the last shared historical anchor year onward,
            # reaching roughly half the PI=1 2050 value (organic market
            # growth without policy reinforcement plausibly undershoots
            # the policy-driven case).
            pivot = self.m.ev_bau_damping_pivot_year
            pivot_idx = list(self.years).index(pivot)
            ev_target_bau = np.where(
                self.years <= pivot, ev_target_pi1,
                ev_target_pi1[pivot_idx] + (ev_target_pi1 - ev_target_pi1[pivot_idx]) * 0.5
            )
        else:
            # No separate BAU damping configured (e.g. Granollers, whose
            # original script only documents a single PI=1 EV trajectory)
            # -- the same EV curve applies regardless of scenario.
            ev_target_bau = ev_target_pi1
        # behaviour model: EV gap (full policy - BAU) scaled by the compliance with the combustion-car
        # sales ban, relative to the 2019 coping-type distribution (1 without a coping scenario)
        ev_gap_factor = np.ones(n)
        if m.ev_ban_compliance_by_type is not None:
            comp = np.asarray(m.ev_ban_compliance_by_type)
            ev_gap_factor = (self.coping_dist_t @ comp) / float(self.coping_dist_t[0] @ comp)
        ev_share = ev_target_bau + (ev_target_pi1 - ev_target_bau) * self.pi * ev_gap_factor

        car_i = MODE_IDX["car"]
        carpass_i = MODE_IDX["car passenger"]
        pt_i = MODE_IDX["public transport"]
        bike_i = MODE_IDX["bicycle"]
        walk_i = MODE_IDX["walk"]

        logit = self.m.mode_choice == "logit"
        if logit:
            # pivot point of the logit mode choice: base-year shares and generalised cost (D51)
            car_cost0 = (self.car_costs_fuel[0] * (1 - ev_share[0] / 100)
                         + self.car_costs_ev[0] * ev_share[0] / 100)
            gc_base = self._generalised_cost(0, car_cost0, trips[0])
            share_base = trips[0] / np.maximum(trips[0].sum(axis=0, keepdims=True), 1e-12)
            heat_beta = np.array([self.m.heat_active_per_cdd if mo in ACTIVE_MODES
                                  else self.m.heat_pt_per_cdd if mo == "public transport" else 0.0
                                  for mo in MODES])

        for t in range(1, n):
            prev = trips[t - 1]
            ev_prev = ev_share[t - 1]

            car_cost_per_km = (self.car_costs_fuel[t - 1] * (1 - ev_prev / 100)
                                + self.car_costs_ev[t - 1] * ev_prev / 100)

            # --- Generalised cost per [mode, trip_length, traffic_type, coping_type] ---
            gc = self._generalised_cost(t - 1, car_cost_per_km, prev)


            # --- Demand change (own-mode elasticity response) ---
            demand_elasticity = 0.01
            # NOTE: mode_change_damping is a deliberate, EXPLICIT calibration
            # knob (default 1.0 = no damping = full original Vensim
            # elasticity), added after confirming that an earlier Vensim
            # PI=1 run reportedly landed near ~20% car share by 2050,
            # whereas the unmodified elasticity converges toward ~1%. Three
            # candidate causes were checked and ruled out first: (1)
            # TR Cal AreaToll / TR Cal RoadPricing calibration factors are
            # both flat 1 in the .mdl (no hidden moderation), (2) TIME STEP
            # coarseness (tested monthly sub-stepping -- result unchanged,
            # ruling out a numerical-integration cause), (3) TR ParkingCost
            # was found to be a real missing term (1.5 EUR/trip, now fixed
            # below) but acts in the wrong direction to explain the gap.
            # This means the discrepancy is most likely because the actual
            # historical Vensim PI=1 run did not apply every policy lever
            # at full simultaneous mob_inp10.xlsx strength (the same
            # "policy-stacking" issue documented for Granollers, where
            # several PIs were explicitly capped at their 2040 values for
            # the same reason). Rather than re-capping individual policy
            # levers, a general damping factor on the mode-change response
            # itself is used instead, by explicit decision -- this affects
            # the SPEED of mode-shift uniformly across all mode pairs,
            # without favouring or specially treating any one policy lever.
            mode_change_elasticity = 0.01 * getattr(self, "mode_change_damping", 1.0)
            gc_prev_step = gc  # GC of previous timestep approximated by current
            # (DELAY FIXED with TIME STEP=1yr collapses to same-step value
            # in an annual-step Euler scheme on the first pass; the dynamic
            # term TR DemandChangeRate is therefore dominated by
            # TR ModeChangeRate, consistent with how this model behaves
            # in practice at coarse time steps)
            demand_change = -demand_elasticity * 0 / 10 * prev  # negligible at dGC=0 same-step

            # --- Mode-change (inter-mode shifts driven by GC differences) ---
            mode_change = np.zeros_like(prev)
            weighted = self.m.mode_change_destination_weighting
            if logit:
                heat = (1 - heat_beta * self.cdd[t]) / (1 - heat_beta * self.cdd[0])
                utility = np.log(np.maximum(share_base, 1e-300)) - self.m.logit_scale * (gc - gc_base)
                utility += np.log(heat)[:, None, None, None]
                utility -= utility.max(axis=0, keepdims=True)
                target = np.exp(utility) * (share_base > 0)
                target /= np.maximum(target.sum(axis=0, keepdims=True), 1e-300)
                total = prev.sum(axis=0, keepdims=True)
                share_prev = prev / np.maximum(total, 1e-12)
                mode_change = total * self.m.logit_adjustment * (target - share_prev)
            for tl in range(N_TL if not logit else 0):
                for tt in range(N_TT):
                    for ci in range(N_CT):
                        gc_slice = gc[:, tl, tt, ci]
                        trip_slice = prev[:, tl, tt, ci]
                        net = np.zeros(N_MODE)
                        if weighted:
                            total = max(trip_slice.sum(), 1e-12)
                            a = self.m.mode_change_destination_blend
                            dest_weight = 1 - a + a * N_MODE * np.maximum(trip_slice, 0) / total
                        for i in range(N_MODE):
                            for j in range(N_MODE):
                                if i == j:
                                    continue
                                diff = gc_slice[i] - gc_slice[j]
                                i_worse = (gc_slice[j] - gc_slice[i]) < 0
                                source = trip_slice[i] if i_worse else trip_slice[j]
                                rate = mode_change_elasticity * diff * max(source, 0)
                                if weighted:
                                    rate *= dest_weight[j if i_worse else i]
                                net[i] -= rate
                        mode_change[:, tl, tt, ci] = net

            # --- Coping-type re-weighting (DemandIncreaseCT) ---
            # trips of each coping type scale with its population share; the term vanishes
            # for a static distribution
            ct_now = self.coping_dist_t[t]
            ct_prev = self.coping_dist_t[t - 1]
            ratio = np.divide(ct_now, ct_prev, out=np.ones_like(ct_now), where=ct_prev > 0)
            demand_increase_ct = prev * (ratio - 1)[None, None, None, :]

            new_trips = prev + demand_change + mode_change + demand_increase_ct
            new_trips = np.maximum(new_trips, 0)
            new_trips = self._shorter_trips(new_trips, t)
            if not logit:  # the logit target carries the heat effect
                new_trips = self._heat_transfer(new_trips, t)
            trips[t] = new_trips

        self.trips = trips
        self.ev_share = ev_share
        return self._summarise()

    # ------------------------------------------------------------------
    def _generalised_cost(self, t_idx, car_cost_per_km, trips_now, baseattr_correction="use_calibrated"):
        """TR GeneralisedCost[mode, trip_length, traffic_type, coping_type].

        baseattr_correction: "use_calibrated" (default, normal operation) ->
        uses self.baseattr_correction computed once at init; None -> skip
        the correction entirely (used internally, once, to COMPUTE that
        calibration in the first place, to avoid a circular dependency)."""
        gc = np.zeros((N_MODE, N_TL, N_TT, N_CT))

        if baseattr_correction == "use_calibrated":
            correction = getattr(self, "baseattr_correction", None) or {m: 0.0 for m in MODES}
        else:
            correction = {m: 0.0 for m in MODES}

        m = self.m
        generic_mode = m.base_attr_by_mode_and_zone is not None

        if generic_mode:
            # Granollers-style: base attractiveness is 2D (mode, zone),
            # scaled by an explicit attr_distinction multiplier on the
            # coping-type profile.
            base_attr_2d = m.base_attr_by_mode_and_zone
            attr_distinction = m.attr_distinction
            attr_profile = PROFILE_GENERIC
            value_of_time = m.value_of_time_base + m.value_of_time_dist * np.array(m.value_of_time_profile)
            parking_cost_base = m.parking_cost_base
            pt_cost_internal, pt_cost_od = m.pt_cost_by_zone
            street_green_term = self.street_green[t_idx] if hasattr(self, "street_green") else 0.0
            if m.street_green_by_pi:  # coupled with the capacity measures and scaled by the PI (D55)
                street_green_term *= self.pi * m.lever_calibration.get("street_green", 1.0)
        else:
            # Tallinn-style: flat per-mode base attractiveness (no zone
            # dimension), attr_distinction implicitly 1.0.
            base_attr = {"car": 2, "car passenger": 3, "public transport": 2.5,
                         "bicycle": 5, "walk": 5}
            attr_profile = PROFILE_TALLINN
            # NOTE: TR AttractivenessProfile[mode, coping type] rows in the
            # .mdl are given in the order: active modes (bicycle,walk share one
            # row group), public transport, car modes (car,car passenger) --
            # the .mdl lists 5 rows for the 5 distinct subscript groups it
            # cycles through (active x2 use same row twice differently keyed).
            # Re-derived explicitly above per mode for clarity in this
            # translation; sign convention matches the .mdl listing order.
            attr_distinction = m.attr_distinction  # Tallinn: fitted so the coping-type spread stays stable (D46)
            value_of_time_base = m.value_of_time_base  # was fixed at 15; class B, set per city
            vot_profile = np.array([3, -2, 2, -3, -1, 1])
            # coping-type profile relative to the mdl base of 15 EUR/h, so that it scales with the
            # configured value of time (D39, D46)
            value_of_time = value_of_time_base * (1 + m.value_of_time_profile_scale * vot_profile / 15.0)
            parking_cost_base = m.parking_cost_base  # 1.5 default
            pt_cost_internal, pt_cost_od = 0.0, 0.72
            street_green_term = 0.0

        cdd = self.cdd[t_idx] if hasattr(self, "cdd") else m.cooling_degree_days

        cal = m.lever_calibration
        cal_areatoll = cal.get("area_toll", 1.0)
        cal_carpassenger_attr = cal.get("car_passenger", 1.0)
        cal_pt_traveltime = cal.get("pt_traveltime", 1.0)
        cal_cycling_attr = cal.get("cycling", 1.0)
        cal_roadpricing = cal.get("road_pricing", 1.0)
        cal_parking = cal.get("parking", 1.0)
        cal_capacity = cal.get("capacity", 1.0)
        # capacity change with its calibration factor: (1 - PI) + PI * (1 - cal * (1 - adaptation))
        capacity_factor = (1 - self.PI_Capacity) + self.PI_Capacity * (
            1 - cal_capacity * (1 - self.capacity_adapt[t_idx])
        )

        car_pass_attr_term = (self.PI_CarPassenger * self.car_pass_attr[t_idx]
                               * cal_carpassenger_attr)
        cycling_attr_term = (self.PI_Cycling * self.cycling_attr[t_idx]
                              * cal_cycling_attr) if self.cycling_resistance is None else 0.0

        # Car congestion speed factor (Granollers-style only): csf =
        # max(0.05, 1 - car_trips_in_zone / adapted_capacity), computed
        # PER ZONE (internal/OD separately, not combined), using CAR-ONLY
        # trips (not car+car_passenger -- car_passenger trips don't add a
        # vehicle to the road). Capacity itself is time-varying via the
        # capacity-adaptation policy series (TR_NetworkCapacity * ((1-PI)
        # + PI*CapacityAdaptation[t])) -- representing e.g. road-space
        # reallocation away from cars over time, NOT a fixed constant.
        # Tallinn's translation uses constant free-flow speed
        # (network_capacity=None -> csf=1.0 for all zones).
        # without a network capacity (Tallinn branch) the capacity change acts on car speed directly
        csf_by_zone = {tt: (1.0 if m.network_capacity else max(capacity_factor, 0.05)) for tt in TRAFFIC_TYPES}
        if generic_mode and m.network_capacity and trips_now is not None:
            car_i = MODE_IDX["car"]
            adapted_capacity = m.network_capacity * capacity_factor
            for tt_name in TRAFFIC_TYPES:
                tti = TT_IDX[tt_name]
                car_trips_zone = trips_now[car_i, :, tti, :].sum()
                csf_by_zone[tt_name] = max(0.05, 1.0 - car_trips_zone / adapted_capacity)

        parking_cost_adapted = (
            parking_cost_base * (1 - self.PI_Parking)
            + parking_cost_base * self.PI_Parking * self.parking_adapt[t_idx] * cal_parking
        )
        parking_delta = parking_cost_adapted - parking_cost_base
        comp = m.parking_compliance_by_type
        if comp is not None:
            comp = np.asarray(comp)
            parking_weight = comp / float(np.dot(self.coping_dist_t[t_idx], comp))
        else:
            parking_weight = np.ones(N_CT)

        for tt_name in TRAFFIC_TYPES:
            tti = TT_IDX[tt_name]
            for tl_name in TRIP_LENGTHS:
                tli = TL_IDX[tl_name]
                centroid_dist = self.trip_length_centroid[tt_name][tl_name]
                road_pricing_adapted = self.PI_RoadPricing * self.road_pricing[t_idx] * cal_roadpricing
                area_toll_adapted = self.PI_AreaToll * self.area_toll[t_idx] * cal_areatoll * m.area_toll_affected_share

                for mode in MODES:
                    mi = MODE_IDX[mode]
                    dist = (m.trip_length_by_mode[tt_name][tl_name][mi] if m.trip_length_by_mode
                            else centroid_dist)

                    # ---- Cost ----
                    priced_km = m.road_pricing_km_scale * (min(dist, m.road_pricing_od_km)
                                 if m.road_pricing_od_km is not None and tt_name == "origin destination" else dist)
                    if mode in CAR_MODES:
                        cost = (car_cost_per_km * dist + road_pricing_adapted * priced_km
                                + parking_cost_adapted
                                + area_toll_adapted)
                    elif mode == "public transport":
                        cost = pt_cost_internal if tt_name == "internal" else pt_cost_od
                    else:  # bicycle, walk
                        cost = 0.0

                    # ---- Travel time ----
                    speed = self._average_speed(mode, tl_name, tt_name, t_idx, csf_by_zone[tt_name])
                    if m.access_time_by_mode is not None:
                        zone_idx = 0 if tt_name == "internal" else 1
                        access_time = {tt_name2: {mo: m.access_time_by_mode[mo][zone_idx] for mo in MODES}
                                        for tt_name2 in TRAFFIC_TYPES}
                    else:
                        access_time = {"internal": {"public transport": 0.15, "car": 0.1,
                                                     "car passenger": 0.2, "bicycle": 0, "walk": 0},
                                        "origin destination": {"public transport": 0.15, "car": 0.1,
                                                                "car passenger": 0.2, "bicycle": 0, "walk": 0}}
                    # strength form: (1 - PI) + PI * (1 - cal * (1 - adaptation)); cal = 1 as in the mdl
                    pt_adapt_factor = (1 if mode != "public transport" else
                                        ((1 - self.PI_PTTravelTime)
                                         + self.PI_PTTravelTime
                                         * (1 - cal_pt_traveltime * (1 - self.pt_traveltime_adapt[t_idx]))))
                    if m.travel_time_by_mode:
                        # ABM light door-to-door time; capacity acts on car modes, the PT lever on PT
                        travel_time = m.travel_time_by_mode[tt_name][tl_name][mi] * (
                            pt_adapt_factor / (csf_by_zone[tt_name] if mode in CAR_MODES else 1.0))
                        free_time = m.travel_time_by_mode[tt_name][tl_name][mi] * pt_adapt_factor
                    else:
                        travel_time = (dist / max(speed, 1e-6)
                                       + access_time[tt_name][mode] * pt_adapt_factor)
                        free_time = travel_time
                    # push-lever parts of car cost and time, weighted per coping type (D48)
                    push_by_type = m.push_levers_by_compliance and mode in CAR_MODES and not m.network_capacity
                    if push_by_type:
                        push_cost = road_pricing_adapted * priced_km + area_toll_adapted
                        push_time = (travel_time - free_time) if m.travel_time_by_mode else (
                            dist / max(speed, 1e-6) - dist / max(speed / max(csf_by_zone[tt_name], 1e-6), 1e-6))
                    # perceived-time levers of the active modes (ABM light "perceived travel time bonus")
                    if mode == "bicycle" and self.cycling_resistance is not None:
                        travel_time *= max(1 - self.PI_Cycling * cal_cycling_attr * self.cycling_resistance[t_idx], 0.05)
                    if mode in self.calming_bonus:
                        travel_time *= max(1 - self.PI_Capacity * cal.get("capacity", 1.0) * self.calming_bonus[mode][t_idx], 0.05)
                    if mode in self.fifteen_bonus and tl_name == "short":
                        travel_time *= max(1 - self.PI_DistanceAdapt * cal.get("distance", 1.0) * self.fifteen_bonus[mode][t_idx], 0.05)

                    for ci, ct_name in enumerate(COPING_TYPES):
                        if generic_mode:
                            base = base_attr_2d[mode][0 if tt_name == "internal" else 1]
                        else:
                            base = base_attr[mode]
                        attr = base + attr_distinction * attr_profile[mi, ci]

                        if generic_mode:
                            # Granollers attractiveness adjustments (compute_GC):
                            #   active modes: attr = base - CDD/100 + street_green*2 + (cycling if bike)
                            #   PT:           attr = base - CDD/200 + street_green
                            #   car/car-pass: attr = base - street_green*2 + (car_pass if car passenger)
                            # climate (CDD) acts through _heat_transfer, not through the attractiveness
                            if mode in ACTIVE_MODES:
                                attr += street_green_term * 2 + (cycling_attr_term if mode == "bicycle" else 0)
                            elif mode == "public transport":
                                attr += street_green_term
                            else:  # car, car passenger
                                attr += -street_green_term * 2 + (car_pass_attr_term if mode == "car passenger" else 0)
                        else:
                            if mode == "bicycle":
                                attr += cycling_attr_term
                            elif mode == "car passenger":
                                attr += car_pass_attr_term
                        attr += correction[mode]
                        if baseattr_correction == "use_calibrated":
                            # class-R offsets act on top of the GC-neutral correction (not absorbed by it)
                            attr += m.attr_offset.get(mode, 0.0)

                        cost_ct = cost + (parking_delta * (parking_weight[ci] - 1) if mode in CAR_MODES else 0.0)
                        time_ct = travel_time
                        if push_by_type:
                            cost_ct += push_cost * (parking_weight[ci] - 1)
                            time_ct += push_time * (parking_weight[ci] - 1)
                        gc[mi, tli, tti, ci] = (cost_ct + time_ct * value_of_time[ci] - attr)

        return gc

    def _shorter_trips(self, trips_t, t):
        """TR ShorterTrips (15-minute city): a share PI * DistanceAdaptation / 10 * Cal of
        medium trips becomes short and of long trips becomes medium, per year (annual mdl)."""
        f = self.PI_DistanceAdapt * self.distance_adapt[t] / 10 * self.m.lever_calibration.get("distance", 1.0)
        if f <= 0:
            return trips_t
        out = trips_t.copy()
        s, md, lg = TL_IDX["short"], TL_IDX["medium"], TL_IDX["long"]
        to_short = f * trips_t[:, md]
        to_medium = f * trips_t[:, lg]
        if self.m.shorter_trips_rechoose_mode:
            # moved trips take the mode split of their new class (per zone and coping type)
            def resplit(moved, target):
                share = target / np.maximum(target.sum(axis=0, keepdims=True), 1e-12)
                return moved.sum(axis=0, keepdims=True) * share
            add_short, add_medium = resplit(to_short, trips_t[:, s]), resplit(to_medium, trips_t[:, md])
            out[:, s] += add_short
            out[:, md] += add_medium - to_short
            out[:, lg] -= to_medium
            return out
        out[:, s] += to_short
        out[:, md] += to_medium - to_short
        out[:, lg] -= to_medium
        return out

    def _heat_transfer(self, trips_t, t):
        """Heat effect on active modes and PT, replacing the former attractiveness terms
        -CDD/100 (active) and -CDD/200 (PT).

        Evidence: cycling rises with temperature up to about 20-25 degC and falls only
        on hot days (Boecker et al. 2019, Transp. Res. D; Hogeweij et al. 2026, Environ.
        Res.: decline above UTCI 32 degC); on very hot days walking and transit lose trips
        to the car (Belloc et al. 2025, J. Reg. Sci.); total mobility falls by up to 10 %
        on hot days (Renninger et al. 2026, PNAS Nexus). A hot day with about 5 degree
        days above the CDD base and a 10 % loss of active trips gives 0.02 per degree
        day; PT loses half of that. The base year already contains the 2019 climate, so
        only the change of the CDD against the previous year moves trips: active and PT
        trips go to car and car passenger in proportion to their trips."""
        m = self.m
        cdd_now, cdd_prev = self.cdd[t], self.cdd[t - 1]
        if cdd_now == cdd_prev:
            return trips_t
        out = trips_t.copy()
        car = [MODE_IDX[mo] for mo in CAR_MODES]
        car_trips = out[car].sum(axis=0)
        car_weight = np.divide(out[car], car_trips, out=np.full_like(out[car], 0.5), where=car_trips > 0)
        for mo, beta in [(mo, m.heat_active_per_cdd) for mo in ACTIVE_MODES] + [("public transport", m.heat_pt_per_cdd)]:
            i = MODE_IDX[mo]
            keep = (1 - beta * cdd_now) / (1 - beta * cdd_prev)
            moved = out[i] * (1 - keep)  # negative when the CDD falls: trips return
            out[i] -= moved
            out[car] += car_weight * moved
        return np.maximum(out, 0)

    def _average_speed(self, mode, trip_length, traffic_type, t_idx, csf=1.0):
        """TR AverageSpeed. Tallinn-style: non-car modes use a FIXED speed
        per mode (constant across trip length); car modes use constant
        free-flow speed. Granollers-style (when initial_travel_speed has
        per-trip-length variation and a congestion factor is supplied):
        TR_InitialTravelSpeed[zone, trip_length, mode] * (csf if car else 1)."""
        m = self.m
        if m.base_attr_by_mode_and_zone is not None:
            # Granollers-style: full per-trip-length/zone/mode speed table,
            # with congestion scaling applied to car modes only.
            speed_table = m.initial_travel_speed[traffic_type][trip_length]
            base_speed = speed_table[MODE_IDX[mode]]
            return base_speed * (csf if mode in CAR_MODES else 1.0)

        non_car_velocity = {
            "public transport": 20.0,
            "bicycle": 12.0,
            "walk": 4.5,
        }
        if mode in non_car_velocity:
            return non_car_velocity[mode]
        free_speed = {"internal": 40, "origin destination": 60}
        return free_speed[traffic_type] * (csf if mode in CAR_MODES else 1.0)

    # ------------------------------------------------------------------
    def _summarise(self):
        """Compute distance outputs under BOTH pkm methods for comparison."""
        n = self.n_years
        out = {"years": self.years, "ev_share": self.ev_share, "microclimate": self.microclimate}

        for method in ("centroid", "mode_specific"):
            if method == "mode_specific" and self.trip_length_mode_specific is None:
                continue
            dist_cars_total = np.zeros(n)
            dist_pt_total = np.zeros(n)
            dist_active_total = np.zeros(n)
            modal_split = {mode: np.zeros(n) for mode in MODES}
            # car + passenger km of the OD zone (trips crossing the city boundary), per resident
            dist_cars_od = np.zeros(n)
            dist_pt_od = np.zeros(n)

            for t in range(n):
                total_dist = 0.0
                mode_dist = {mode: 0.0 for mode in MODES}
                for tt_name in TRAFFIC_TYPES:
                    tti = TT_IDX[tt_name]
                    for tl_name in TRIP_LENGTHS:
                        tli = TL_IDX[tl_name]
                        for mode in MODES:
                            mi = MODE_IDX[mode]
                            trips_sum = self.trips[t, mi, tli, tti, :].sum()
                            if method == "centroid" and self.m.trip_length_by_mode:
                                dist = self.m.trip_length_by_mode[tt_name][tl_name][mi]
                            elif method == "centroid":
                                dist = self.trip_length_centroid[tt_name][tl_name]
                            else:
                                dist = self.trip_length_mode_specific[tt_name][mode]
                            d = trips_sum * dist
                            mode_dist[mode] += d
                            total_dist += d
                            if tt_name == "origin destination" and mode in ("car", "car passenger"):
                                dist_cars_od[t] += d
                            elif tt_name == "origin destination" and mode == "public transport":
                                dist_pt_od[t] += d
                for mode in MODES:
                    modal_split[mode][t] = mode_dist[mode] / total_dist if total_dist > 0 else 0
                pop_internal = self.population["internal"][t]
                dist_cars_total[t] = (mode_dist["car"] + mode_dist["car passenger"]) * 365 / pop_internal
                dist_pt_total[t] = mode_dist["public transport"] * 365 / pop_internal
                dist_active_total[t] = (mode_dist["bicycle"] + mode_dist["walk"]) * 365 / pop_internal
                dist_cars_od[t] *= 365 / pop_internal
                dist_pt_od[t] *= 365 / pop_internal

            ev_frac = self.ev_share / 100
            out[method] = {
                "dist_car_fossil_km_cap_yr": dist_cars_total * (1 - ev_frac),
                "dist_car_electric_km_cap_yr": dist_cars_total * ev_frac,
                "dist_pt_km_cap_yr": dist_pt_total,
                "dist_active_km_cap_yr": dist_active_total,
                "dist_car_od_share": np.divide(dist_cars_od, dist_cars_total, out=np.zeros(n), where=dist_cars_total > 0),
                "dist_pt_od_share": np.divide(dist_pt_od, dist_pt_total, out=np.zeros(n), where=dist_pt_total > 0),
                "modal_split": modal_split,
            }
        return out


def run_mobility(city: CityConfig, pi_scenario: float = 1.0):
    model = MobilityModel(city, pi_scenario=pi_scenario)
    return model.run()


if __name__ == "__main__":
    from city_config import TALLINN
    results = run_mobility(TALLINN, pi_scenario=1.0)
    print("Years:", results["years"][[0, 11, 21, 31]])
    for method in ("centroid", "mode_specific"):
        if method not in results:
            continue
        r = results[method]
        print(f"\n--- PKM method: {method} ---")
        print("Car fossil km/cap/yr:", np.round(r["dist_car_fossil_km_cap_yr"][[0, 11, 21, 31]], 1))
        print("Car electric km/cap/yr:", np.round(r["dist_car_electric_km_cap_yr"][[0, 11, 21, 31]], 1))
        print("PT km/cap/yr:", np.round(r["dist_pt_km_cap_yr"][[0, 11, 21, 31]], 1))
        print("Active km/cap/yr:", np.round(r["dist_active_km_cap_yr"][[0, 11, 21, 31]], 1))
