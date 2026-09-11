#!/usr/bin/env bash
# ./build.sh [double|single|debug] [mode] [delt] [nreg]
#
# Compiles the SHIPPING mp_wsm6.F90 in place (no copy) so the harness can never drift from the
# source WRF builds. Objects go to a mktemp dir; nothing lands in the repo.
#
# module_libmassv.F90 and mp_radar.F90 are NOT in this overlay -- the overlay carries only the
# modified physics_mmm files and WRF gets the rest from the release tarball. Same convention as
# check_fork_sync.sh: $WVT_MMM, defaulting to the sibling checkout.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
phys="$here/../../phys/physics_mmm"
mmm="${WVT_MMM:-$HOME/git/wrf-repos/MMM-physics}"
[[ -f "$mmm/module_libmassv.F90" && -f "$mmm/mp_radar.F90" ]] || {
    echo "need module_libmassv.F90 and mp_radar.F90 from MMM-physics." >&2
    echo "set WVT_MMM=<path to the MMM-physics checkout> (tried: $mmm)" >&2
    exit 2
}
prec="${1:-double}"
flags=(-O2 -ffree-line-length-none -fbacktrace -cpp -DWVT_CLAMP_DIAG)
case "$prec" in
  single) flags+=(-DSINGLE_PREC) ;;
  # ⚠ WSM6 does dozens of P/X*tr_X divisions each guarded by its own `if (X.gt.0.)`. An unguarded
  # one is exactly this bug class, and -ffpe-trap=zero finds it in a single run. A review round
  # found a divide-by-zero mutant passing the identity gate silently, because gfortran's
  # max(NaN,0.) returns 0 -- so the trap is not optional for mutation work.
  # underflow/denormal are deliberately excluded: the inlined qsat underflows legitimately.
  debug)  flags=(-O0 -g -fcheck=bounds,pointer -ffpe-trap=invalid,zero,overflow -finit-real=snan
                 -ffree-line-length-none -fbacktrace -cpp -DWVT_CLAMP_DIAG) ;;
esac
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
cd "$work"
gfortran "${flags[@]}" -c "$here/../single_column/ccpp_kind_types.F90"   # one stub, shared
gfortran "${flags[@]}" -c "$mmm/module_libmassv.F90"
gfortran "${flags[@]}" -c "$mmm/mp_radar.F90"
gfortran "${flags[@]}" -c "$phys/mp_wsm6.F90"
gfortran "${flags[@]}" -c "$here/mp_wsm6_sc.F90"
gfortran "${flags[@]}" -o mp_wsm6_sc ./*.o
echo "--- $prec precision ---"
# ~30 automatic arrays in mp_wsm6_run are dimensioned on num_wvt_regions UNCONDITIONALLY; at
# nreg=12 that is several MB of stack. An overflow here looks like a segfault at an arbitrary
# line and reads as a physics bug.
ulimit -s 65536 2>/dev/null || true
rc=0
./mp_wsm6_sc "${2:-}" "${3:-}" "${4:-}" || rc=$?
exit $rc
