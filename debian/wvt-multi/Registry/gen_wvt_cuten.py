#!/usr/bin/env python3
"""Generate the WVT convective-tracer-tendency (RTRQ{V,C,I}CUTEN) Registry + Fortran
fragments for source regions 2..MAX (Stage 1d-b, Option B: named members).

Background
----------
cu_ntiedtke transports tagged moisture convectively via coupled tracer tendencies
RTRQ{V,C,I}CUTEN: set once per cumulus step (uncoupled mixing-ratio tendency), coupled
(x mu) before the RK step, added to tracer_tendf, and decoupled (/ mu) afterwards so they
persist between cumulus steps. Region 1 keeps the ORIGINAL unsuffixed names (untouched ->
N=1 stays bit-identical). Regions 2..MAX add suffixed members RTRQVCUTEN_02..NN etc.,
declared IDENTICALLY (ikj misc 1 - r) so they inherit region-1's allocation / default-init
/ restart / IO behaviour with no extra init code. cu_ntiedtke transports only qv,qc,qi
(matches 1d-a), so only those 3 species get named members.

Lifecycle wiring (where grid is in scope -> handled in-place, no signature threading):
  SET      cu_ntiedtke_driver  (per-region n_wvt>=2 select store)   <- needs dummies (S2/S3/S4)
                                 + cumulus_driver passes grid%rtrq*cuten_0n (S5)
  COUPLE   first_rk_step_part2  after calculate_phy_tend  (S6)   mirrors module_em couple (x (c1h*mut+c2h))
  APPLY    first_rk_step_part2  after update_phy_ten      (S7)   add_a2a into tracer_tend(P_*_TR+(n-1)*6)
  DECOUPLE solve_em             after phy_prep_part2       (S8)   mirrors phy_prep_part2 (/ (c1h*muts+c2h))

Usage:  python3 gen_wvt_cuten.py [MAX] > fragments.txt   (default MAX=8)
Paste each labelled SECTION into the indicated file. Keep MAX in sync with
gen_wvt_tracers.py / MAX_WVT_REGIONS in module_check_a_mundo.F.
"""
import sys

# cu_ntiedtke transports qv,qc,qi. (suffix letter, registry Q tag, block 4th-index offset, P_* index)
SPECIES = [("v", "Q_V", 1, "P_QV_TR"),
           ("c", "Q_C", 2, "P_QC_TR"),
           ("i", "Q_I", 4, "P_QI_TR")]


def fld(sp, n):
    return f"rtrq{sp}cuten_{n:02d}"


