"""
city_config.py

Generic CityConfig structure for the KNOWING integrated urban simulation
framework (Mobility + Energy Demand + Energy Supply, 2019-2050).

This module defines the parameters that differ between cities so that the
three submodels (mobility.py, energy_demand.py, energy_supply.py) can run
unchanged across cities -- only the CityConfig instance changes.

Two cities are defined here:
    - TALLINN   : the original reference city, Vensim-faithful baseline
    - GRANOLLERS: v8 (PLATER PV correction), Mediterranean adaptation case

Naples is intentionally NOT included yet (separate follow-up step).
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# Portable data directory: all XLSX inputs are expected alongside this file
# (or in a ./data subdirectory, checked as a fallback), the same convention
# used in granollers_model_handoff.zip so the model runs regardless of the
# working directory it's launched from.
_THIS_DIR = Path(__file__).resolve().parent


def _resolve_data_path(filename: str) -> str:
    candidates = [_THIS_DIR / filename, _THIS_DIR / "data" / filename]
    for c in candidates:
        if c.exists():
            return str(c)
    # fall back to the bare filename (lets the caller's own error surface
    # if truly missing, rather than masking it with a misleading path)
    return filename



MODES = ["car", "car passenger", "public transport", "bicycle", "walk"]
CAR_MODES = ["car", "car passenger"]
ACTIVE_MODES = ["bicycle", "walk"]
NON_CAR_MODES = ["public transport", "bicycle", "walk"]
TRIP_LENGTHS = ["short", "medium", "long"]
TRAFFIC_TYPES = ["internal", "origin destination"]
COPING_TYPES = [
    "Active Antagonists",
    "Beneficent Believers",
    "Concerned Compliers",
    "Doubting Distressed",
    "Empathic Engagers",
    "Fierce Forerunners",
]

YEARS = list(range(2019, 2051))


@dataclass
class MobilityConfig:
    """Mobility submodel (Submodel_Mobility_v10.mdl) parameters."""

    # HB Population[traffic type] -- internal, origin destination
    population_internal: float
    population_od: float

    # TR InitialTripLength[traffic type, trip length] -- centroid distances (km)
    # order: [internal_short, internal_medium, internal_long],
    #        [od_short, od_medium, od_long]
    initial_trip_length_internal: tuple  # (short, medium, long) km
    initial_trip_length_od: tuple

    # TR InitialTripRate[trip length, traffic type, mode] -- trips/person/day
    # shape: {traffic_type: {trip_length: [5 values, mode order = MODES]}}
    initial_trip_rate: dict

    # TR InitialTravelSpeed[mode, trip length, traffic type] -- km/h (empirical, used
    # ONLY for the alternative mode-specific trip-length derivation, not in the
    # original Vensim model)
    initial_travel_speed: dict

    # CopingTypesDistribution[coping type] -- must sum to 1.0, order = COPING_TYPES
    coping_type_distribution: tuple

    # CL Cooling degree days -- original Vensim default is 100. Tallinn's
    # Baltic climate is far lower (Estonia ~15-40 CDD); Granollers used 380
    # (Mediterranean, PVGIS/Catalan climate data).
    cooling_degree_days: float
    # CDD per year from MAED-City (CETS, including the full pathway); None: constant
    cooling_degree_days_trajectory: Optional[dict] = None

    # Whether to apply the Granollers-style GC-neutral BaseAttr compensation
    # for the CDD term. Only relevant if cooling_degree_days is high enough
    # to distort BAU mode choice; decided empirically per city.
    apply_cdd_baseattr_compensation: bool = False

    # Policy time series, each as {year: value} for years 2019/2030/2040/2050
    # (Vensim GET XLS Lookup style sparse keyframes; linear-interpolated)
    policy_car_costs_fuel: dict = field(default_factory=dict)
    policy_car_costs_ev: dict = field(default_factory=dict)
    policy_capacity_adaptation: dict = field(default_factory=dict)
    policy_parking_cost_adaptation: dict = field(default_factory=dict)
    policy_area_toll: dict = field(default_factory=dict)
    policy_road_pricing: dict = field(default_factory=dict)
    policy_cycling_attractiveness: dict = field(default_factory=dict)
    policy_pt_traveltime_adaptation: dict = field(default_factory=dict)
    policy_distance_adaptation: dict = field(default_factory=dict)
    policy_car_passenger_attractiveness: dict = field(default_factory=dict)
    policy_ev_adoption_adaptation: dict = field(default_factory=dict)

    # Population net increase per traffic type (Vensim HB PopNetIncrease),
    # {year: value}. Tallinn's original .mdl had nonzero growth; Granollers
    # used zero growth for both zones by explicit decision.
    pop_net_increase_internal: dict = field(default_factory=dict)
    pop_net_increase_od: dict = field(default_factory=dict)

    # Whether area toll / PI is applicable at all (Granollers: excluded,
    # city too small for cordon infrastructure)
    area_toll_applicable: bool = True

    # EV adoption ceiling trajectory override {year: percent}, PI=1 scenario
    ev_pi_trajectory: Optional[dict] = None

    # If set, BAU follows a damped version of the PI=1 EV curve from this
    # pivot year onward (see mobility.py run() docstring). None = same EV
    # curve applies regardless of scenario (Granollers' original script
    # only documents a single PI=1 EV trajectory, no separate BAU case).
    ev_bau_damping_pivot_year: Optional[int] = None

    # Mode-specific empirical trip length override (the "v8 fix"),
    # {traffic_type: {mode: km}}. None = not available / not used.
    mode_specific_trip_length: Optional[dict] = None

    # ------------------------------------------------------------------
    # Generalised-cost formula parameters (added for Granollers migration
    # -- these were previously hardcoded inside mobility.py's
    # _generalised_cost, fine for a single city but not generic across
    # cities whose real GC formulas differ structurally, not just in
    # constants).
    # ------------------------------------------------------------------

    # TR_BaseAttr[mode, traffic_type] -- base attractiveness, genuinely
    # 2D (differs by internal vs. origin-destination zone). Order of modes
    # matches MODES; order of traffic types matches TRAFFIC_TYPES.
    # None = use the simple flat-per-mode Tallinn-style default inside
    # mobility.py (kept for backward compatibility with the Tallinn run).
    base_attr_by_mode_and_zone: Optional[dict] = None  # {mode: (internal_val, od_val)}

    # TR_AttrDistinction -- scalar multiplier on the coping-type
    # attractiveness profile (Granollers: 0.22142; Tallinn's original
    # translation used an implicit 1.0).
    attr_distinction: float = 1.0

    # Value-of-time: VoT_base + VoT_dist * profile[coping_type].
    # Tallinn's original translation effectively used base=15, dist=1.0
    # with a different profile shape; Granollers uses base=5.09502,
    # dist=0.1. Both are now explicit, city-specific parameters.
    value_of_time_base: float = 15.0
    value_of_time_dist: float = 1.0
    value_of_time_profile: tuple = (3.0, -2.0, 2.0, -3.0, -1.0, 1.0)

    # Street-green policy lever (Granollers-specific; Tallinn's .mdl has
    # no equivalent -- defaults to 0/inactive for cities that don't use it)
    policy_street_green: dict = field(default_factory=dict)

    # Network capacity (trips/day) used for the car congestion speed-factor
    # csf = max(0.05, 1 - total_car_trips/capacity). None = no congestion
    # speed penalty applied (Tallinn's original translation used constant
    # free-flow speed; Granollers uses TR_NetworkCapacity=440,000).
    network_capacity: Optional[float] = None

    # Per-zone PT cost override (Granollers: TR_Cost_PT = [0.0, 0.72] for
    # [internal, origin destination]). None = use the Tallinn-style
    # internal=0/OD=0.72 default already in mobility.py.
    pt_cost_by_zone: Optional[tuple] = None

    # Car cost per km (fuel/EV), as flat constants rather than a lookup
    # series, for cities (like Granollers) whose .mdl encodes these as
    # fixed scalars rather than a time-varying policy series. None = use
    # the policy_car_costs_fuel/ev time series instead.
    car_cost_per_km_fuel_constant: Optional[float] = None
    car_cost_per_km_ev_constant: Optional[float] = None

    # Parking cost baseline (EUR/trip). Tallinn's .mdl value is 1.5;
    # Granollers' is 0.18 -- different enough to need to be configurable
    # rather than hardcoded.
    parking_cost_base: float = 1.5

    # Access time by mode, in hours (TR_AccessTime[zone, mode] in
    # Granollers' script: car=0.15, car_passenger=0.10, PT=0.20, bike/walk=0
    # -- note this is DIFFERENT from the flat Tallinn-style default
    # hardcoded in mobility.py, which must not be silently reused for
    # other cities). {mode: (internal_val, od_val)}. None = use the
    # Tallinn-style flat default already in mobility.py.
    access_time_by_mode: Optional[dict] = None

    # Multiplier on TR_ModeChangeElasticity (see mobility.py run()
    # docstring for full justification). Calibrated per city against
    # known reference checkpoints since the raw elasticity makes PI=1
    # mode-share dynamics collapse too aggressively when every policy
    # lever applies at full simultaneous strength.
    mode_change_damping: float = 1.0
    # class-R calibration offsets on the attractiveness per mode, fitted to the ABM light
    # reference and optimised trajectories (regsim: sd_knowing.recalibrate_class_r)
    attr_offset: dict = field(default_factory=dict)


@dataclass
class EnergyDemandConfig:
    """Energy demand submodel (MAED-City XLSX lookup) parameters."""

    xlsx_path: str
    sheet_name: str = "CETS"
    # whether household space heating is broken out by Biomass/Solar/DH/
    # electric/fossil (Tallinn CETS layout) vs. an aggregate format
    detailed_heating_breakdown: bool = True


@dataclass
class EnergySupplyConfig:
    """Energy supply submodel (Submodel_EnergySupply_v4.mdl) parameters."""

    xlsx_path: Optional[str] = None
    has_district_heating: bool = True
    # Grid emission factor trajectory, kg CO2/kWh, {year: value}
    grid_emission_factor: dict = field(default_factory=dict)
    # PLATER-style planning-grounded PV target by 2050 (MWp), None = not applicable
    plater_pv_target_2050: Optional[float] = None

    # For cities without a real multi-technology capacity XLSX (e.g.
    # Granollers, whose supply side is a handful of scalar interpolations
    # rather than Tallinn's ES_inputs.xlsx table): a function that returns
    # the SAME {category: {item: (val_2019, val_2050)}} structure
    # _read_supply_xlsx() would produce from a real file. When set,
    # xlsx_path is ignored and this is used instead, so run_energy_supply()
    # itself needs no per-city branching.
    synthetic_supply_data: Optional[object] = None  # Callable[[], dict]

    # Whether local fossil-fuelled power generation force-phases-out after
    # 10 years (Tallinn's .mdl behaviour: "Assumption: Preference over
    # importing; but anyway zero after 10y" -- appropriate for peaker
    # plants filling a temporary gap). Granollers' Gas CHP is a real,
    # ongoing combined-heat-and-power plant that runs throughout 2019-2050
    # (declining capacity 15->2 MW, never force-zeroed) -- so this is a
    # per-city, explicit choice rather than a hardcoded assumption.
    # Whether local fossil generation dispatches as a FIXED schedule
    # (Granollers' Gas CHP: PP_CHP = IC_GasCHP*2.0, runs at its own
    # capacity-determined output regardless of demand, with grid import
    # absorbing any mismatch) vs. DEMAND-FILLING (Tallinn's peakers: fills
    # the residual gap between demand and other local sources, capped by
    # installed capacity). This is a genuine dispatch-logic difference,
    # not just a parameter -- per-city, explicit.
    fossil_power_dispatch_mode: str = "demand_filling"  # or "fixed_schedule"

    fossil_power_phases_out_after_10y: bool = True

    # Local fossil power emission factor, kg CO2/kWh. Tallinn's .mdl uses
    # a blended 0.55 (oil/gas/peat/biogas mix); Granollers' script uses
    # 0.45 kt/GWh specifically for its single Gas CHP technology (the
    # units are equivalent: 0.45 kt/GWh = 0.45 kg/kWh).
    fossil_power_emission_factor: float = 0.55


@dataclass
class TransportEnergyConfig:
    """Conversion of passenger-km to final energy (energy_demand.py). The mobility
    submodel reports car + car-passenger kilometres; vehicle-km = pkm / load_factor."""
    car_fossil_kwh_per_vkm: float
    car_electric_kwh_per_vkm: float
    load_factor: float
    pt_internal_kwh_per_pkm: float = 0.040
    pt_od_kwh_per_pkm: float = 0.050
    # share of trips crossing the city boundary counted in the city's energy balance
    # (GPC induced-activity method: 0.5; 1.0 counts all OD traffic)
    od_energy_share: float = 1.0


@dataclass
class MicroclimateConfig:
    """Microclimate submodel (Submodel_MicroClimate_v4.mdl), see microclimate.py."""
    calibration_csv: Optional[str] = None  # PALM-4U class table; None: CDD from MAED-City only
    beta: Optional[float] = None  # relative CDD change per K; None: cross-calibrated (Tallinn)


@dataclass
class CityConfig:
    name: str
    country: str
    mobility: MobilityConfig
    energy_demand: EnergyDemandConfig
    energy_supply: EnergySupplyConfig
    transport_energy: Optional[TransportEnergyConfig] = None  # None: Tallinn factors per pkm (legacy)
    microclimate: Optional[MicroclimateConfig] = None


# ---------------------------------------------------------------------------
# TALLINN -- reference city, original Vensim calibration
# ---------------------------------------------------------------------------

# mob_inputs.csv layout (mode order: car, car passenger, public transport,
# bicycle, walk), rows = short/medium/long
_tallinn_trip_rate_internal = {
    "short":  [0.053803841, 0.010031393, 0.045166865, 0.0081743,    0.444160633],
    "medium": [0.411726934, 0.098982613, 0.337763626, 0.010761575,  0.078466005],
    "long":   [0.205819091, 0.042649515, 0.173491533, 0.000901984,  5.28652e-08],
}
_tallinn_trip_rate_od = {
    "short":  [0.001382669, 0.000267208, 0.001649848, 0.000210527,  0.008027336],
    "medium": [0.167456967, 0.036955099, 0.265295936, 0.001888521,  0.010288415],
    "long":   [1.505354624, 0.295876048, 1.40113854,  0.003374393,  6.39979e-06],
}
_tallinn_speed_internal = {
    "short":  [4.827300479, 4.996112655, 4.637179798, 12.37711409,  4.630704888],
    "medium": [13.56955874, 13.43467681, 10.1452391,  11.6817183,   4.378480368],
    "long":   [20.42536667, 20.46145732, 14.18191382, 11.54904423,  4.130219327],
}
_tallinn_speed_od = {
    "short":  [6.768238522, 6.76171463,  3.750591121, 14.12822434,  5.415632737],
    "medium": [17.3686944,  17.24267216, 6.448048122, 12.48419053,  4.884849543],
    "long":   [29.15371155, 29.0770918,  18.14241815, 11.70668359,  4.227508913],
}

TALLINN = CityConfig(
    name="Tallinn",
    country="Estonia",
    mobility=MobilityConfig(
        population_internal=436772,
        population_od=113320,
        initial_trip_length_internal=(0.993799957, 5.719549309, 13.70258984),
        initial_trip_length_od=(1.649944013, 6.786485894, 26.39949463),
        initial_trip_rate={"internal": _tallinn_trip_rate_internal, "origin destination": _tallinn_trip_rate_od},
        initial_travel_speed={"internal": _tallinn_speed_internal, "origin destination": _tallinn_speed_od},
        # D3.3 Table 28 / Fig. 73, metropolitan Estonia (KNOWING survey 2023); was national Estonia (D1.3)
        coping_type_distribution=(0.09, 0.17, 0.32, 0.13, 0.13, 0.17),
        cooling_degree_days=8.6,  # MAED-City base year (D3.3 Table 7); was 100 (Vensim default)
        cooling_degree_days_trajectory={2019: 8.6, 2050: 15.0},  # CETS 2050 (D3.3 Table 7)
        apply_cdd_baseattr_compensation=True,  # verified: produces stable near-2019-equilibrium behavior (65.7%->66.3%->65.0% oscillation) vs. monotonic drift when off (65.7%->67.9%); see mobility.py _compute_baseattr_calibration
        policy_car_costs_fuel={2019: 0.17, 2030: 0.185, 2040: 0.195, 2050: 0.2},
        policy_car_costs_ev={2019: 0.2, 2030: 0.15, 2040: 0.13, 2050: 0.12},
        policy_capacity_adaptation={2019: 1, 2030: 0.95, 2040: 0.85, 2050: 0.75},
        policy_parking_cost_adaptation={2019: 1, 2030: 1.1, 2040: 1.2, 2050: 1.3},
        policy_area_toll={2019: 0, 2030: 10, 2040: 15, 2050: 20},
        policy_road_pricing={2019: 0, 2030: 0.1, 2040: 0.3, 2050: 0.5},
        policy_cycling_attractiveness={2019: 0, 2030: 0.5, 2040: 1.5, 2050: 2.5},
        policy_pt_traveltime_adaptation={2019: 1, 2030: 0.95, 2040: 0.85, 2050: 0.75},
        policy_distance_adaptation={2019: 0, 2030: 0.05, 2040: 0.05, 2050: 0.05},
        policy_car_passenger_attractiveness={2019: 0, 2030: 0.5, 2040: 1.5, 2050: 2.5},
        policy_ev_adoption_adaptation={2019: 1, 2030: 1.2, 2040: 1.2, 2050: 1.2},
        pop_net_increase_internal={2009: 0, 2019: 182, 2030: 243.3, 2040: 259.5},
        pop_net_increase_od={2009: 0, 2019: 0, 2030: 0, 2040: 0},
        area_toll_applicable=True,
        ev_pi_trajectory=None,  # uses native TR EVChangeRate dynamics
        ev_bau_damping_pivot_year=2026,  # last shared historical anchor; BAU damps to ~half PI=1 by 2050
        # class R, fitted to the ABM light reference and optimised pkm shares 2030/2040/2050
        # (regsim sd_knowing.recalibrate_class_r, decision D32; loss 0.0118)
        mode_change_damping=0.0988,
        attr_offset={"car passenger": -1.865, "public transport": 5.525, "bicycle": 0.495, "walk": -3.192},
        mode_specific_trip_length=None,  # derived empirically in mobility.py for comparison
    ),
    energy_demand=EnergyDemandConfig(
        xlsx_path=_resolve_data_path("EN_MEADCityInput.xlsx"),
        sheet_name="CETS",
        detailed_heating_breakdown=True,
    ),
    energy_supply=EnergySupplyConfig(
        xlsx_path=_resolve_data_path("Supply_Data_Tallinn.xlsx"),
        has_district_heating=True,
        # Evidence-based trajectory (kg CO2/kWh), anchored to actual reported
        # values rather than an EU-average assumption:
        #   2019: ~0.78 (oil-shale-dominated, validated against earlier
        #         Estonian Competition Authority / Elering cross-check)
        #   2024: ~0.42 (Ember/Nowtricity reported actual, 52% renewable share)
        #   2030: ~0.20 (continued wind/solar buildout per NECP, before oil
        #         shale phase-out begins)
        #   2050: ~0.02 (Estonia NECP 2025 targets -95% GHG vs. 1990 by 2050;
        #         oil shale phase-out starts 2040 per SEI/Balmorel modelling)
        # NOTE: these are still desk-research anchors, not a primary national
        # projection (e.g. Elering's own long-term scenario). Flagging for
        # Martin to confirm/replace with an official Estonian source if one
        # exists, the same way the Spanish REE/PNIEC/PROENCAT path was used
        # for Granollers.
        #
        # EXPLICIT DECISION: the original Submodel_EnergySupply_v4.mdl
        # contains its own simplified built-in assumption for Estonia
        # ("Average for Estonia: 0.4, going linear towards zero until
        # 2050" -- ES ImportedElectricityMixFactor = 0.4 - 0.4/31*(Time-
        # 2019)). This evidence-based trajectory (0.78->0.02) REPLACES
        # that simplified in-model assumption, the same way Granollers
        # replaced the Vensim model's generic EU-average default with a
        # Spain-specific REE/PNIEC/PROENCAT path.
        grid_emission_factor={2019: 0.78, 2024: 0.42, 2030: 0.20, 2050: 0.02},
        plater_pv_target_2050=None,
    ),
    microclimate=MicroclimateConfig(calibration_csv=_resolve_data_path("mc4_cal_tallinn.csv")),
    # Estonian fleet 0.749 kWh/vkm (energy_demand.TallinnConversionFactors); load factor 1.23 (D3.3 MAED-City key measures)
    transport_energy=TransportEnergyConfig(car_fossil_kwh_per_vkm=0.749, car_electric_kwh_per_vkm=0.222, load_factor=1.23, od_energy_share=0.5),
)


# ---------------------------------------------------------------------------
# GRANOLLERS -- v8 (PLATER PV correction), migrated from the standalone
# granollers_integrated_model.py script into this generic CityConfig
# structure. All values below are transcribed VERBATIM from that script's
# hardcoded NumPy arrays/scalars (mobility) and from EN_MEADCityInput_
# 0527_v6.xlsx (energy demand) -- not re-derived or approximated.
#
# Mode order in the original script: car, car passenger, public transport,
# bicycle, walk (NM=5) -- matches MODES exactly.
# Zone order: internal, origin destination (NZ=2) -- matches TRAFFIC_TYPES.
# Coping-type order matches COPING_TYPES.
# ---------------------------------------------------------------------------

# TR_InitialTripRate[zone, trip_length, mode] -- trips/person/day
_granollers_trip_rate_internal = {
    "short":  [0.045505, 0.010921, 0.018202, 0.036404, 1.392465],
    "medium": [0.227527, 0.047326, 0.050056, 0.050056, 0.139246],
    "long":   [0.182022, 0.032764, 0.022753, 0.004551, 0.015472],
}
_granollers_trip_rate_od = {
    "short":  [0.006127, 0.000943, 0.007777, 0.007070, 0.150830],
    "medium": [0.300245, 0.046192, 0.147766, 0.015319, 0.035822],
    "long":   [0.306372, 0.047134, 0.103695, 0.001178, 0.001885],
}
# TR_InitialTravelSpeed[zone, trip_length, mode] -- km/h
_granollers_speed_internal = {
    "short":  [8.0, 8.0, 3.5, 12.0, 4.5],
    "medium": [18.0, 18.0, 8.0, 11.5, 4.3],
    "long":   [28.0, 28.0, 12.0, 11.0, 4.1],
}
_granollers_speed_od = {
    "short":  [10.0, 10.0, 5.0, 13.0, 5.0],
    "medium": [30.0, 30.0, 15.0, 12.0, 4.8],
    "long":   [55.0, 55.0, 40.0, 11.5, 4.2],
}

GRANOLLERS = CityConfig(
    name="Granollers",
    country="Spain (Catalonia)",
    mobility=MobilityConfig(
        population_internal=60108,   # XLSX row 35, 2019 anchor (HBP[0])
        population_od=45000,         # HBP[1] -- script hardcoded, not from row 35
        initial_trip_length_internal=(0.90, 3.50, 10.00),
        initial_trip_length_od=(1.20, 6.00, 20.00),
        initial_trip_rate={"internal": _granollers_trip_rate_internal, "origin destination": _granollers_trip_rate_od},
        initial_travel_speed={"internal": _granollers_speed_internal, "origin destination": _granollers_speed_od},
        # D3.4b section 5.3.3, urban Spain (KNOWING survey 2023); was national Spain (D1.3)
        coping_type_distribution=(0.03, 0.09, 0.09, 0.37, 0.33, 0.10),
        cooling_degree_days=380,  # Mediterranean climate (PVGIS/Catalan climate data)
        apply_cdd_baseattr_compensation=False,  # Granollers' own TR_BaseAttr is already hand-tuned; this correction is NOT needed (and was found to double-correct PT's GC by +2.49 when mistakenly left on)
        # Mode-specific empirical trip lengths (the v8 "PKM fix") --
        # TR_TripLength[zone, mode], km. This is the PRIMARY method for
        # Granollers (unlike Tallinn, no centroid/mode-specific ambiguity
        # was left open -- this was already the resolved v8 approach).
        mode_specific_trip_length={
            "internal": {"car": 3.8, "car passenger": 3.5, "public transport": 2.8, "bicycle": 2.0, "walk": 0.9},
            "origin destination": {"car": 18.0, "car passenger": 18.0, "public transport": 18.0, "bicycle": 5.0, "walk": 1.5},
        },
        # Policy time series. NOTE: the original script's PI=1 run applies
        # every lever via a SHARED ramp curve RP=[2019:0, 2030:.5, 2040:.75,
        # 2050:1] multiplying each policy's own adaptation series below --
        # captured here as PI_dict-equivalent policy series already at
        # PI=1 strength (PI multiplier itself is handled in mobility.py via
        # self.pi, consistent with the Tallinn translation).
        policy_car_costs_fuel={},  # not a time series for Granollers -- see car_cost_per_km_fuel_constant
        policy_car_costs_ev={},
        policy_capacity_adaptation={2009: 1, 2019: 1, 2030: 0.95, 2040: 0.85, 2050: 0.85},  # CAS
        policy_parking_cost_adaptation={2009: 1, 2019: 1, 2030: 1.1, 2040: 1.2, 2050: 1.2},  # PAS
        policy_area_toll={},  # ARS = np.zeros(NT) -- area toll not applicable (city too small)
        policy_road_pricing={2009: 0, 2019: 0, 2030: 0.10, 2040: 0.30, 2050: 0.30},  # RPS
        policy_cycling_attractiveness={2009: 0, 2019: 0, 2030: 0.5, 2040: 1.5, 2050: 1.5},  # CYS
        policy_pt_traveltime_adaptation={2009: 1, 2019: 1, 2030: 0.95, 2040: 0.85, 2050: 0.85},  # PTS
        policy_distance_adaptation={},
        policy_car_passenger_attractiveness={2009: 0, 2019: 0, 2030: 0.5, 2040: 1.5, 2050: 1.5},  # CPS
        policy_ev_adoption_adaptation={},  # EV trajectory handled separately (ev_pi_trajectory below)
        policy_street_green={2019: 0.0, 2030: 0.5, 2040: 0.75, 2050: 1.0},  # = RP itself when active
        pop_net_increase_internal={},  # Granollers uses a growing-population RATE (POP_GROWTH_ARR
        pop_net_increase_od={},        # derived from XLSX row 35), not a net-increase series --
                                        # see note below; population growth is handled via the
                                        # shared POP_GROWING interpolation, not this field, for Granollers.
        area_toll_applicable=False,    # city too small, no cordon infrastructure
        ev_pi_trajectory={2019: 0.2, 2022: 1.5, 2025: 7.0, 2028: 14.0, 2030: 20.0, 2040: 55.0, 2050: 80.0},  # EV_PI, percent
        # --- Generalised-cost formula parameters (Granollers-specific) ---
        base_attr_by_mode_and_zone={
            "car": (2.0399, 3.2007),
            "car passenger": (1.7911, 2.9519),
            "public transport": (2.6624, 3.7156),
            "bicycle": (4.4269, 7.4929),
            "walk": (5.8769, 14.0183),
        },
        attr_distinction=0.22142,
        value_of_time_base=5.09502,
        value_of_time_dist=0.1,
        value_of_time_profile=(3.0, -2.0, 2.0, -3.0, -1.0, 1.0),
        network_capacity=440000.0,
        pt_cost_by_zone=(0.0, 0.72),
        car_cost_per_km_fuel_constant=0.10,
        car_cost_per_km_ev_constant=0.04,
        parking_cost_base=0.18,
        access_time_by_mode={
            "car": (0.15, 0.15),
            "car passenger": (0.10, 0.10),
            "public transport": (0.20, 0.20),
            "bicycle": (0.0, 0.0),
            "walk": (0.0, 0.0),
        },
        mode_change_damping=0.84,  # calibrated against REF_MOB checkpoints from granollers_integrated_model.py
    ),
    energy_demand=EnergyDemandConfig(
        xlsx_path=_resolve_data_path("EN_MEADCityInput_0527_v6.xlsx"),
        sheet_name="CETS",
        detailed_heating_breakdown=True,
    ),
    energy_supply=EnergySupplyConfig(
        xlsx_path=None,  # no multi-technology capacity XLSX -- synthetic data used instead
        has_district_heating=False,  # no DH network at all (em_dh = 0 always)
        # Spain PNIEC trajectory: 0.190 (2019 actual) -> 0.060 (2030,
        # PNIEC milestone) -> 0.005 (2050, near-zero residual for gas
        # peakers/balancing). Replaces the .mdl's generic EU-average
        # default, the same way Tallinn's evidence-based path replaced
        # the .mdl's simplified Estonia assumption.
        grid_emission_factor={2019: 0.190, 2030: 0.060, 2050: 0.005},
        # PLATER (Catalonia territorial renewable energy plan, pending
        # approval ~2027): 79.9 MWp by 2050 (7.7 non-urbanised land +
        # 4.4 infrastructure + 67.8 buildings). Supersedes the earlier
        # 250 MWp "ambitious technical potential" assumption.
        plater_pv_target_2050=79.9,
        fossil_power_dispatch_mode="fixed_schedule",
        fossil_power_phases_out_after_10y=False,  # not used in fixed_schedule mode, kept False for clarity
        fossil_power_emission_factor=0.45,  # kt CO2/GWh = kg/kWh, Gas-CHP-specific (vs Tallinn's blended 0.55)
        synthetic_supply_data=lambda: {
            "ES ElectricityCapacity": {
                "PV": (2.0, 79.9),
                "Natural Gas CHP el": (15.0, 2.0),
            },
            "ES ElectrictitySupply": {
                # PV: capacity x PV_YIELD(1.5) -- supply_2019/capacity_2019 ratio = 1.5,
                # reproduced here via matching 2019 numbers so the existing
                # capacity_scaled() logic in energy_supply.py yields the
                # same productivity ratio.
                "PV": (2.0 * 1.5, 79.9 * 1.5),
                # Gas CHP: PP_CHP = IC_GasCHP * 2.0 -- same trick, ratio = 2.0
                "Natural Gas CHP el": (15.0 * 2.0, 2.0 * 2.0),
            },
            "ES HeatCapacity": {},  # no DH network
            "ES HeatSupply": {},
        },
    ),
)


# ---------------------------------------------------------------------------
# NAPLES -- Mediterranean large-city case, populated from public sources.
#
# DATA SOURCES (per field):
#   Population     : ISTAT 2019 permanent census (comune.napoli.it / istat.it)
#   Mode shares    : ISFORT Audimob 2019 national report + Naples-context
#                    adjustment (Naples PUMS PDFs not machine-readable;
#                    car share lowered vs. national 62.5% due to Naples'
#                    dense urban fabric and metro/funicular network;
#                    PT raised accordingly). FLAG for replacement once the
#                    Comune di Napoli PUMS 2021 technical annex is accessible.
#   Trip rates     : Derived from ISFORT 2019 (1.76 trips/cap/day Italy
#                    national) distributed across modes using estimated
#                    mode shares, then split by zone/length following the
#                    same structural logic as Granollers.
#   Travel speeds  : Naples-specific estimates; car speeds reflect severe
#                    urban congestion (TomTom Traffic Index 2019: Naples
#                    ranked among Italy's most congested cities, ~50-55%
#                    congestion level); PT speeds reflect mixed bus/metro
#                    network.
#   EV trajectory  : EAFO 2019 fleet share (0.3% BEV); 2030 PNIEC 2023
#                    Policy Driven scenario (6.6M BEV+PHEV / ~40M fleet =
#                    16.5%); 2050 extrapolated to 85% (EU full-fleet target
#                    trajectory, consistent with Italian PNIEC decarbonisation
#                    goal). BAU uses same damping structure as Tallinn
#                    (pivot 2026).
#   Grid EF        : Nowtricity/Terna 2019 actual (0.362 kg/kWh); PNIEC 2023
#                    2030 milestone (~0.150 kg/kWh, 65% renewable target);
#                    2050 near-zero (0.010 kg/kWh, full decarbonisation).
#   PV capacity    : GSE 2019 report: Campania total 751 MWp. Naples city
#                    share estimated by population ratio (905k / 5.7M ×
#                    751) ≈ 119 MWp, corrected downward (~40%) for urban
#                    density vs. rural Campania → 70 MWp 2019 baseline.
#                    2050 target: Campania 2030 target 873 MWp (Clean
#                    Cities / ScienceDirect 2050 study), Naples urban share
#                    ~130 MWp.
#   Coping types   : PLACEHOLDER -- must be replaced with KNOWING Naples
#                    survey data. Using Mediterranean profile similar to
#                    Granollers as best available proxy.
#   Energy demand  : PLACEHOLDER xlsx_path -- a Naples-specific MAED-City
#                    XLSX does not yet exist. Energy demand submodel cannot
#                    run until this file is provided by KNOWING partners.
#   Policy levers  : Adapted from Naples PUMS 2021 strategy documents
#                    (Clean Cities summary + ambientenonsolo.com coverage):
#                    ZTL expansion (area toll: YES, city already has ZTL),
#                    PT travel-time targets (-25% by 2030), cycling
#                    infrastructure programme (12 new routes planned),
#                    parking cost increases. Magnitudes calibrated to be
#                    consistent with Granollers / Tallinn PI=1 ranges.
# ---------------------------------------------------------------------------

_naples_trip_rate_internal = {
    "short":  [0.18054, 0.06195, 0.19247, 0.05737, 0.24278],
    "medium":  [0.44669, 0.14694, 0.43439, 0.06521, 0.03703],
    "long":  [0.35839, 0.10332, 0.26327, 0.00695, 1e-05],
}
_naples_trip_rate_od = {
    "short":  [0.18054, 0.06195, 0.19247, 0.05737, 0.24278],
    "medium":  [0.44669, 0.14694, 0.43439, 0.06521, 0.03703],
    "long":  [0.35839, 0.10332, 0.26327, 0.00695, 1e-05],
}

# TR_InitialTravelSpeed[zone, trip_length, mode] -- km/h
# Naples urban speeds: severe congestion (TomTom 2019: ~50-55% congestion)
_naples_speed_internal = {
    "short":  [10.0, 10.0,  8.0, 12.0, 4.5],
    "medium": [14.0, 14.0, 12.0, 11.5, 4.3],
    "long":   [18.0, 18.0, 16.0, 10.5, 4.1],
}
_naples_speed_od = {
    "short":  [14.0, 14.0, 12.0, 13.0, 4.5],
    "medium": [25.0, 25.0, 18.0, 12.0, 4.3],
    "long":   [45.0, 45.0, 35.0, 11.0, 4.2],
}

NAPLES = CityConfig(
    name="Naples",
    country="Italy (Campania)",
    mobility=MobilityConfig(
        # ISTAT 2019 permanent census: Naples comune ~905,000; metropolitan
        # commuter inflow estimated at ~250,000 (hinterland to city-proper flows
        # not yet available from ISTAT OD microdata -- FLAG for update).
        population_internal=954_318,  # D3.4a Table A-15 (MAED-City); was 905,000 (ISTAT)
        population_od=250_000,
        # Centroid distances: Naples is denser than Granollers; shorter trip
        # lengths consistent with compact Mediterranean city fabric.
        # class centroids and trip rates from ABM light base year (D3.4a Fig. A-87/A-88; estimate_trip_classes.py)
        initial_trip_length_internal=(1.3, 7.93, 28.65),
        initial_trip_length_od=(1.3, 7.93, 28.65),
        initial_trip_rate={
            "internal": _naples_trip_rate_internal,
            "origin destination": _naples_trip_rate_od,
        },
        initial_travel_speed={
            "internal": _naples_speed_internal,
            "origin destination": _naples_speed_od,
        },
        # Mode-specific empirical trip lengths (estimated; FLAG for replacement
        # with survey-derived values from KNOWING data or PUMS technical annex).
        mode_specific_trip_length={
            "internal": {
                "car": 4.2, "car passenger": 4.0,
                "public transport": 3.5, "bicycle": 2.2, "walk": 0.8,
            },
            "origin destination": {
                "car": 16.0, "car passenger": 16.0,
                "public transport": 15.0, "bicycle": 4.5, "walk": 1.2,
            },
        },
        # D3.4a Fig. A-94, metropolitan Italy (KNOWING survey 2023). Table A-29
        # of D3.4a lists the same values in reverse order of types.
        coping_type_distribution=(0.01, 0.06, 0.14, 0.29, 0.37, 0.14),
        # Naples: Mediterranean climate, ~120 CDD (higher than Tallinn,
        # lower than Granollers' 380; PVGIS data for Campania).
        cooling_degree_days=326,  # MAED-City base year (D3.4a heat-wave table); was 120 (PVGIS estimate)
        cooling_degree_days_trajectory={2019: 326.0, 2050: 610.0},  # CETS 2050
        apply_cdd_baseattr_compensation=False,  # BaseAttr hand-tuned below; same logic as Granollers
        # Base attractiveness by mode and zone: calibrated so 2019 logit
        # equilibrium reproduces estimated Naples mode split (car ~50%,
        # PT ~25%, walk ~22%, bicycle ~2%, car_pass ~15% rough target).
        # Values are provisional estimates; recalibrate once real mode-share
        # data from PUMS or KNOWING survey is available.
        base_attr_by_mode_and_zone={
            "car":              (2.10, 3.30),
            "car passenger":    (1.80, 3.00),
            "public transport": (2.90, 3.90),   # higher than Granollers: metro/funicular network
            "bicycle":          (3.80, 6.50),   # lower than Granollers: hillier terrain, less cycle culture
            "walk":             (5.50, 12.00),
        },
        # Generalised-cost formula: Southern Italian city, similar VoT to
        # Granollers; attr_distinction estimated, needs KNOWING survey data.
        attr_distinction=0.22,
        value_of_time_base=5.5,    # EUR/h; slightly above Granollers (higher Naples income level)
        value_of_time_dist=0.1,
        value_of_time_profile=(3.0, -2.0, 2.0, -3.0, -1.0, 1.0),
        # Naples road network: estimated ~3.5M car trips/day capacity
        # (vs. Granollers 440k for 105k pop; Naples is ~15x larger).
        network_capacity=3_500_000.0,
        pt_cost_by_zone=(0.0, 1.10),  # Naples ANM/EAV flat fare ~1.10 EUR (2019)
        car_cost_per_km_fuel_constant=0.12,   # Italy avg fuel cost/km 2019 (ACI data)
        car_cost_per_km_ev_constant=0.05,
        parking_cost_base=1.0,   # EUR/trip; Naples urban parking ~0.5-2 EUR/h
        access_time_by_mode={
            "car":              (0.15, 0.15),
            "car passenger":    (0.10, 0.10),
            "public transport": (0.25, 0.25),   # longer PT access: infrequent buses, station distance
            "bicycle":          (0.0,  0.0),
            "walk":             (0.0,  0.0),
        },
        # Policy levers (PI=1 strength), based on Naples PUMS 2021 strategy:
        policy_car_costs_fuel={},   # constant (car_cost_per_km_fuel_constant used instead)
        policy_car_costs_ev={},
        # Policy paths from D3.4a Table A-27 (ABM light optimised scenario), mapped
        # like Tallinn's Table 1 (D3.3): capacity -5/-15/-25 %, parking +10/+20/+30 %,
        # central zone charge 10/15/20 EUR/entry, road pricing 0.10/0.30/0.50 EUR/km (city).
        policy_capacity_adaptation={2019: 1, 2030: 0.95, 2040: 0.85, 2050: 0.75},
        policy_parking_cost_adaptation={2019: 1, 2030: 1.1, 2040: 1.2, 2050: 1.3},
        policy_area_toll={2019: 0, 2030: 10, 2040: 15, 2050: 20},
        policy_road_pricing={2019: 0, 2030: 0.10, 2040: 0.30, 2050: 0.50},
        policy_cycling_attractiveness={2019: 0, 2030: 0.4, 2040: 1.2, 2050: 2.0},  # 12 new routes PUMS target
        # PT: Table A-27 gives -15 % (2040) and -25 % (2050); 2030 is "metro extensions",
        # not quantified, so the previous 0.90 is kept. Cycling (citywide -5/-15/-25 %,
        # no core-network measure as in Tallinn) keeps its previous series.
        policy_pt_traveltime_adaptation={2019: 1, 2030: 0.90, 2040: 0.85, 2050: 0.75},
        policy_distance_adaptation={2019: 0, 2030: 0.05, 2040: 0.05, 2050: 0.05},  # 15-minute city as Tallinn
        policy_car_passenger_attractiveness={2019: 0, 2030: 0.5, 2040: 1.5, 2050: 2.5},  # car occupancy -5/-15/-25 %
        policy_ev_adoption_adaptation={},
        policy_street_green={},     # not a Naples PUMS lever
        pop_net_increase_internal={},  # ISTAT projects Campania slight population decline; using zero
        pop_net_increase_od={},
        area_toll_applicable=True,  # Naples ZTL already in place; model its expansion
        # EV trajectory (PI=1): EAFO 2019 baseline + PNIEC 2023 Policy Driven
        # 2030 target (6.6M / ~40M Italian fleet = 16.5%) + EU 2050 trajectory.
        ev_pi_trajectory={
            2019: 0.3, 2022: 1.0, 2025: 4.0,
            2030: 18.0, 2040: 51.0, 2050: 85.0,  # ZEV share, D3.4a Table A-27
        },
        ev_bau_damping_pivot_year=2026,  # same structure as Tallinn; BAU ~half PI=1 from 2026
        # class R, fitted to the ABM light reference and optimised pkm shares 2030/2040/2050
        # (regsim sd_knowing.recalibrate_class_r, decision D32; loss 0.0047)
        mode_change_damping=0.0846,
        attr_offset={"car passenger": 0.326, "public transport": -1.289, "bicycle": -14.852, "walk": -15.806},
    ),
    energy_demand=EnergyDemandConfig(
        # reconstructed from D3.4a (build_naples_d34a_xlsx.py); replaces the estimate of build_naples_xlsx.py
        xlsx_path=_resolve_data_path("EN_MEADCityInput_Naples_D34a.xlsx"),
        sheet_name="CETS",
        detailed_heating_breakdown=False,
    ),
    energy_supply=EnergySupplyConfig(
        xlsx_path=_resolve_data_path("Supply_Data_Naples.xlsx"),  # IESopt Tables A-19, A-24, A-25 (D3.4a)
        has_district_heating=True,  # DH from 2030 in the CETS (geothermal, heat pumps)
        # Italy grid EF trajectory:
        #   2019: 0.362 kg/kWh (Nowtricity/Terna actual)
        #   2030: 0.150 kg/kWh (PNIEC 2023 target: 65% renewable in electricity)
        #   2050: 0.010 kg/kWh (PNIEC full decarbonisation goal)
        grid_emission_factor={2019: 0.362, 2030: 0.150, 2050: 0.010},
        plater_pv_target_2050=899.0,  # A24
        fossil_power_dispatch_mode="fixed_schedule",
        fossil_power_phases_out_after_10y=False,
        fossil_power_emission_factor=0.45,
    ),

    # Italian fleet about 7 l/100 km (0.65 kWh/vkm), EV 0.17 kWh/vkm (estimates); load factor 1.11 (D3.4a Table A-15)
    transport_energy=TransportEnergyConfig(car_fossil_kwh_per_vkm=0.65, car_electric_kwh_per_vkm=0.17, load_factor=1.11, od_energy_share=0.5),
)


# ---------------------------------------------------------------------------
# SOUTH WESTPHALIA -- regional demonstrator (Soil fertility & agriculture),
# populated from KNOWING Deliverable D3.5. PROVISIONAL: built for
# calibration; class-R parameters (base attractiveness, damping) and the
# length-class structure of trips are to be recalibrated to the ABM light
# base year (configs/sd_calibration_targets.csv in the regsim repository).
#
# DATA SOURCES (per field):
#   Population     : D3.5 Table 11 (1,381,751 in 2019; 1,264,822 in 2050).
#                    The OD-zone population is not published; 437,000 is a
#                    placeholder giving the OD zone the same per-capita trip
#                    rate as residents (24 % of trips assumed OD).
#   Trip rates     : ABM light base year (D3.5 Fig. 47/48), split into length
#                    classes (<3, 3-15, >15 km) assuming exponential trip-length
#                    distributions with the ABM mean per mode
#                    (estimate_trip_classes.py).
#   Speeds         : Granollers values (regional structure), provisional.
#   Coping types   : D3.5 Fig. 56, rural Germany (Table 25 lists the same
#                    values in reverse order).
#   CDD            : D3.5 Table 13 (MAED-City base year).
#   Costs          : fuel ~0.10 EUR/km (7 l/100 km x 1.40 EUR/l, 2019);
#                    parking base from Table 23 (0.5-2.5 EUR/h); PT fare and
#                    value of time are placeholders.
#   Policy levers  : D3.5 Table 23 (ABM light optimised scenario), mapped
#                    like Tallinn's Table 1. No area toll in SWF.
#   EV trajectory  : ZEV share 0.2 % (2019, Table 11), 19/64/91 % (Table 23).
#   Energy demand  : EN_MEADCityInput_SouthWestphalia.xlsx, reconstructed
#                    from D3.5 (build_southwestphalia_xlsx.py).
#   Energy supply  : Supply_Data_SouthWestphalia.xlsx, IESopt Tables 15-22.
#   Grid EF        : Germany 2019 about 0.40 kg/kWh (UBA); 2030 0.15 and
#                    2050 0.01 assumed in line with 80 % RE by 2030 and
#                    climate neutrality by 2045 -- not from D3.5.
# ---------------------------------------------------------------------------

_swf_trip_rate_internal = {
    "short":  [0.17597, 0.04197, 0.06876, 0.05996, 0.40118],
    "medium":  [0.53085, 0.12052, 0.18958, 0.12759, 0.01614],
    "long":  [0.89703, 0.16466, 0.22111, 0.06537, 0.0],
}
_swf_trip_rate_od = {
    "short":  [0.17597, 0.04197, 0.06876, 0.05996, 0.40118],
    "medium":  [0.53085, 0.12052, 0.18958, 0.12759, 0.01614],
    "long":  [0.89703, 0.16466, 0.22111, 0.06537, 0.0],
}

SOUTH_WESTPHALIA = CityConfig(
    name="South Westphalia",
    country="Germany (North Rhine-Westphalia)",
    mobility=MobilityConfig(
        population_internal=1_381_751,
        population_od=437_000,
        # class centroids from ABM light mean trip lengths (estimate_trip_classes.py)
        initial_trip_length_internal=(1.11, 8.34, 38.56),
        initial_trip_length_od=(1.11, 8.34, 38.56),
        initial_trip_rate={"internal": _swf_trip_rate_internal, "origin destination": _swf_trip_rate_od},
        initial_travel_speed={"internal": _granollers_speed_internal, "origin destination": _granollers_speed_od},
        coping_type_distribution=(0.12, 0.21, 0.27, 0.12, 0.14, 0.15),
        cooling_degree_days=21,
        cooling_degree_days_trajectory={2019: 21.0, 2050: 37.0},  # D3.5 Table 13 (CETS 2050)
        apply_cdd_baseattr_compensation=False,
        base_attr_by_mode_and_zone={  # start values from Granollers; class R, to be recalibrated
            "car":              (2.04, 3.30),
            "car passenger":    (1.80, 3.00),
            "public transport": (2.66, 3.90),
            "bicycle":          (4.00, 6.50),
            "walk":             (5.88, 12.00),
        },
        attr_distinction=0.22,
        value_of_time_base=10.0,  # placeholder (class B)
        value_of_time_dist=0.1,
        value_of_time_profile=(3.0, -2.0, 2.0, -3.0, -1.0, 1.0),
        network_capacity=None,
        pt_cost_by_zone=(2.0, 3.5),  # placeholder
        car_cost_per_km_fuel_constant=0.10,
        car_cost_per_km_ev_constant=0.05,
        parking_cost_base=1.5,
        policy_car_costs_fuel={},
        policy_car_costs_ev={},
        policy_capacity_adaptation={2019: 1, 2030: 0.95, 2040: 0.85, 2050: 0.75},
        policy_parking_cost_adaptation={2019: 1, 2030: 1.1, 2040: 1.2, 2050: 1.3},
        policy_area_toll={},
        policy_road_pricing={2019: 0, 2030: 0.05, 2040: 0.15, 2050: 0.25},
        policy_cycling_attractiveness={2019: 0, 2030: 0.5, 2040: 1.5, 2050: 2.5},
        policy_pt_traveltime_adaptation={2019: 1, 2030: 0.95, 2040: 0.85, 2050: 0.75},
        policy_distance_adaptation={2019: 0, 2030: 0.05, 2040: 0.05, 2050: 0.05},
        policy_car_passenger_attractiveness={2019: 0, 2030: 0.5, 2040: 1.5, 2050: 2.5},
        policy_ev_adoption_adaptation={},
        policy_street_green={},
        pop_net_increase_internal={},
        pop_net_increase_od={},
        area_toll_applicable=False,
        ev_pi_trajectory={2019: 0.2, 2030: 19.0, 2040: 64.0, 2050: 91.0},
        ev_bau_damping_pivot_year=2026,
        # class R, fitted to the ABM light reference and optimised pkm shares 2030/2040/2050
        # (regsim sd_knowing.recalibrate_class_r, decision D32; loss 0.0153)
        mode_change_damping=0.4791,
        attr_offset={"car passenger": -1.400, "public transport": 7.929, "bicycle": 1.099, "walk": 3.574},
    ),
    energy_demand=EnergyDemandConfig(
        xlsx_path=_resolve_data_path("EN_MEADCityInput_SouthWestphalia.xlsx"),
        sheet_name="CETS",
        detailed_heating_breakdown=True,
    ),
    energy_supply=EnergySupplyConfig(
        xlsx_path=_resolve_data_path("Supply_Data_SouthWestphalia.xlsx"),
        has_district_heating=True,
        grid_emission_factor={2019: 0.40, 2030: 0.15, 2050: 0.01},
        plater_pv_target_2050=7003.0,
        fossil_power_dispatch_mode="demand_filling",
        fossil_power_phases_out_after_10y=True,
        fossil_power_emission_factor=0.55,
    ),
    # German fleet about 7.4 l/100 km (0.69 kWh/vkm), EV 0.19 kWh/vkm (estimates); load factor 1.13 (D3.5 Table 11)
    transport_energy=TransportEnergyConfig(car_fossil_kwh_per_vkm=0.69, car_electric_kwh_per_vkm=0.19, load_factor=1.13, od_energy_share=0.5),
)
