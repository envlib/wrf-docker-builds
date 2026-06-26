#!/usr/bin/env bash
# Run real.exe + wrf.exe for a given num_wvt_regions and report tracer activation.
set -uo pipefail

run_one() {
    local N="$1"
    local d="/runN${N}"
    echo "##################### num_wvt_regions=${N} #####################"
    mkdir -p "$d" && cd "$d" || return 1
    ln -sf /WRF/run/* . 2>/dev/null
    rm -f namelist.input
    cp "/work/namelist.input.n${N}" namelist.input
    cp /work/trmask_d01 .
    ln -sf /test_data/met_em.d01.* .
    ulimit -s unlimited

    echo "--- real.exe ---"
    mpirun -n 4 ./real.exe > real.log 2>&1
    if grep -q "SUCCESS COMPLETE REAL_EM INIT" rsl.out.0000 2>/dev/null; then
        echo "REAL: OK"
    else
        echo "REAL: FAIL"; tail -12 rsl.error.0000 2>/dev/null; return 1
    fi

    echo "--- num_tracer reported by WRF (rsl) ---"
    grep -iE 'num_tracer|p_qv_tr' rsl.out.0000 2>/dev/null | head -4 || true

    echo "--- wrf.exe ---"
    mpirun -n 4 ./wrf.exe > wrf.log 2>&1
    if grep -q "SUCCESS COMPLETE WRF" rsl.out.0000 2>/dev/null; then
        echo "WRF: OK"
    else
        echo "WRF: FAIL"; tail -15 rsl.error.0000 2>/dev/null; return 1
    fi

    local last
    last=$(ls -1 wrfout_d01_* 2>/dev/null | tail -1)
    echo "--- wrfout: $last ---"
    echo -n "tracer vars present: "
    ncdump -h "$last" | grep -oE '\bq[vcrisg]_tr(_[0-9]+)?\b' | sort -u | tr '\n' ' '; echo
    echo -n "  count: "; ncdump -h "$last" | grep -oE '\bq[vcrisg]_tr(_[0-9]+)?\b' | sort -u | wc -l
    echo "--- region-1 vs region-2 max(qv_tr) (region 2 should be 0 in Phase 0) ---"
    ncwa -O -y max -v qv_tr "$last" /tmp/m1.nc 2>/dev/null && echo -n "  max(qv_tr)    = " && ncks -H -s '%g\n' -v qv_tr /tmp/m1.nc 2>/dev/null | tail -1
    if ncdump -h "$last" | grep -q '\bqv_tr_02\b'; then
        ncwa -O -y max -v qv_tr_02 "$last" /tmp/m2.nc 2>/dev/null && echo -n "  max(qv_tr_02) = " && ncks -H -s '%g\n' -v qv_tr_02 /tmp/m2.nc 2>/dev/null | tail -1
    fi
    echo "--- TR_RAINNC max (region-1 tagged precip) ---"
    ncwa -O -y max -v TR_RAINNC "$last" /tmp/mr.nc 2>/dev/null && echo -n "  max(TR_RAINNC) = " && ncks -H -s '%g\n' -v TR_RAINNC /tmp/mr.nc 2>/dev/null | tail -1
    echo
}

run_one 2
run_one 1
echo "ALL DONE"
