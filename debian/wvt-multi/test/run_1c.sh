#!/usr/bin/env bash
# Stage 1c validation: N=2 (west+east) and N=1 (full ocean) WSM6 tracer microphysics.
set -uo pipefail
mkdir -p /work/out

run_one() {
    local N="$1"; local TRMASK="$2"
    local d="/runN${N}c"
    echo "##################### num_wvt_regions=${N}  trmask=${TRMASK} #####################"
    mkdir -p "$d" && cd "$d" || return 1
    ln -sf /WRF/run/* . 2>/dev/null
    rm -f namelist.input trmask_d01
    cp "/work/namelist.input.n${N}" namelist.input
    cp "/work/${TRMASK}" trmask_d01
    ln -sf /test_data/met_em.d01.* .
    ulimit -s unlimited
    echo "--- real.exe ---"
    mpirun -n 4 ./real.exe > real.log 2>&1
    grep -q "SUCCESS COMPLETE REAL_EM INIT" rsl.out.0000 2>/dev/null && echo "REAL OK" || { echo "REAL FAIL"; tail -15 rsl.error.0000 2>/dev/null; return 1; }
    echo "--- wrf.exe ---"
    mpirun -n 4 ./wrf.exe > wrf.log 2>&1
    grep -q "SUCCESS COMPLETE WRF" rsl.out.0000 2>/dev/null && echo "WRF OK" || { echo "WRF FAIL"; tail -20 rsl.error.0000 2>/dev/null; return 1; }
    local last; last=$(ls -1 wrfout_d01_* 2>/dev/null | tail -1)
    cp "$last" "/work/out/wrfout_1c_n${N}.nc"
    echo "N=${N} -> /work/out/wrfout_1c_n${N}.nc"
    echo
}

run_one 2 trmask_d01       || exit 1
run_one 1 trmask_1reg_d01  || exit 1
echo "ALL DONE"
