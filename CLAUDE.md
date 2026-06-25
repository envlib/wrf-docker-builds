# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Docker containerization of the Weather Research and Forecasting (WRF) model and related tools (WPS, WRF-Hydro). Provides reproducible builds for meteorological simulation. Two compiler families are supported: gfortran (Debian 13 base) and Intel oneAPI (Ubuntu 24.04 base).

## Build Commands

Each Docker image is built via `docker compose build` from its respective directory:

```bash
# gfortran chain (depends on wrf-base)
cd debian/wrf-base && docker compose build           # build first
cd debian/wrf && docker compose build
cd debian/wrf-wps && docker compose build
cd debian/wrf-wps-wvt && docker compose build
cd debian/wrf-wps-hydro-coupled && docker compose build
cd debian/wrf-hydro-sa && docker compose build

# Intel oneAPI chain (multi-stage, no wrf-base dependency)
cd debian/wrf-wps-intel && docker compose build
cd debian/wrf-wps-intel-wvt && docker compose build

# Geog data container
cd geog && docker compose build
```

For ARM64 cross-compilation on amd64: install `qemu-user-static` and enable Docker multi-platform builds.

## Image Hierarchy

```
wrf-base (Debian 13 + gfortran + mpich + HDF5 + NetCDF + tools)
├── wrf-debian             — WRF only
├── wrf-wps-debian:1.3     — WRF 4.7.1 + WPS 4.6.0 (gfortran, dmpar, -fno-stack-arrays)
├── wrf-wps-wvt-debian:1.3 — WRF 4.7.1 + WPS 4.6.0 + WVT (gfortran, dmpar, -fno-stack-arrays)
├── wrf-wps-wvt-ref-debian:1.0 — WRF 4.3.3 + WPS reference build
├── wrf-wps-hydro-coupled  — WRF 4.7.1 + WPS 4.6.0 + WRF-Hydro 5.4.0
└── wrf-hydro-sa           — WRF-Hydro 5.4.0 standalone

intel/oneapi-hpckit (multi-stage — builder + runtime)
├── wrf-wps-intel-ubuntu:1.0     — WRF 4.7.1 + WPS 4.6.0 (Intel oneAPI, serial WPS)
└── wrf-wps-intel-wvt-ubuntu:2.0 — WRF 4.7.1 + WPS 4.6.0 + multi-region WVT (Intel oneAPI, dmpar WPS, -heap-arrays)

wps-geog-nz (separate, no base dependency) — WPS geographical static data
```

Downstream pipeline images (`wrf-auto-runs`, `wrf-auto-runs-wvt`, `wrf-auto-runs-intel-wvt`, `wrf-auto-runs-wvt-ref`) are built in the `wrf-auto-runs` repo and `FROM` the WPS images here.

## Multi-region WVT (`wrf-wps-intel-wvt-ubuntu:2.0`)

The WVT (water-vapour-tracer) image tags evaporative-source moisture and follows it through the full
hydrological cycle to attribute precipitation by source. **v2.0 generalises this to N disjoint source
regions tracked simultaneously in one run** (1..8, scalar namelist `num_wvt_regions`) — replacing N
duplicate single-region runs. `num_wvt_regions=1` reproduces the original single-region build bit-for-bit.

- Source lives on the **`multi-tracer` branch**, overlay `debian/wvt/` (COPYed over a stock WRF 4.7.1 in
  the builder stage, then `./compile em_real`). Resume/design doc: **`debian/wvt/MULTI_REGION_WIP.md`**.
- Region n's 6 tracer species are contiguous at `P_QV_TR+(n-1)*6`; 2D fields gain a region dimension via
  `dimspec wvtreg` (`i{wvtreg}j` → `grid%f(i,n,j)`); 3D fields use named members (`qv_tr`, `qv_tr_02`..).
  Cross-region WSM6 clipping caps `Σ_n tracer ≤ base` (guard `.and. tr_sum>0.` on every cap — a `0/0` there
  produced NaN that masqueraded as a ~13% deficit). Scoped to `bl_pbl_physics=0` + 2D source.
- **Cost — single base pass:** the base atmosphere/physics is integrated ONCE; the per-region tracer loops
  ride on top. Wall-clock ≈ `T_base + N·T_tracer` — fixed base (dynamics/radiation/surface/PBL + base
  microphysics *rates*) plus a per-region increment (tracer advection/diffusion of 6 species, WSM6 tracer
  updates + sedimentation, cumulus) that scales ~linearly with `num_wvt_regions`; memory + wrfout scale the
  same way. So one N-region run ≪ N single-region runs (which recompute the identical base N times).
- **Validation — production cross-check (2026-06-26):** a full production-config 4-region run (Cyclone
  Gabrielle, 12 km NZ d01, FDDA nudging + CCI SST + 28-day spin-up + restart chunking) reproduces the
  **independent legacy image** `:1.14` single-region runs (a different WRF build *and* a different
  `create_trmask`, driven with identical lat/lon masks): **zero NaN**; per-region precip ratios **0.993**
  (north) / **0.989** (west) at spatial **r≈0.9999** (the ~1% deficit is the cross-region cap apportioning
  condensate among co-present regions — conservative, scales with mixing); Σ-regions ≤ total precip exact
  (max +0.008 mm); bucket reconstruction + restart continuity clean. Per-stage development checks (N=1
  bit-match, N=2 linearity/conservation) are in `debian/wvt/MULTI_REGION_WIP.md`. → production-trustworthy.