def main():
    mx = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    regions = range(2, mx + 1)

    print("==== SECTION 1: registry.moisttracers (paste after the RTRQICUTEN line) ====")
    for n in regions:
        for sp, q, _off, _p in SPECIES:
            name = f"RTRQ{sp.upper()}CUTEN_{n:02d}"
            print(f'state    real  {name:17s} ikj      misc        1         -      r        '
                  f'"{name}"     "COUPLED TRACER {q} TENDENCY DUE TO CUMULUS SCHEME, region {n:02d}"   "Pa kg kg-1 s-1"')
    print()

    print("==== SECTION 2: module_cu_ntiedtke.F driver arg list (after ',rtrqvcuten,rtrqccuten,rtrqicuten') ====")
    for n in regions:
        names = ",".join(fld(sp, n) for sp, *_ in SPECIES)
        print(f"                ,{names}  & ! wvt 1d-b region {n:02d}")
    print()

    print("==== SECTION 3: module_cu_ntiedtke.F declarations (after the rtrqicuten declaration) ====")
    print(" real(kind=kind_phys),intent(inout),dimension(ims:ime,kms:kme,jms:jme),optional:: & ! wvt 1d-b: regions 2..N")
    decls = ["    " + ", ".join(fld(sp, n) for sp, *_ in SPECIES) for n in regions]
    print(", &\n".join(decls))
    print()

    print("==== SECTION 4: module_cu_ntiedtke.F SET block (after the 'endif' closing the n_wvt==1 block) ====")
    print("!--- wvt 1d-b: regions 2..N convective tracer tendency store (region 1 handled above on n_wvt==1). ! wvt")
    print("    if (l_do_tracers .and. n_wvt >= 2) then                                                ! wvt")
    print("       select case (n_wvt)                                                                 ! wvt")
    for n in regions:
        print(f"       case ({n})                                                                              ! wvt")
        print(f"          if (present({fld('v', n)})) then                                                    ! wvt")
        print("             do k = kts,kte                                                                   ! wvt")
        print("                do i = its,ite                                                                ! wvt")
        for sp, _q, off, _p in SPECIES:
            print(f"                   {fld(sp, n)}(i,k,j) = (tr_q{sp}_hv(i,kte-k+kts) "
                  f"- tr_block(i,k,j,ib_wvt+{off}))/(dt*stepcu)  ! wvt")
        print("                enddo                                                                         ! wvt")
        print("             enddo                                                                            ! wvt")
        print("          endif                                                                               ! wvt")
    print("       end select                                                                          ! wvt")
    print("    endif                                                                                   ! wvt")
    print()

    print("==== SECTION 5: module_cumulus_driver.F cu_ntiedtke_driver call (after ',rtrqicuten=rtrqicuten') ====")
    for n in regions:
        parts = ",".join(f"{fld(sp, n)}=grid%{fld(sp, n)}" for sp, *_ in SPECIES)
        print(f"               ,{parts} & ! wvt 1d-b region {n:02d}")
    print()

    print("==== SECTION 6: module_first_rk_step_part2.F COUPLE block (after BENCH_END(cal_phy_tend)) ====")
    print("! wvt 1d-b: couple convective tracer tendencies for regions 2..N (mirrors module_em calculate_phy_tend).")
    print("      IF (P_QV_TR .ge. PARAM_FIRST_SCALAR) THEN")
    for n in regions:
        print(f"         IF (config_flags%num_wvt_regions >= {n}) THEN")
        print("            DO j = jps, MIN(jpe,jde-1)")
        print("            DO k = kps, MIN(kpe,kde-1)")
        print("            DO i = ips, MIN(ipe,ide-1)")
        for sp, *_ in SPECIES:
            print(f"               grid%{fld(sp, n)}(i,k,j) = (grid%c1h(k)*grid%mut(i,j)+grid%c2h(k))*grid%{fld(sp, n)}(i,k,j)")
        print("            ENDDO")
        print("            ENDDO")
        print("            ENDDO")
        print("         ENDIF")
    print("      ENDIF")
    print()

    print("==== SECTION 7: module_first_rk_step_part2.F APPLY block (after BENCH_END(update_phy_ten_tim)) ====")
    print("! wvt 1d-b: apply convective tracer tendencies for regions 2..N (mirrors phy_cu_ten NTIEDTKE add_a2a).")
    print("      IF (config_flags%cu_physics == NTIEDTKESCHEME .OR. config_flags%cu_physics == TIEDTKESCHEME) THEN")
    for n in regions:
        off = (n - 1) * 6
        print(f"         IF (config_flags%num_wvt_regions >= {n}) THEN")
        for sp, _q, _o, pidx in SPECIES:
            print(f"            IF ({pidx} .ge. PARAM_FIRST_SCALAR) "
                  f"CALL add_a2a(tracer_tend(ims,kms,jms,{pidx}+{off}),grid%{fld(sp, n)}, &")
            print("                 config_flags, ids,ide,jds,jde,kds,kde, ims,ime,jms,jme,kms,kme, ips,ipe,jps,jpe,kps,kpe)")
        print("         ENDIF")
    print("      ENDIF")
    print()

    print("==== SECTION 8: solve_em.F DECOUPLE block (after the phy_prep_part2 tile loop ENDDO) ====")
    print("! wvt 1d-b: decouple convective tracer tendencies for regions 2..N (mirrors phy_prep_part2 region 1).")
    print("      IF (P_QV_TR .ge. PARAM_FIRST_SCALAR) THEN")
    for n in regions:
        print(f"         IF (config_flags%num_wvt_regions >= {n}) THEN")
        print("            DO j = jps, MIN(jpe,jde-1)")
        print("            DO k = kps, MIN(kpe,kde-1)")
        print("            DO i = ips, MIN(ipe,ide-1)")
        for sp, *_ in SPECIES:
            print(f"               grid%{fld(sp, n)}(i,k,j) = grid%{fld(sp, n)}(i,k,j)/(grid%c1h(k)*grid%muts(i,j)+grid%c2h(k))")
        print("            ENDDO")
        print("            ENDDO")
        print("            ENDDO")
        print("         ENDIF")
    print("      ENDIF")
    print()


if __name__ == "__main__":
    sys.exit(main() or 0)
