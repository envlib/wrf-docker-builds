#!/usr/bin/env bash
# Gate 0: run the 8-region configuration so two images can be compared bit-for-bit.
# The namelist deliberately omits num_wvt_bdy_regions -- the pre-change binary does not know
# that variable, and the post-change binary defaults it to 0, which IS the boundary_faces=[]
# condition. Same namelist, same mask, same ranks in both.
#
# The baseline mask /work/base/trmask_d01 is produced on the host by the SAME generator as the
# 12-region mask, pointed at this namelist:
#     WVT_TEST_NAMELIST=namelist.input.n8 WVT_TEST_WORK=<work>/base python make_trmask_n12.py
# (namelist.input.n8 omits num_wvt_bdy_regions, which the generator reads as 0 -> no shells;
# the eight source strips come out byte-identical to the 12-region mask's, which is what gate 0
# asserts: the two runs differ ONLY by the presence of the shells.)
set -uo pipefail
OUT="${GATE0_OUT:?set GATE0_OUT}"
mkdir -p "/work/$OUT"
d=/rung0
mkdir -p "$d" && cd "$d" || exit 1
ln -sf /WRF/run/* . 2>/dev/null
rm -f namelist.input trmask_d01
cp /work/namelist.input.n8 namelist.input
cp /work/base/trmask_d01 trmask_d01
ln -sf /test_data/met_em.d01.* .
ulimit -s unlimited
mpirun -n 4 ./real.exe > real.log 2>&1
grep -q "SUCCESS COMPLETE REAL_EM INIT" rsl.out.0000 2>/dev/null || { echo "REAL FAIL"; tail -20 rsl.error.0000; exit 1; }
mpirun -n 4 ./wrf.exe > wrf.log 2>&1
grep -q "SUCCESS COMPLETE WRF" rsl.out.0000 2>/dev/null || { echo "WRF FAIL"; tail -25 rsl.error.0000; exit 1; }
for f in wrfout_d01_*; do cp "$f" "/work/$OUT/$f"; done
echo "OK: $(ls -1 wrfout_d01_* | wc -l) file(s) -> /work/$OUT"
