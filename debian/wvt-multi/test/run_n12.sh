#!/usr/bin/env bash
# 12-region lateral-boundary-tag runtime test: 8 ocean sources + 4 face shells.
#
# Runs inside the builder image. Expects /work to hold namelist.input.n12 and trmask_d01
# (both produced on the host by make_trmask_n12.py), and /test_data to hold met_em + geo_em.
# The wrfout is copied to /work/out/ for host-side gate checking -- nothing else in the
# container survives.
set -uo pipefail
mkdir -p /work/out

N=12
d="/runN${N}"
echo "##################### num_wvt_regions=${N} (8 sources + 4 faces) #####################"
mkdir -p "$d" && cd "$d" || exit 1
ln -sf /WRF/run/* . 2>/dev/null
rm -f namelist.input trmask_d01
cp /work/namelist.input.n12 namelist.input
cp /work/trmask_d01 trmask_d01
ln -sf /test_data/met_em.d01.* .
ulimit -s unlimited

echo "--- real.exe ---"
mpirun -n 4 ./real.exe > real.log 2>&1
if grep -q "SUCCESS COMPLETE REAL_EM INIT" rsl.out.0000 2>/dev/null; then
    echo "REAL OK"
else
    echo "REAL FAIL"; tail -25 rsl.error.0000 2>/dev/null; exit 1
fi

# num_tracer should be 6*12 = 72 active members; if the Registry packages did not activate
# for N=12 this is where it shows, before any physics runs.
echo "--- tracer activation reported by WRF ---"
grep -iE 'num_tracer|p_qv_tr' rsl.out.0000 2>/dev/null | head -4 || true

echo "--- wrf.exe ---"
mpirun -n 4 ./wrf.exe > wrf.log 2>&1
if grep -q "SUCCESS COMPLETE WRF" rsl.out.0000 2>/dev/null; then
    echo "WRF OK"
else
    echo "WRF FAIL"; tail -30 rsl.error.0000 2>/dev/null; exit 1
fi

echo "--- tracer members in output ---"
last=$(ls -1 wrfout_d01_* 2>/dev/null | tail -1)
echo -n "  qv_tr members: "
ncdump -h "$last" | grep -oE '\bqv_tr(_[0-9]+)?\b' | sort -u | wc -l

for f in wrfout_d01_*; do cp "$f" "/work/out/$f"; done
echo "copied $(ls -1 wrfout_d01_* | wc -l) wrfout file(s) to /work/out/"
echo "ALL DONE"
