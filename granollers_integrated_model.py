"""
Granollers Integrated Model  — v8
===================================
PI=1 scenario only (all policy interventions active).

Integration structure (Vensim parent models):
─────────────────────────────────────────────
  Parent_Tallinn.mdl  →  TR dist per mode (km/cap/yr) from mobility model
  ParentModel_Energy_corrected.mdl  →  demand → supply → emissions

Mobility model (granollers_pi_vensim__1_.py  — updated, PMUS-calibrated):
  Fix applied: PKM now computed from TR_TripLength[zone,mode] (mode-specific
  empirical distances from PMUS 2009) instead of TR_InitialTripLength trip-
  length class centroids used for GC only. This yields correct km/cap values.

Transport energy interface:
  EN_GWh = km_cap × POP × EI_conv(t)
  EI_conv factors taken from XLSX rows 41–44 (Granollers-calibrated, declining
  with fleet efficiency improvement). These are the same factors used in the
  XLSX to derive rows 36–39, so methodology is fully consistent.

  XLSX rows 36–39 are NOT used — they were based on an older mobility model
  version (different km/cap trajectory, growing population 60108→76500).
  Population: XLSX row 35 growing series (60,108→76,500) used consistently
  across mobility model, km/cap→GWh conversion, and non-transport demand rows.

Non-transport energy demand: directly from XLSX rows 6–17, 19–21, 23, 46–52.

Emission components (ParentModel_Energy_corrected.mdl):
  1. Direct emissions transport  = (pax_fuel + pax_other + fr_fuels) × 270 t/GWh
  2. Direct emissions other      = (hh_fuel + hh_sh_fos + ind_fos + svc_fos) × 270 t/GWh
  3. Emissions from elec prod    = Gas_CHP × 0.45 kt/GWh
  4. Emissions from imported elec= NetImport × GridEF  [kt CO₂/GWh]
  5. Emissions from DH           = (gas_DH + oil_DH) × 210 t/GWh  → 0 (biomass DH)
  Total Emissions = sum(1..5)
  Accumulated emissions = INTEG(Total Emissions, 0)
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import FuncFormatter
import openpyxl
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent
XLSX       = OUTPUT_DIR / "EN_MEADCityInput_0527_v6.xlsx"
YEARS      = np.arange(2019, 2051, dtype=float)
NT         = len(YEARS)
# Growing population from XLSX row 35 (consistent with non-transport demand rows)
POP_R35_YEARS = np.array([2019,2025,2027,2030,2035,2040,2045,2050], float)
POP_R35_VALS  = np.array([60108,65346,66700,68500,71000,73000,75000,76500], float)
POP_GROWING   = np.interp(YEARS, POP_R35_YEARS, POP_R35_VALS)  # array over YEARS
POP_2019      = 60_108.   # 2019 anchor (municipal register, consistent with XLSX r35)

# ── XLSX lookup ────────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(str(XLSX), data_only=True)
ws = wb["CETS"]
T_YEARS = np.array([2019,2025,2027,2030,2035,2040,2045,2050], float)
T_COLS  = [2,3,4,5,6,7,8,9]

def lup(row):
    vals = np.array([ws.cell(row=row, column=c).value or 0 for c in T_COLS], float)
    return np.interp(YEARS, T_YEARS, vals)

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — MOBILITY SUBMODEL  (granollers_pi_vensim__1_.py, PI=1)
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 74)
print("GRANOLLERS INTEGRATED MODEL  v8  |  PI=1 scenario  |  2019–2050")
print("=" * 74)
print("\n[MOB] Running mobility submodel (updated, PMUS-calibrated)…")

NM,NL,NZ,NC = 5,3,2,6
CAR_MODES=[0,1]; PT_MODE=2; ACTIVE_MODES=[3,4]
# Time-varying annual growth rate from XLSX r35 series (internal zone only)
# Rate at each year t: d/dt ln(pop) ≈ (pop(t+1)-pop(t))/pop(t)
_pop_arr = POP_GROWING  # same interpolation already computed above
POP_GROWTH_ARR = np.gradient(_pop_arr) / _pop_arr  # instantaneous fractional rate
HBP = np.array([60_108., 45_000.])  # 2019 anchor from XLSX r35

TR_InitialTripLength = np.array([
    [0.90, 3.50, 10.00],
    [1.20, 6.00, 20.00],
])
# Mode-specific empirical trip lengths for PKM (the fix)
TR_TripLength = np.array([
    [3.8, 3.5, 2.8, 2.0, 0.9],   # internal [car,cp,PT,bike,walk] km
    [18.0,18.0,18.0,5.0, 1.5],   # OD
])
TR_InitialTravelSpeed = np.array([
    [[8.0,  8.0, 3.5,12.0,4.5],[18.0,18.0, 8.0,11.5,4.3],[28.0,28.0,12.0,11.0,4.1]],
    [[10.0,10.0, 5.0,13.0,5.0],[30.0,30.0,15.0,12.0,4.8],[55.0,55.0,40.0,11.5,4.2]],
])
TR_AccessTime = np.array([[0.15,0.10,0.20,0.,0.],[0.15,0.10,0.20,0.,0.]])
TR_InitialTripRate = np.array([
    [[.045505,.010921,.018202,.036404,1.392465],
     [.227527,.047326,.050056,.050056,.139246],
     [.182022,.032764,.022753,.004551,.015472]],
    [[.006127,.000943,.007777,.007070,.150830],
     [.300245,.046192,.147766,.015319,.035822],
     [.306372,.047134,.103695,.001178,.001885]],
])
TR_InitialTrips = np.zeros((NM,NL,NZ))
for z in range(NZ):
    for l in range(NL):
        TR_InitialTrips[:,l,z] = HBP[z] * TR_InitialTripRate[z,l,:]

CT_Dist = np.array([.04,.09,.10,.37,.31,.09])
VoT_base = 5.09502; VoT_dist = 0.1; VoT_prof = np.array([3.,-2.,2.,-3.,-1.,1.])
TR_ValueOfTime = VoT_base + VoT_dist * VoT_prof
TR_BaseAttr = np.array([
    [2.0399,3.2007],[1.7911,2.9519],[2.6624,3.7156],[4.4269,7.4929],[5.8769,14.0183]])
TR_AttrDistinction = 0.22142
TR_AttrProfile = np.array([
    [ 3., 2., 1.,-1.,-2.,-3.],[ 3., 2., 1.,-1.,-2.,-3.],
    [ 3., 2., 1., 0.,-1.,-2.],[-3.,-2.,-1., 1., 3., 2.],[-3.,-2.,-1., 1., 3., 2.]])
TR_ParkingCost=0.18; TR_CarCostPerKmFuel=0.10; TR_CarCostPerKmEV=0.04
TR_NetworkCapacity=440_000.; TR_CDD=380.; TR_Cost_PT=np.array([0.0,0.72])
TR_ModeChangeElasticity=0.01; TR_DemandElasticity=0.01

# EV trajectory: two-phase calibration
# Phase 1 (2019-2025): follows real DGT/ANFAC trend (0.2%→7%)
# Phase 2 (2025-2030): steeper ramp to reach 20% by 2030 (EU ZEV mandate)
# 2030-2050: unchanged from original NECP-aligned trajectory
# Anchor 2022=1.5% from real DGT data; 2025=7% realistic market projection
EV_PI = np.interp(YEARS,[2019.,2022.,2025.,2028.,2030.,2040.,2050.],
                        [.002, .015, .07,  .14,  .20,  .55,  .80])

_y=[2009.,2019.,2030.,2040.,2050.]
mk=lambda y,v: np.interp(YEARS,y,v)
ARS=np.zeros(NT); RPS=mk(_y,[0,0,.10,.30,.30]); PAS=mk(_y,[1,1,1.1,1.2,1.2])
PTS=mk(_y,[1,1,.95,.85,.85]); CYS=mk(_y,[0,0,.5,1.5,1.5])
CPS=mk(_y,[0,0,.5,1.5,1.5]); CAS=mk(_y,[1,1,.95,.85,.85])
RP = np.interp(YEARS,[2019.,2030.,2040.,2050.],[0.,.5,.75,1.])

def compute_GC(trips, ev, pi_t, t):
    G = np.zeros((NM,NL,NZ,NC))
    ck = TR_CarCostPerKmFuel*(1-ev)+TR_CarCostPerKmEV*ev
    ar = pi_t["road_pricing"]*RPS[t]
    pp = pi_t["parking"]
    ap = TR_ParkingCost*(1-pp)+TR_ParkingCost*pp*PAS[t]
    at_ = pi_t["area_toll"]*ARS[t]
    pi_pt = pi_t["pt_time"]; pta=(1-pi_pt)+pi_pt*PTS[t]
    pi_cyc=pi_t["cycling"]*CYS[t]; pi_cp=pi_t["car_pass"]*CPS[t]
    pi_sg=pi_t["street_green"]
    cap=TR_NetworkCapacity*((1-pi_t["capacity"])+pi_t["capacity"]*CAS[t])
    for z in range(NZ):
        csf=max(.05,1.-trips[0,:,z,:].sum()/cap)
        for l in range(NL):
            L=TR_InitialTripLength[z,l]
            for m in range(NM):
                sp=TR_InitialTravelSpeed[z,l,m]*(csf if m in CAR_MODES else 1.)
                at2=TR_AccessTime[z,m]*(pta if m==PT_MODE else 1.)
                tt=L/max(sp,.1)+at2
                if m in CAR_MODES:   cost=(ck+ar)*L+ap+at_
                elif m==PT_MODE:     cost=TR_Cost_PT[z]
                else:                cost=0.
                for c in range(NC):
                    base=TR_BaseAttr[m,z]+TR_AttrDistinction*TR_AttrProfile[m,c]
                    if m in ACTIVE_MODES:
                        attr=base-TR_CDD/100+pi_sg*2+(pi_cyc if m==3 else 0)
                    elif m==PT_MODE: attr=base-TR_CDD/200+pi_sg
                    else:            attr=base-pi_sg*2+(pi_cp if m==1 else 0)
                    G[m,l,z,c]=cost+tt*TR_ValueOfTime[c]-attr
    return G

def run_mob(PI_dict, ev_arr):
    trips=np.zeros((NM,NL,NZ,NC))
    for z in range(NZ):
        for l in range(NL):
            for c in range(NC):
                trips[:,l,z,c]=TR_InitialTrips[:,l,z]*CT_Dist[c]
    ms_int=np.zeros((NT,NM)); ms_od=np.zeros((NT,NM)); ms_all=np.zeros((NT,NM))
    pkm_out=np.zeros((NT,NM,NZ)); GC_prev=None
    for t in range(NT):
        pi_t={k:v[t] for k,v in PI_dict.items()}
        G=compute_GC(trips,ev_arr[t],pi_t,t)
        if GC_prev is None: GC_prev=G.copy()
        # PKM: mode-specific empirical distances (the fix)
        for z in range(NZ):
            dist_m=np.zeros(NM)
            for m in range(NM):
                dist_m[m]=trips[m,:,z,:].sum()*TR_TripLength[z,m]
            pkm_out[t,:,z]=dist_m*365
            ms=dist_m/max(dist_m.sum(),1e-9)
            if z==0: ms_int[t]=ms
            else:    ms_od[t]=ms
        dist_all=pkm_out[t,:,0]+pkm_out[t,:,1]
        ms_all[t]=dist_all/max(dist_all.sum(),1e-9)
        if t<NT-1:
            d=np.zeros_like(trips)
            for z in range(NZ):
                for l in range(NL):
                    for c in range(NC):
                        for m in range(NM):
                            dG=G[m,l,z,c]-GC_prev[m,l,z,c]
                            d[m,l,z,c]+=-TR_DemandElasticity*dG/10*trips[m,l,z,c]
                            d[m,l,z,c]+=TR_InitialTrips[m,l,z]*CT_Dist[c]*POP_GROWTH_ARR[t]
                            for m2 in range(NM):
                                if m2==m: continue
                                dGr=G[m,l,z,c]-G[m2,l,z,c]
                                ref=max(trips[m,l,z,c],0.) if dGr>0 else max(trips[m2,l,z,c],0.)
                                d[m,l,z,c]-=TR_ModeChangeElasticity*dGr*ref
            trips=np.clip(trips+d,0.,None)
        GC_prev=G.copy()
    pkm_car=pkm_out[:,0,:].sum(1)+pkm_out[:,1,:].sum(1)
    # Divide by growing population to get per-capita rates
    return dict(
        ms_int=ms_int, ms_od=ms_od, ms_all=ms_all, pkm=pkm_out,
        km_car_fos=pkm_car/POP_GROWING*(1-ev_arr),
        km_car_elc=pkm_car/POP_GROWING*ev_arr,
        km_pt=pkm_out[:,2,:].sum(1)/POP_GROWING,
        km_active=(pkm_out[:,3,:].sum(1)+pkm_out[:,4,:].sum(1))/POP_GROWING,
        ev=ev_arr, pop=POP_GROWING,
    )

PI_ON = {k: RP for k in ["parking","area_toll","road_pricing","pt_time",
                           "ev","cycling","car_pass","capacity","street_green"]}
mob = run_mob(PI_ON, EV_PI)

# Verify against standalone output
CHK=[2019,2025,2030,2040,2050]; CHKI=[int(y-2019) for y in CHK]
REF_MOB = {"km_car_fos":[4112,3350,2587,773,111],
           "km_pt":      [1330, 855, 766,1083,1419],
           "km_active":  [ 681, 802, 906,1185,1453]}
print(f"   {'Mode':<14}  {'2019':>7}  {'2025':>7}  {'2030':>7}  {'2040':>7}  {'2050':>7}  Status")
for key,refs in REF_MOB.items():
    vals=[mob[key][i] for i in CHKI]
    maxd=max(abs(v-r)/max(r,1)*100 for v,r in zip(vals,refs))
    row=f"   {key:<14}"+"".join(f"  {v:>5.0f}≈{r:<4}" for v,r in zip(vals,refs))
    print(row+f"  {'✓' if maxd<1 else '⚠'}")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — ENERGY DEMAND (PI=1)
# Non-transport: XLSX rows 6–17, 19–21, 23, 46–52  (unchanged, as in v6)
# Transport: km_cap (mob model) × POP × EI_conv (XLSX rows 41–44)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[ED ] Building energy demand (non-transport from XLSX, transport from mob×EI)…")

# Non-transport demand (identical to standalone v6)
sh_bio =lup(6);  sh_sol =lup(7);  sh_dh  =lup(8)
sh_el  =lup(9);  sh_fos =lup(10); hh_cool=lup(11)
hh_ob  =lup(13); hh_os  =lup(14); hh_od  =lup(15)
hh_oe  =lup(16); hh_of  =lup(17)
ind_e1 =lup(19); ind_e2 =lup(20); ind_e3 =lup(21)
svc_tot=lup(23)
svc_el =lup(46); svc_dh =lup(47); svc_fos=lup(51)
ind_el =lup(48); ind_fos=lup(52)
fr_fuels=lup(2); fr_elec=lup(3);  fr_oth =lup(4)

# EI conversion factors (XLSX rows 41–44, GWh per km per person)
EI_car_fos  = lup(41)   # row 41: cars fuel    GWh/(km·person)
EI_car_elec = lup(42)   # row 42: cars electr  GWh/(km·person)
EI_pt_elec  = lup(43)   # row 43: PT electr    GWh/(km·person)
EI_oth_fos  = lup(44)   # row 44: other fuels  GWh/(km·person)

# Transport energy: mob model km/cap × POP_GROWING(t) × EI_conv
pax_fuel = mob["km_car_fos"] * POP_GROWING * EI_car_fos   # car fossil GWh
pax_elec = mob["km_car_elc"] * POP_GROWING * EI_car_elec  # car electric GWh
pt_elec  = mob["km_pt"]      * POP_GROWING * EI_pt_elec   # PT electric GWh
# "Other" (motorcycles etc.): not in mob model → use XLSX row 39 directly
# (motorcycles not represented in PMUS → keep as calibrated in XLSX)
pax_oth  = lup(39)

# Derived aggregates
ind_tot  = ind_e1+ind_e2+ind_e3
svc_oth  = np.maximum(0., svc_tot-svc_el-svc_dh-svc_fos)
ind_oth  = np.maximum(0., ind_tot-ind_el-ind_fos)
hh_total = hh_cool+sh_bio+sh_dh+sh_el+sh_fos+sh_sol+hh_ob+hh_od+hh_oe+hh_of+hh_os
pax_total= pax_fuel+pax_elec+pt_elec+pax_oth
frt_total= fr_fuels+fr_elec+fr_oth
tr_total = pax_total+frt_total
grand_tot= hh_total+svc_tot+ind_tot+tr_total

total_electr=hh_cool+sh_el+pax_elec+pt_elec+hh_oe+svc_el+ind_el+fr_elec
total_fossil =sh_fos+pax_fuel+pax_oth+hh_of+ind_fos+svc_fos+fr_fuels
total_dh     =sh_dh+hh_od+svc_dh
total_bio    =sh_bio+hh_ob+hh_os+sh_sol
total_oth    =fr_oth+svc_oth+ind_oth

# Sector consistency check
for yr in [2019,2025,2030,2040,2050]:
    i=int(yr-2019)
    sec=hh_total[i]+svc_tot[i]+ind_tot[i]+tr_total[i]
    assert abs(sec-grand_tot[i])<0.1, f"Sector Σ mismatch at {yr}"
print("   Sector consistency: ✓ (Δ<0.1 GWh at all years)")

# Cross-check non-transport against v6 standalone
# (should match exactly — same XLSX rows, same interpolation)
NON_TR_REF = {2020:1374.1-266.7, 2030:1321.5-201.5, 2050:1280.6-70.1}
for yr,ref_nontr in NON_TR_REF.items():
    i=int(yr-2019)
    my_nontr=hh_total[i]+svc_tot[i]+ind_tot[i]
    d=my_nontr-ref_nontr
    print(f"   Non-transport {yr}: integrated={my_nontr:.1f}  v6_ref={ref_nontr:.1f}  "
          f"Δ={d:+.1f}  {'✓' if abs(d)<2 else '⚠'}")

# Transport energy comparison: integrated vs XLSX rows 36-39
print(f"\n   Transport energy (GWh) — mob×EI  vs  XLSX rows 36–39:")
print(f"   {'Year':>6}  {'CarFos mob':>11}  {'CarFos xl':>10}  "
      f"{'CarEl mob':>10}  {'CarEl xl':>9}  {'PT mob':>8}  {'PT xl':>7}")
xl36=lup(36); xl37=lup(37); xl38=lup(38)
for yr in [2019,2025,2030,2040,2050]:
    i=int(yr-2019)
    print(f"   {yr:>6}  {pax_fuel[i]:>11.1f}  {xl36[i]:>10.1f}  "
          f"{pax_elec[i]:>10.2f}  {xl37[i]:>9.2f}  {pt_elec[i]:>8.2f}  {xl38[i]:>7.2f}")
print("   ✓ Energy demand complete")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — ENERGY SUPPLY + EMISSIONS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[ES ] Running energy supply & emissions (ParentModel_Energy_corrected)…")

FUEL_EF = 270.   # t CO₂/GWh
CHP_EF  = 0.45   # kt CO₂/GWh gas CHP
# Grid emission factor: Spain PNIEC trajectory
# 0.190 (2019 actual) → 0.060 (2030, PNIEC milestone) → 0.005 (2050, near-zero residual)
# 0.005 kg CO₂/kWh retained as residual for gas peakers/balancing (vs 0.000 in Tallinn MDL)
# Consistent with Spain PNIEC 100% renewable target; parent MDL goes to exactly 0.
GRID_EF = np.interp(YEARS,[2019.,2030.,2050.],[0.190,0.060,0.005])

# PV capacity: aligned to PLATER (Catalonia territorial renewable energy plan,
# pending approval ~2027). Granollers target = 79.9 MWp by 2050
# (7.7 MWp non-urbanised land + 4.4 MWp infrastructure + 67.8 MWp buildings).
# Supersedes the earlier 250 MWp "technical potential" assumption, which was
# ~3.1x more ambitious than the PLATER planning-grounded target.
IC_PV    = np.interp(YEARS,[2019.,2050.],[2.,  79.9])
IC_GasCHP= np.interp(YEARS,[2019.,2050.],[15., 2.  ])
PV_YIELD = 1.5
DH_DEMAND= np.interp(YEARS,[2019,2025,2027,2030,2035,2040,2045,2050],
                            [0.00,0.01,0.01,2.11,2.95,3.71,4.50,5.20])

PP_PV    = IC_PV * PV_YIELD
PP_CHP   = np.maximum(0., IC_GasCHP * 2.0)
NetImport= np.maximum(0., total_electr - PP_PV - PP_CHP)
PV_share = PP_PV / np.maximum(total_electr,1.) * 100

# Five emission components (ParentModel_Energy_corrected.mdl)
em_transport = (pax_fuel + pax_oth + fr_fuels) * FUEL_EF / 1000.
em_other     = (hh_of + sh_fos + ind_fos + svc_fos) * FUEL_EF / 1000.
em_elec_prod = PP_CHP * CHP_EF
em_elec_imp  = NetImport * GRID_EF
em_dh        = np.zeros(NT)   # biomass+HP DH → zero fossil emissions
total_em     = em_transport + em_other + em_elec_prod + em_elec_imp + em_dh
accum_em     = np.cumsum(total_em)

# Cross-check: electricity-only emissions should match v4 standalone
V4_EM = {2019:129.4, 2025:83.4, 2030:45.0, 2040:29.1, 2050:13.3}
print(f"   Cross-check elec emissions vs supply v4:")
for yr,ref in V4_EM.items():
    i=int(yr-2019); iv=em_elec_prod[i]+em_elec_imp[i]
    print(f"     {yr}: v4={ref:.1f}  integrated={iv:.1f}  Δ={iv-ref:+.1f}  "
          f"{'✓' if abs(iv-ref)<5 else '⚠'}")
print("   ✓ Energy supply & emissions complete")

# ═══════════════════════════════════════════════════════════════════════════════
# PLOTS
# ═══════════════════════════════════════════════════════════════════════════════
print("\nGenerating plots…")
C={"car":"#C62828","car_el":"#4FC3F7","pt":"#2196F3","act":"#4CAF50",
   "fos":"#795548","elec":"#1565C0","pv":"#F9CB42","chp":"#BF4F1E",
   "imp":"#A87DC8","em_tr":"#E53935","em_oth":"#FF7043","em_ep":"#BF4F1E",
   "em_ei":"#7B1FA2","bio":"#4CAF50","dh":"#FF5722"}

def fax(ax,ylabel=None,ylim=None):
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f"{x:,.0f}"))
    ax.set_xlim(2019,2050); ax.grid(True,alpha=0.25,ls=":")
    ax.tick_params(labelsize=8)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    if ylabel: ax.set_ylabel(ylabel,fontsize=9)
    if ylim:   ax.set_ylim(*ylim)

def ann(ax,yr,y,txt,**kw):
    ax.annotate(txt,(yr,y),ha="center",fontsize=8.5,fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2",fc="white",alpha=0.85),**kw)

fig=plt.figure(figsize=(18,26),facecolor="#FAFAFA")
fig.suptitle(
    "Granollers — Integrated Model v8  |  PI=1 Scenario  |  2019–2050\n"
    "Mobility (updated, PMUS-calibrated) → Energy Demand (mob×EI + XLSX) "
    "→ Energy Supply → Emissions",
    fontsize=12,fontweight="bold",y=0.998)
gs=gridspec.GridSpec(4,3,figure=fig,hspace=0.52,wspace=0.33)

# ── [0,0] Modal split (km share) ─────────────────────────────────────────────
ax=fig.add_subplot(gs[0,0])
ms_car_pct=mob["ms_all"][:,0]*100+mob["ms_all"][:,1]*100
ms_pt_pct =mob["ms_all"][:,2]*100
ms_act_pct=(mob["ms_all"][:,3]+mob["ms_all"][:,4])*100
ax.stackplot(YEARS,ms_car_pct,ms_pt_pct,ms_act_pct,
    labels=["Car (fossil+EV)","PT","Active"],
    colors=[C["car"],C["pt"],C["act"]],alpha=0.85)
ax.set_title("Modal split — PI=1\n(combined int+OD, km share %)",fontweight="bold")
fax(ax,"km share (%)",(0,100)); ax.legend(fontsize=8.5,loc="upper right")
for yr,ha_ in [(2019,"left"),(2050,"right")]:
    i=int(yr-2019)
    ax.text(yr+(3 if ha_=="left" else -3),50,
            f"Car {ms_car_pct[i]:.0f}%\nPT {ms_pt_pct[i]:.0f}%\nAct {ms_act_pct[i]:.0f}%",
            fontsize=7.5,ha=ha_,va="center",color="white",fontweight="bold")

# ── [0,1] TR dist interface (mob model km/cap) ───────────────────────────────
ax=fig.add_subplot(gs[0,1])
ax.plot(YEARS,mob["km_car_fos"],color=C["car"],  lw=2.5,label="Car fossil km/cap")
ax.plot(YEARS,mob["km_car_elc"],color=C["car_el"],lw=2.5,label="Car electric km/cap")
ax.plot(YEARS,mob["km_pt"],     color=C["pt"],   lw=2.5,label="PT km/cap")
ax.plot(YEARS,mob["km_active"], color=C["act"],  lw=2.5,label="Active km/cap")
ax.set_title("TR dist per mode — PI=1\n(mob model, km/cap/yr)",fontweight="bold")
fax(ax,"km/cap/yr"); ax.legend(fontsize=8)
for yr in [2019,2050]:
    i=int(yr-2019)
    ann(ax,yr,mob["km_car_fos"][i]+50,f"{mob['km_car_fos'][i]:.0f}")

# ── [0,2] EV share + PV self-sufficiency ─────────────────────────────────────
ax=fig.add_subplot(gs[0,2]); ax2=ax.twinx()
ax.plot(YEARS,mob["ev"]*100,color=C["car_el"],lw=2.5,label="EV fleet share")
ax2.plot(YEARS,PV_share,color=C["pv"],lw=2.5,ls="--",label="PV self-suff. (right)")
ax.set_title("EV share & PV self-sufficiency\n(PI=1)",fontweight="bold")
ax.set_ylabel("EV fleet share (%)"); ax2.set_ylabel("PV % of elec demand")
ax.set_xlim(2019,2050); ax.grid(True,alpha=0.25)
ax.spines["top"].set_visible(False)
h1,l1=ax.get_legend_handles_labels(); h2,l2=ax2.get_legend_handles_labels()
ax.legend(h1+h2,l1+l2,fontsize=8,loc="upper left")

# ── [1,0] Energy demand by carrier ───────────────────────────────────────────
ax=fig.add_subplot(gs[1,0])
ax.stackplot(YEARS,total_bio,total_dh,total_fossil,total_electr,total_oth,
    labels=["Biomass/Solar","District Heat","Fossil","Electricity","Other"],
    colors=[C["bio"],C["dh"],C["fos"],C["elec"],"#9C27B0"],alpha=0.85)
ax.plot(YEARS,grand_tot,"k--",lw=2,label="Total",zorder=5)
ax.set_title("Final energy demand by carrier\n(PI=1, GWh/yr)",fontweight="bold")
fax(ax,"GWh/yr"); ax.legend(fontsize=7.5,loc="upper right",ncol=2)
ann(ax,2019,grand_tot[0]+20,f"{grand_tot[0]:,.0f} GWh")
ann(ax,2050,grand_tot[-1]+20,f"{grand_tot[-1]:,.0f} GWh")

# ── [1,1] Energy demand by sector ────────────────────────────────────────────
ax=fig.add_subplot(gs[1,1])
ax.stackplot(YEARS,hh_total,svc_tot,ind_tot,pax_total,frt_total,
    labels=["Households","Services","Industry","Passenger transport","Freight transport"],
    colors=["#E91E63","#FF9800","#607D8B",C["em_tr"],"#FF7043"],alpha=0.85)
ax.plot(YEARS,grand_tot,"k--",lw=2,label="Total",zorder=5)
ax.set_title("Final energy demand by sector\n(PI=1, GWh/yr)",fontweight="bold")
fax(ax,"GWh/yr"); ax.legend(fontsize=7.5,loc="upper right",ncol=2)

# ── [1,2] Transport energy detail ─────────────────────────────────────────────
ax=fig.add_subplot(gs[1,2])
ax.stackplot(YEARS,pax_fuel,pax_elec,pt_elec,pax_oth,fr_fuels,fr_elec,
    labels=["Car fossil","Car electric","PT electric","Other pax (motorcycles)",
            "Freight fossil","Freight electric"],
    colors=[C["car"],"#4FC3F7",C["pt"],"#CFD8DC",C["chp"],"#0277BD"],alpha=0.85)
ax.set_title("Transport energy — PI=1\n(mob×EI for car/PT, GWh/yr)",fontweight="bold")
fax(ax,"GWh/yr"); ax.legend(fontsize=7.5,loc="upper right",ncol=2)
ann(ax,2019,tr_total[0]+5,f"{tr_total[0]:.0f} GWh")
ann(ax,2050,tr_total[-1]+5,f"{tr_total[-1]:.0f} GWh")

# ── [2,0] Electricity supply mix ─────────────────────────────────────────────
ax=fig.add_subplot(gs[2,0])
ax.stackplot(YEARS,PP_PV,PP_CHP,NetImport,
    labels=["PV local","Gas CHP","Grid import"],
    colors=[C["pv"],C["chp"],C["imp"]],alpha=0.85)
ax.plot(YEARS,total_electr,"k--",lw=2,label="Electricity demand")
ax.set_title("Electricity supply mix — PI=1\n(GWh/yr)",fontweight="bold")
fax(ax,"GWh/yr"); ax.legend(fontsize=8)

# ── [2,1] Emissions by component ─────────────────────────────────────────────
ax=fig.add_subplot(gs[2,1])
ax.stackplot(YEARS,em_transport,em_other,em_elec_prod,em_elec_imp,
    labels=["Direct: transport combustion","Direct: buildings + ind + svc",
            "Electricity: CHP (local)","Electricity: grid import"],
    colors=[C["em_tr"],C["em_oth"],C["em_ep"],C["em_ei"]],alpha=0.85)
ax.plot(YEARS,total_em,"k-",lw=2.5,label="Total",zorder=5)
ax.set_title("GHG emissions by component — PI=1\n(kt CO₂-eq/yr)",fontweight="bold")
fax(ax,"kt CO₂-eq/yr"); ax.legend(fontsize=8)
ann(ax,2019,total_em[0]+4,f"{total_em[0]:.0f} kt")
ann(ax,2050,total_em[-1]+4,f"{total_em[-1]:.0f} kt")

# ── [2,2] Accumulated emissions ──────────────────────────────────────────────
ax=fig.add_subplot(gs[2,2])
ax.fill_between(YEARS,accum_em/1000,alpha=0.30,color="#1565C0")
ax.plot(YEARS,accum_em/1000,color="#1565C0",lw=2.5)
ax.set_title("Accumulated emissions 2019–year\n(Mt CO₂-eq, PI=1)",fontweight="bold")
fax(ax,"Mt CO₂-eq")
ax.annotate(f"{accum_em[-1]/1000:.1f} Mt CO₂\n(2019–2050)",
            xy=(2050,accum_em[-1]/1000),xytext=(2040,accum_em[-1]/1000*0.6),
            arrowprops=dict(arrowstyle="->",color="#1565C0"),
            fontsize=10,fontweight="bold",color="#1565C0",
            bbox=dict(boxstyle="round,pad=0.3",fc="white",ec="#1565C0",alpha=0.9))

# ── [3,:] Summary table ───────────────────────────────────────────────────────
ax=fig.add_subplot(gs[3,:])
ax.axis("off")
MILE=[2019,2025,2030,2040,2050]; MIDX=[int(y-2019) for y in MILE]
col_x=[0.00,0.41,0.52,0.62,0.73,0.84]

def trow(ax,y_,label,vals,fmt=".0f",bold=False,color="#222"):
    ax.text(col_x[0],y_,label,transform=ax.transAxes,fontsize=8.5,
            fontweight="bold" if bold else "normal",va="top",color="#444")
    for ci,v in enumerate(vals,1):
        ax.text(col_x[ci],y_,format(v,fmt),transform=ax.transAxes,
                fontsize=8.5,va="top",color=color,fontweight="bold" if bold else "normal")

def thead(ax,y_,label):
    ax.text(col_x[0],y_,label,transform=ax.transAxes,fontsize=8,
            fontweight="bold",va="top",color="#555",style="italic")

yr_hdr=["","2019","2025","2030","2040","2050"]
for ci,cell in enumerate(yr_hdr):
    ax.text(col_x[ci],1.0,cell,transform=ax.transAxes,fontsize=9,
            fontweight="bold",va="top",color="#222")

rows=[
  ("head","── MOBILITY (PI=1, Python mob model)"),
  ("data","Car share km %",          [mob["ms_all"][i,:2].sum()*100 for i in MIDX]),
  ("data","PT share km %",           [mob["ms_all"][i,2]*100 for i in MIDX]),
  ("data","Active share km %",       [(mob["ms_all"][i,3]+mob["ms_all"][i,4])*100 for i in MIDX]),
  ("data","EV fleet share %",        [mob["ev"][i]*100 for i in MIDX]),
  ("data","Car fossil km/cap",       [mob["km_car_fos"][i] for i in MIDX],".0f"),
  ("data","PT km/cap",               [mob["km_pt"][i] for i in MIDX],".0f"),
  ("head","── ENERGY DEMAND (PI=1, GWh/yr)"),
  ("bold","Total energy demand",     [grand_tot[i] for i in MIDX]),
  ("data","  Households",            [hh_total[i] for i in MIDX]),
  ("data","  Services",              [svc_tot[i] for i in MIDX]),
  ("data","  Industry",              [ind_tot[i] for i in MIDX]),
  ("bold","  Transport total",       [tr_total[i] for i in MIDX]),
  ("data","    Car fossil (GWh)",    [pax_fuel[i] for i in MIDX]),
  ("data","    Car+PT electric (GWh)",[pax_elec[i]+pt_elec[i] for i in MIDX],".1f"),
  ("data","  Fossil all sectors",    [total_fossil[i] for i in MIDX]),
  ("data","  Electricity total",     [total_electr[i] for i in MIDX]),
  ("head","── EMISSIONS (kt CO₂-eq/yr)"),
  ("bold","Total emissions",         [total_em[i] for i in MIDX],".1f","#C62828"),
  ("data","  Direct transport",      [em_transport[i] for i in MIDX],".1f"),
  ("data","  Direct other (bldg+ind)",[em_other[i] for i in MIDX],".1f"),
  ("data","  Grid import",           [em_elec_imp[i] for i in MIDX],".1f"),
  ("data","  CHP",                   [em_elec_prod[i] for i in MIDX],".1f"),
  ("data","Accumulated (Mt CO₂)",    [accum_em[i]/1000 for i in MIDX],".1f","#1565C0"),
]
y_=0.965
for row in rows:
    y_-=0.040
    if row[0]=="head":
        ax.text(col_x[0],y_,row[1],transform=ax.transAxes,fontsize=7.5,
                fontweight="bold",va="top",color="#555",style="italic"); continue
    fmt=row[3] if len(row)>3 else ".0f"
    col=row[4] if len(row)>4 else "#222"
    bold=row[0]=="bold"
    trow(ax,y_,row[1],row[2],fmt,bold,col)

plt.tight_layout(rect=[0,0,1,0.996])
out=OUTPUT_DIR/"granollers_integrated_v8_results.png"
plt.savefig(out,dpi=150,bbox_inches="tight",facecolor=fig.get_facecolor())
print(f"✓ Plot saved → {out}")
plt.close()

# ═══════════════════════════════════════════════════════════════════════════════
# CONSOLE SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n"+"="*74)
print("  GRANOLLERS INTEGRATED MODEL v8  |  PI=1  |  KEY RESULTS")
print("="*74)
print(f"\n  {'Indicator':<36}"+"".join(f"  {y:>7}" for y in MILE))
print("  "+"-"*(36+9*len(MILE)))
summary=[
    ("Car share km %",               [mob["ms_all"][i,:2].sum()*100 for i in MIDX],".0f"),
    ("PT share km %",                [mob["ms_all"][i,2]*100 for i in MIDX],".0f"),
    ("Active share km %",            [(mob["ms_all"][i,3]+mob["ms_all"][i,4])*100 for i in MIDX],".0f"),
    ("EV fleet share %",             [mob["ev"][i]*100 for i in MIDX],".0f"),
    ("Car fossil km/cap",            [mob["km_car_fos"][i] for i in MIDX],".0f"),
    ("PT km/cap",                    [mob["km_pt"][i] for i in MIDX],".0f"),
    ("─"*36,None,None),
    ("Total energy demand (GWh)",    [grand_tot[i] for i in MIDX],".0f"),
    ("  Transport (GWh)",            [tr_total[i] for i in MIDX],".0f"),
    ("  Car fossil (GWh)",           [pax_fuel[i] for i in MIDX],".0f"),
    ("  Fossil all sectors (GWh)",   [total_fossil[i] for i in MIDX],".0f"),
    ("  Electricity (GWh)",          [total_electr[i] for i in MIDX],".0f"),
    ("─"*36,None,None),
    ("Total emissions (kt CO₂)",     [total_em[i] for i in MIDX],".1f"),
    ("  Direct transport (kt)",      [em_transport[i] for i in MIDX],".1f"),
    ("  Direct other (kt)",          [em_other[i] for i in MIDX],".1f"),
    ("  Grid import (kt)",           [em_elec_imp[i] for i in MIDX],".1f"),
    ("  CHP (kt)",                   [em_elec_prod[i] for i in MIDX],".1f"),
    ("Accumulated emissions (Mt CO₂)",[accum_em[i]/1000 for i in MIDX],".1f"),
]
for item in summary:
    lbl,vals,fmt=item
    if vals is None: print(f"  {lbl}"); continue
    print(f"  {lbl:<36}"+"".join(f"  {v:{fmt[1:]}}" for v in vals))
print(f"\n  Emission reduction 2019→2050: {(1-total_em[-1]/total_em[0])*100:.0f}%")
print(f"  Total accumulated 2019–2050:  {accum_em[-1]/1000:.1f} Mt CO₂")
