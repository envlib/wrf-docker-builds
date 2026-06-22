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
    return 0


if __name__ == "__main__":
    sys.exit(main())
