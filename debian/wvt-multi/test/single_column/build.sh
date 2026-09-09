#!/usr/bin/env bash
# Build and run the single-column identity harness.
#   ./build.sh          double precision (default)
#   ./build.sh single   single precision  (kind_phys = real4, as some WRF builds use)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
phys="$here/../../phys/physics_mmm"
prec="${1:-double}"
flags=(-O2 -ffree-line-length-none -fbacktrace -cpp -DWVT_CLAMP_DIAG)
[[ "$prec" == "single" ]] && flags+=(-cpp -DSINGLE_PREC)
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
cd "$work"
gfortran "${flags[@]}" -c "$here/ccpp_kind_types.F90"
gfortran "${flags[@]}" -c "$phys/cu_ntiedtke.F90"
gfortran "${flags[@]}" -c "$here/sc_driver.F90"
gfortran "${flags[@]}" -o sc_driver *.o
echo "--- $prec precision ---"
rc=0
./sc_driver "${2:-}" "${3:-}" || rc=$?
[[ -f v0_export.txt ]] && cp v0_export.txt "$here/"
exit $rc
