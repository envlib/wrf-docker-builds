#!/usr/bin/env python3
"""Generate the WVT per-region total-humidity moisture-flux (tr_thum_{u,v}_phy_dt)
Registry + Fortran fragments for source regions 2..MAX.

Background
----------
`calc_moist_fluxes` accumulates thum = sum over a CONTIGUOUS species range of a moisture
array, times wind times dt, into thum_u/v_phy_dt (a diagnostic vapour-transport flux). The
single-region WVT scheme passes the WHOLE `tracer` array -> tr_thum is the ALL-regions-combined
flux. Per-region: region n sums only its 6 contiguous species (P_QV_TR+(n-1)*6 .. +5) into its
own named field. Region 1 keeps the ORIGINAL unsuffixed names (restricted to region-1's range;
for N=1 that IS the whole tracer array -> bit-identical). Regions 2..MAX add suffixed members
tr_thum_{u,v}_phy_dt_02..NN, declared identically (ikj misc 1 - rh).

Wiring: all per-region calls live in `phy_prep` (module_big_step_utilities_em.F) next to the
base call; calc_moist_fluxes gains an `ispe_start` arg (loop ispe=ispe_start..n_moist).
first_rk_step_part1 threads grid%tr_thum_*_0n into phy_prep.

Usage: python3 gen_wvt_thum.py [MAX]  (default 8). Keep MAX in sync with the other generators.
"""
import sys

COMP = ['u', 'v']  # x- and y-flux components


def fld(c, n):
    return f"tr_thum_{c}_phy_dt_{n:02d}"


def main():
    mx = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    regions = range(2, mx + 1)

    print("==== SECTION 1: registry.moisttracers (after the tr_thum_v_phy_dt line) ====")
    for n in regions:
        for c in COMP:
            name = f"tr_thum_{c}_phy_dt_{n:02d}"
            ax = 'x' if c == 'u' else 'y'
            print(f'state   real  {name:20s} ikj      misc        1         -      rh       '
                  f'"{name}"   "tracer total humidity * {ax}-wind component * dt, region {n:02d}"   "kg kg-1 m"')
    print()

    print("==== SECTION 2: phy_prep signature args (after 'tr_thum_u_phy_dt, tr_thum_v_phy_dt,') ====")
    for n in regions:
        names = ", ".join(fld(c, n) for c in COMP)
        print(f"                         {names}, & ! wvt 1d/thum region {n:02d}")
    print()

    print("==== SECTION 3: phy_prep declarations (after the tr_thum_u_phy_dt/tr_thum_v_phy_dt decl) ====")
    for n in regions:
        names = ", ".join(fld(c, n) for c in COMP)
        print(f"   REAL, DIMENSION( ims:ime, kms:kme , jms:jme ),INTENT(INOUT) :: {names} ! wvt")
    print()

    print("==== SECTION 4: phy_prep tracer-flux block (REPLACES the existing single tracer calc_moist_fluxes call) ====")
    print("! wvt: per-region tracer total-humidity moisture fluxes (region 1 = unsuffixed; 2..N = _0n).")
    print("! Each region sums only its 6 contiguous species [P_QV_TR+(n-1)*6 .. +5]. For N=1 region 1")
    print("! spans the whole tracer array -> bit-identical to the original all-species call.")
    print(" IF (p_qv_tr .ge. PARAM_FIRST_SCALAR) THEN")
    print("   CALL calc_moist_fluxes(   dt, itimestep, tracer, p_qv_tr+5, p_qv_tr,     &")
    print("                             tr_thum_u_phy_dt, tr_thum_v_phy_dt,     &")
    print("                             t_phy, p_phy, u_phy, v_phy,       &")
    print("                             ids, ide, jds, jde, kds, kde,     &")
    print("                             ims, ime, jms, jme, kms, kme,     &")
    print("                             its, ite, jts, jte, kts, kte  )")
    print(" ENDIF")
    for n in regions:
        base = (n - 1) * 6
        print(f" IF (config_flags%num_wvt_regions .ge. {n}) THEN")
        print(f"   CALL calc_moist_fluxes(   dt, itimestep, tracer, p_qv_tr+{base + 5}, p_qv_tr+{base},     &")
        print(f"                             {fld('u', n)}, {fld('v', n)},     &")
        print(f"                             t_phy, p_phy, u_phy, v_phy,       &")
        print(f"                             ids, ide, jds, jde, kds, kde,     &")
        print(f"                             ims, ime, jms, jme, kms, kme,     &")
        print(f"                             its, ite, jts, jte, kts, kte  )")
        print(f" ENDIF")
    print()

    print("==== SECTION 5: first_rk_step_part1.F phy_prep call actuals (after grid%tr_thum_u_phy_dt, grid%tr_thum_v_phy_dt,) ====")
    for n in regions:
        names = ", ".join(f"grid%{fld(c, n)}" for c in COMP)
        print(f"                        {names},    & ! wvt 1d/thum region {n:02d}")
    print()


if __name__ == "__main__":
    sys.exit(main() or 0)
