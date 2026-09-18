#!/usr/bin/env python3
"""Generate the WVT moisture-tracer Registry.EM entries for N source regions.

The single-region WVT scheme declares 6 tagged moisture species (qv_tr..qg_tr) in WRF's
4D ``tracer`` array. For multi-region tagging we need 6 species x MAX_WVT_REGIONS members.

Region 1 keeps the ORIGINAL unsuffixed names (qv_tr..qg_tr) so the existing single-region
physics and the generated P_QV_TR.. indices are unchanged -- N=1 stays bit-identical.
Regions 2..MAX add suffixed members qv_tr_02..qg_tr_NN, declared region-contiguously
(all 6 species of region 2, then region 3, ...) so the per-region index map is clean.

Usage:
    python3 gen_wvt_tracers.py [MAX]      # default 8

Paste the printed ``state`` lines into Registry.EM directly after the qg_tr line, and
replace the existing ``package tracer_moist`` line with the printed package block.

Activation scales with num_wvt_regions so a single-region run only advects 6 tracers:
region 1 stays gated on ``tracer_opt==4`` (unchanged -> default num_wvt_regions=1 activates
exactly the original 6 members, fully backward compatible), and regions 2..MAX are activated
by cumulative ``num_wvt_regions==N`` packages (package N lists regions 2..N). Only the package
matching num_wvt_regions is active, so exactly 6*num_wvt_regions members are active at runtime.
(module_check_a_mundo.F enforces 1<=num_wvt_regions<=MAX under tracer_opt==4, and forbids
num_wvt_regions>1 without tracer_opt==4 so the active tracer block stays contiguous.)
Keep MAX in sync with the MAX_WVT_REGIONS bound in module_check_a_mundo.F.
"""
import sys

# (name, human description) -- order defines the per-region species order.
SPECIES = [
    ("qv_tr", "water vapor"),
    ("qc_tr", "cloud water"),
    ("qr_tr", "rain water"),
    ("qi_tr", "ice"),
    ("qs_tr", "snow"),
    ("qg_tr", "graupel"),
]
DIMS = "ikjftb"
# Every WVT state field outside the per-region _0N families and the deferred region-1
# RTRQ*CUTEN. Names as declared (the registry lower-cases them anyway); check_generators.sh
# asserts each is declared and that no WVT state field is left unpackaged.
STATE_ON_TRACER_OPT = [
    "RTRQVBLTEN", "RTRQCBLTEN", "RTRQIBLTEN", "tr_thum_u_phy_dt", "tr_thum_v_phy_dt",
    "TRMASK3D", "TRMASK3D2", "TRQFX",
    "TR_CAPCRE", "TR_CAPDES", "I_TR_CAPCRE", "I_TR_CAPDES",
    "TR_MPCRE", "TR_MPDES", "TR_MPRED", "I_TR_MPCRE", "I_TR_MPDES", "I_TR_MPRED",
    "TRMASK", "TR_RAINNC", "TR_SNOWNC", "TR_GRAUPELNC", "TR_RAINC", "TR_PRATEC",
    "PWAT_TR", "VIMF_TR_U", "VIMF_TR_V",
    # NOT here: I_TR_RAINNC, I_TR_RAINC. The original port listed them in the STOCK package
    # `bucketropt bucketr_opt==1` (Registry.EM_COMMON) beside I_RAINC/I_RAINNC, and WRF ORs
    # packages, so listing them here too would make them active with tracers OFF whenever
    # bucket_mm > 0 (measured: written in the tracer-off bucket variant). They stay governed by
    # bucketr_opt alone, exactly as before this change.
]
IOFLAGS = "irh06usdf=(bdy_interp:dt)"  # identical to the region-1 (qv_tr..) declarations


def member(species: str, region: int) -> str:
    """Region 1 is unsuffixed (the original names); regions >=2 get a _NN suffix."""
    return species if region == 1 else f"{species}_{region:02d}"


def main() -> int:
    mx = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    for n in range(2, mx + 1):
        print(f"# wvt region {n:02d}")
        for sp, desc in SPECIES:
            name = member(sp, n)
            print(
                f'state   real    {name:9s} {DIMS}  tracer        1         -     {IOFLAGS}'
                f'    "{name}"   "tracer for {desc} from ET, region {n:02d} (mix. ratio)"   "Kg Kg-1"'
            )
        print()
    # Region 1: gated on tracer_opt==4 (unchanged activation -> backward compatible).
    r1 = ",".join(member(sp, 1) for sp, _ in SPECIES)
    print(f"package   tracer_moist  tracer_opt==4       -             tracer:{r1}")
    # Regions 2..N: activated by num_wvt_regions==N (cumulative; package N lists regions 2..N).
    for N in range(2, mx + 1):
        mems = ",".join(member(sp, n) for n in range(2, N + 1) for sp, _ in SPECIES)
        print(f"package   wvt_nr{N}        num_wvt_regions=={N}       -             tracer:{mems}")
    # 2026-09-18: the region-1 and region-dimensioned WVT state is packaged on tracer_opt==4 so a
    # tracer-off run neither allocates nor writes it. Per-region _0N members have their own
    # packages (gen_wvt_cuten.py SECTION 9, gen_wvt_thum.py SECTION 6). DEFERRED (Stage 2b):
    # region-1 RTRQ{V,C,R,I,S}CUTEN -- see Registry.EM's comment block.
    print("#wvt: region-1 / region-dimensioned WVT state, allocated + written only with tracer_opt=4.")
    print("package   wvt_state      tracer_opt==4       -             state:" + ",".join(STATE_ON_TRACER_OPT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
