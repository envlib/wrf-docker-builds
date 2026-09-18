#!/usr/bin/env bash
# Run the packaging gates' simulations inside a builder image. For each CONFIG: real.exe +
# wrf.exe on 4 ranks with /work/namelist.input.<config> (restart_interval forced to 180 so one
# wrfrst is written at the end of the 3 h run) and the matching mask, then copy every wrfout,
# wrfrst and rsl.out.0000 to /work/out_<TAG>/<config>/. Configs whose name starts with `bad_`
# are EXPECTED to fail in real.exe with a check_a_mundo message; their rsl.error is kept.
#
#   docker run --rm --shm-size=2g -e I_MPI_FABRICS=shm -e TAG=armA -e CONFIGS="n8 n12 n2 n1 notracer" \
#     -v <testdata>:/test_data:ro -v <work>:/work <image> bash /work/run_pkg_gates.sh
set -uo pipefail
TAG="${TAG:?set TAG}"; ulimit -s unlimited; GATE_FAIL=0
for C in ${CONFIGS:-n8 n12 n2 n1 notracer notracer_bucket notracer_kf notracer_ysu bad_3dsource bad_mixed_tracer_opt ok_stock_tracer_opt_2_0}; do
  d=/run_$C; rm -rf $d; mkdir -p $d && cd $d
  ln -sf /WRF/run/* . 2>/dev/null; rm -f namelist.input trmask_d01
  sed 's/restart_interval = 500000/restart_interval = 180/' /work/namelist.input.$C > namelist.input
  case "$C" in
    n8*)  cp /work/trmask_n8  trmask_d01 ;;  n12*) cp /work/trmask_n12 trmask_d01 ;;
    n2*)  cp /work/trmask_n2  trmask_d01 ;;  n1*)  cp /work/trmask_n1  trmask_d01 ;;
    bad_mixed*|ok_stock*) cp /work/trmask_n2 trmask_d01 ;;
  esac
  ln -sf /test_data/met_em.d01.* .
  out=/work/out_$TAG/$C; mkdir -p $out
  mpirun -n 4 ./real.exe > real.log 2>&1
  # Negative tests are SELF-ASSERTING: a bad_* namelist that real.exe accepts is a failure, and
  # so is a refusal for a reason other than the rule under test. ok_* namelists must produce no
  # check_a_mundo error line at all (they may still fail later for want of d02 inputs).
  case "$C" in
    bad_3dsource)          want='tracer2dsource/tracer3dsource/tracer3dsink require tracer_opt=4' ;;
    bad_mixed_tracer_opt)  want='tracer_opt=4 (WVT) must be set on every domain or none' ;;
    *) want='' ;;
  esac
  case "$C" in
    ok_*)
      if grep -q -- '--- ERROR' rsl.error.0000 rsl.out.0000 2>/dev/null; then
        echo "UNEXPECTED_REFUSAL_$C: $(grep -h -m1 -- '--- ERROR' rsl.error.0000 rsl.out.0000 | cut -c1-140)"; GATE_FAIL=1
      else echo "OK_$C: accepted by check_a_mundo"; fi
      cp rsl.error.0000 $out/real.rsl.error.0000 2>/dev/null; cd /; rm -rf $d; continue ;;
    bad_*)
      if grep -q "SUCCESS COMPLETE REAL_EM INIT" rsl.out.0000; then echo "UNEXPECTED_PASS_$C"; GATE_FAIL=1
      elif grep -qF -- "$want" rsl.error.0000; then echo "EXPECTED_FAIL_$C: $want"
      else echo "WRONG_REASON_$C: $(grep -h -m1 -- '--- ERROR' rsl.error.0000 | cut -c1-140)"; GATE_FAIL=1; fi
      cp rsl.error.0000 $out/real.rsl.error.0000 2>/dev/null; cd /; rm -rf $d; continue ;;
  esac
  if ! grep -q "SUCCESS COMPLETE REAL_EM INIT" rsl.out.0000; then
    cp rsl.error.0000 $out/real.rsl.error.0000 2>/dev/null; echo "REAL FAIL $C"; tail -5 rsl.error.0000; GATE_FAIL=1
    cd /; rm -rf $d; continue
  fi
  mpirun -n 4 ./wrf.exe > wrf.log 2>&1
  grep -q "SUCCESS COMPLETE WRF" rsl.out.0000 || { echo "WRF FAIL $C"; tail -5 rsl.error.0000; cp rsl.error.0000 $out/; GATE_FAIL=1; cd /; rm -rf $d; continue; }
  grep 'Timing for main' rsl.out.0000 | awk -v c=${C}_${TAG} '{s+=$(NF-2); n++} END {printf "MAINSUM_%s steps=%d mean=%.3f s\n", c, n, s/n}'
  cp wrfout_d01_* wrfrst_d01_* rsl.out.0000 $out/ 2>/dev/null
  echo "OK_$C: $(ls $out | grep -c wrfout) wrfout, $(ls $out | grep -c wrfrst) wrfrst"
  cd /; rm -rf $d
done
echo "GATES_DONE_$TAG fail=$GATE_FAIL"; exit $GATE_FAIL
