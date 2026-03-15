#!/usr/bin/env bash
set -uo pipefail

# Defaults
IMAGE="mullenkamp/wrf-wps-intel-ubuntu:1.0"
GEOG_PATH="$HOME/WPS_GEOG"
TEST_DATA="$HOME/data/wrf/test_data"
CONTAINER="wrf-intel-test-$$"

PASS_COUNT=0
FAIL_COUNT=0

# Parse CLI args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --image)     IMAGE="$2"; shift 2 ;;
        --geog-path) GEOG_PATH="$2"; shift 2 ;;
        --test-data) TEST_DATA="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 [--image NAME] [--geog-path PATH] [--test-data PATH]"
            exit 0 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# Colors
pass() { echo -e "  \033[32m[PASS]\033[0m $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo -e "  \033[31m[FAIL]\033[0m $1 — $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); }
section() { echo -e "\n\033[1m=== $1 ===\033[0m"; }

run_in() { docker exec "$CONTAINER" bash -c "$1" 2>&1; }

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Start test container
echo "Image: $IMAGE"
echo "Starting test container..."
docker run -d --name "$CONTAINER" --shm-size=1g \
    -e I_MPI_FABRICS=shm \
    -v "$GEOG_PATH":/WPS_GEOG:ro \
    -v "$TEST_DATA":/test_data:ro \
    "$IMAGE" sleep 3600 >/dev/null

# Wait for container to be ready
docker exec "$CONTAINER" true

###############################################################################
# Level 1: File Existence
###############################################################################
section "Level 1: File Existence"

# Check file exists and is non-zero
check_file() {
    local path="$1" desc="$2"
    if run_in "test -s '$path'" >/dev/null 2>&1; then
        pass "$desc"
    else
        fail "$desc" "$path missing or empty"
    fi
}

# Check symlink resolves to a non-zero file
check_link() {
    local path="$1" desc="$2"
    if run_in "test -e '$path' && test -s '$path'" >/dev/null 2>&1; then
        pass "$desc"
    else
        fail "$desc" "$path symlink broken or target empty"
    fi
}

check_file "/WRF/main/wrf.exe"  "WRF wrf.exe exists"
check_file "/WRF/main/real.exe" "WRF real.exe exists"
check_link "/WRF/run/wrf.exe"   "WRF run/wrf.exe symlink resolves"
check_link "/WRF/run/real.exe"  "WRF run/real.exe symlink resolves"

check_file "/WPS/geogrid/src/geogrid.exe" "WPS geogrid.exe exists"
check_file "/WPS/metgrid/src/metgrid.exe" "WPS metgrid.exe exists"
check_file "/WPS/ungrib/src/ungrib.exe"   "WPS ungrib.exe exists"
check_link "/WPS/geogrid.exe" "WPS geogrid.exe symlink resolves"
check_link "/WPS/metgrid.exe" "WPS metgrid.exe symlink resolves"
check_link "/WPS/ungrib.exe"  "WPS ungrib.exe symlink resolves"

check_link "/WRF/run/MPTABLE.TBL"     "MPTABLE.TBL (Noah-MP) resolves"
check_link "/WPS/geogrid/GEOGRID.TBL" "GEOGRID.TBL (NZ) resolves"
check_link "/WPS/metgrid/METGRID.TBL" "METGRID.TBL (NZ) resolves"

###############################################################################
# Level 2: Shared Library Dependencies
###############################################################################
section "Level 2: Shared Library Dependencies"

check_ldd() {
    local exe="$1" desc="$2"
    local output
    output=$(run_in "ldd '$exe' 2>&1")
    if echo "$output" | grep -q "not found"; then
        local missing
        missing=$(echo "$output" | grep "not found")
        fail "$desc" "$missing"
    else
        pass "$desc"
    fi
}

check_ldd "/WRF/main/wrf.exe"             "ldd wrf.exe"
check_ldd "/WRF/main/real.exe"            "ldd real.exe"
check_ldd "/WPS/geogrid/src/geogrid.exe"  "ldd geogrid.exe"
check_ldd "/WPS/metgrid/src/metgrid.exe"  "ldd metgrid.exe"
check_ldd "/WPS/ungrib/src/ungrib.exe"    "ldd ungrib.exe"

###############################################################################
# Level 3: Tool Availability
###############################################################################
section "Level 3: Tool Availability"

check_tool() {
    local cmd="$1" desc="$2"
    if run_in "$cmd" >/dev/null 2>&1; then
        pass "$desc"
    else
        fail "$desc" "command failed"
    fi
}

check_tool "rclone --version"   "rclone"
check_tool "era5_to_int --help" "era5_to_int"
check_tool "ncdump 2>&1 || true; which ncdump" "ncdump"
check_tool "ncks --version"     "ncks"
check_tool "python3 --version"  "python3"
check_tool "uv --version"       "uv"
check_tool "which csh"          "csh"

###############################################################################
# Level 4: Geogrid
###############################################################################
section "Level 4: Geogrid"

run_in "mkdir -p /data"
run_in "cp /test_data/namelist.wps /data/" >/dev/null

output=$(run_in "cd /data && /WPS/geogrid.exe 2>&1") || true

if echo "$output" | grep -qi "Successful completion of geogrid"; then
    pass "geogrid.exe completed successfully"
else
    fail "geogrid.exe" "$(echo "$output" | tail -5)"
fi

if run_in "test -s /data/geo_em.d01.nc" >/dev/null 2>&1; then
    pass "geo_em.d01.nc produced"
else
    fail "geo_em.d01.nc" "file missing or empty"
fi

###############################################################################
# Level 5: Metgrid
###############################################################################
section "Level 5: Metgrid"

run_in "cp '/test_data/ERA5:2023-02-10_00' '/test_data/ERA5:2023-02-10_03' /data/" >/dev/null

output=$(run_in "cd /data && /WPS/metgrid.exe 2>&1") || true

if echo "$output" | grep -qi "Successful completion of metgrid"; then
    pass "metgrid.exe completed successfully"
else
    fail "metgrid.exe" "$(echo "$output" | tail -5)"
fi

if run_in "test -s '/data/met_em.d01.2023-02-10_00:00:00.nc' && test -s '/data/met_em.d01.2023-02-10_03:00:00.nc'" >/dev/null 2>&1; then
    pass "met_em files produced"
else
    fail "met_em files" "missing or empty"
fi

###############################################################################
# Level 6: Real
###############################################################################
section "Level 6: Real"

run_in "cp /test_data/namelist.input /data/" >/dev/null
run_in "mkdir -p /data/run && cd /data/run && ln -sf /WRF/run/* . && ln -sf ../met_em* . && ln -sf /data/namelist.input ." >/dev/null

output=$(run_in "cd /data/run && ulimit -s unlimited && mpirun -n 4 ./real.exe 2>&1") || true

if run_in "tail -c 40 /data/run/rsl.out.0000" 2>/dev/null | grep -q "SUCCESS COMPLETE REAL_EM INIT"; then
    pass "real.exe completed successfully"
else
    fail "real.exe" "$(run_in 'tail -5 /data/run/rsl.error.0000 2>/dev/null || echo "no rsl output"')"
fi

if run_in "test -s /data/run/wrfinput_d01 && test -s /data/run/wrfbdy_d01" >/dev/null 2>&1; then
    pass "wrfinput_d01 and wrfbdy_d01 produced"
else
    fail "wrfinput/wrfbdy" "missing or empty"
fi

###############################################################################
# Level 7: WRF
###############################################################################
section "Level 7: WRF"

output=$(run_in "cd /data/run && ulimit -s unlimited && mpirun -n 4 ./wrf.exe 2>&1") || true

if run_in "grep -q 'SUCCESS COMPLETE WRF' /data/run/rsl.out.0000" >/dev/null 2>&1; then
    pass "wrf.exe completed successfully"
else
    fail "wrf.exe" "$(run_in 'tail -5 /data/run/rsl.error.0000 2>/dev/null || echo "no rsl output"')"
fi

if run_in "ls /data/run/wrfout_d01_* >/dev/null 2>&1"; then
    pass "wrfout file produced"
else
    fail "wrfout" "no output file found"
fi

###############################################################################
# Summary
###############################################################################
echo ""
echo "==========================================="
echo "  Test Summary"
echo "==========================================="
echo "  Passed:  $PASS_COUNT"
echo "  Failed:  $FAIL_COUNT"
echo "  Total:   $((PASS_COUNT + FAIL_COUNT))"
echo "==========================================="

if [[ $FAIL_COUNT -gt 0 ]]; then
    echo "RESULT: FAIL"
    exit 1
else
    echo "RESULT: PASS"
    exit 0
fi