- **Compile test** (cache-warm): `docker build --target builder -t wrf-wvt-mt-test debian/ -f
  debian/wrf-wps-intel-wvt/Dockerfile`, then verify the exes exist (`./compile` exits 0 even on a link
  failure). **Runtime gotcha:** `wrf.exe` needs `ulimit -s unlimited` (docker `--ulimit stack=-1:-1`) or it
  SIGSEGVs at the first integration step — the wrf-auto-runs pipeline sets this; a bare `docker run` must too.

## Critical: WPS heap-array allocation flags

Both WPS builds inject Fortran flags that force automatic-array allocation onto the heap rather than the stack. **This is load-bearing — without these flags, `metgrid.exe` segfaults in `libc.so.6` partway through long preprocessing runs (~1 month of ERA5 data is the typical threshold).**

- **gfortran** (`wrf-wps-wvt/Dockerfile`, `wrf-wps/Dockerfile`): `-fno-stack-arrays` injected via sed into `configure.wps` between `./configure` and `./compile`.
- **Intel ifx** (`wrf-wps-intel-wvt/Dockerfile`, `wrf-wps-intel/Dockerfile`): `-heap-arrays` injected via sed.

Both are added to `FFLAGS` and `F77FLAGS` (`FNGFLAGS` inherits via `$(FFLAGS)`). The sed pattern echoes the patched lines into the build log via `grep -E '^(FFLAGS|F77FLAGS) *='` so cache-busted rebuilds are easy to verify.

When upgrading WPS or modifying these Dockerfiles, **preserve the heap-arrays injection**. The bug is an upstream WPS issue exposed by stack-array allocation in long runs; the flag is a workaround that masks the symptom rather than fixing the root cause.

## WPS configure options

- `wrf-wps-debian:1.3` and `wrf-wps-wvt-debian:1.3`: WPS option **2** (`Linux x86_64, gfortran (dmpar)`). Enables `mpirun -n N metgrid.exe` for parallel preprocessing. Selected via `echo 2 | ./configure --build-grib2-libs`.
- `wrf-wps-intel-ubuntu:1.0`: WPS option **9** (`Linux x86_64, Intel oneAPI (serial)`). Selected via `echo 9 | ./configure --build-grib2-libs`.
- `wrf-wps-intel-wvt-ubuntu:2.0`: WPS option **10** (`Linux x86_64, Intel oneAPI compilers (dmpar)`). Selected via `echo 10 | ./configure --build-grib2-libs`. dmpar is required for the Phase 3 unified per-chunk pipeline where the same image runs both preprocess (parallel `metgrid.exe` / `real.exe` / `ndown.exe`) and WRF.

## Architecture

- **debian/wrf-base/Dockerfile**: Base layer with all compiler toolchain, MPI (mpich), HDF5/NetCDF, and utility installs (uv, rclone, nco, era5_to_int, etc.)
- **debian/wrf-wps/Dockerfile**: gfortran WRF + WPS build
- **debian/wrf-wps-wvt/Dockerfile**: gfortran WRF + WPS + WVT (water vapor tracer) modifications layered on top
- **debian/wrf-wps-intel/Dockerfile**: Multi-stage Intel oneAPI build (builder stage compiles WRF+WPS, runtime stage strips to oneapi-runtime base for size). Builds HDF5/NetCDF-C/NetCDF-Fortran from source with Intel compilers.
- **debian/wrf-wps-intel-wvt/Dockerfile**: Same multi-stage pattern with WVT overlay.
- **debian/wrf-wps/output_module.F**: Custom WPS Fortran module patched into WPS builds for NZ domain support.
- **debian/wrf-wps/GEOGRID.TBL.nz, METGRID.TBL.nz**: Custom geogrid/metgrid tables for New Zealand domains.
- **geog/make_wps_geog.sh**: Downloads and packages WPS static geographical data with zstd compression.
- **debian/wrf/testing/**: Test input data (wrfinput, wrfbdy, wrflowinp) at 1km and 3km resolutions for nested domain simulations.

## Key Patterns

- Dockerfiles use environment variables extensively for compiler flags and library paths (NETCDF, HDF5, etc.).
- WRF compilation: `./configure` then `./compile`. Architecture options: 34 for gfortran+MPI on Linux, 78 for Intel oneAPI dmpar.
- WPS compilation: `./configure --build-grib2-libs` then `./compile`. Options injected via `echo N | ./configure` (see "WPS configure options" above).
- Both gfortran and Intel WPS Dockerfiles patch `configure.wps` between configure and compile to inject the heap-arrays flag (see "Critical" section above).
- Docker compose files mount host volumes, set `shm_size: 1g`, and use `network_mode: host`.
- WPS builds apply patches: custom `output_module.F` is copied over the default before compilation; custom `GEOGRID.TBL.nz` / `METGRID.TBL.nz` are symlinked into place.
- Intel multi-stage builds use a `WVT_CACHE_BUST` ARG to force WVT recompiles when the WVT source changes.
- The geog data container uses an init container pattern — it populates a shared volume on first run.

## Verifying a build

After rebuilding a WPS image, verify the heap-arrays flag actually made it into the binaries:

```bash
# gfortran (dmpar metgrid):
docker run --rm mullenkamp/wrf-wps-wvt-debian:1.3 \
    bash -c "ldd /WPS/metgrid.exe | grep -i mpi && grep -E '^(FFLAGS|F77FLAGS) *=' /WPS/configure.wps"
# Expect: libmpich + libmpichfort, FFLAGS containing -fno-stack-arrays

# Intel (serial metgrid):
docker run --rm mullenkamp/wrf-wps-intel-wvt-ubuntu:2.0 \
    bash -c "grep -E '^(FFLAGS|F77FLAGS) *=' /WPS/configure.wps"
# Expect: FFLAGS containing -heap-arrays
```
