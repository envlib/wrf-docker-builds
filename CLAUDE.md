# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Docker containerization of the Weather Research and Forecasting (WRF) model and related tools (WPS, WRF-Hydro). Provides reproducible, multi-architecture (amd64/arm64) builds for meteorological simulation on Debian 13.

## Build Commands

Each Docker image is built via `docker compose build` from its respective directory:

```bash
# Base image (must be built first — all others depend on it)
cd debian/wrf-base && docker compose build

# Individual images (each in its own directory under debian/)
cd debian/wrf && docker compose build
cd debian/wrf-wps && docker compose build
cd debian/wrf-wps-hydro-coupled && docker compose build
cd debian/wrf-hydro-sa && docker compose build

# Geog data container
cd geog && docker compose build
```

For ARM64 cross-compilation on amd64: install `qemu-user-static` and enable Docker multi-platform builds.

## Image Hierarchy

```
wrf-base (Debian 13 + gfortran + mpich + HDF5 + NetCDF + tools)
├── wrf-debian          — WRF 4.6.1 only (amd64 + arm64)
├── wrf-wps-debian      — WRF 4.7.1 + WPS 4.6.0
├── wrf-wps-hydro-coupled — WRF 4.7.1 + WPS 4.6.0 + WRF-Hydro 5.4.0
└── wrf-hydro-sa        — WRF-Hydro 5.4.0 standalone

wps-geog-nz (separate, no base dependency) — WPS geographical static data
```

## Architecture

- **debian/wrf-base/Dockerfile**: Base layer with all compiler toolchain, MPI, HDF5/NetCDF, and utility installs (uv, rclone, nco, era5_to_int)
- **debian/WRF4.6.1_Install.bash**: Standalone native installation script (not used by Docker builds but documents the full manual process)
- **debian/wrf-wps/output_module.F**: Custom WPS Fortran module patched into WPS builds for NZ domain support
- **debian/wrf-wps/GEOGRID.TBL.nz, METGRID.TBL.nz**: Custom geogrid/metgrid tables for New Zealand domains
- **geog/make_wps_geog.sh**: Downloads and packages WPS static geographical data with zstd compression
- **debian/wrf/testing/**: Test input data (wrfinput, wrfbdy, wrflowinp) at 1km and 3km resolutions for nested domain simulations

## Key Patterns

- Dockerfiles use environment variables extensively for compiler flags and library paths (NETCDF, HDF5, etc.)
- WRF compilation uses `./configure` then `./compile` with architecture-specific options (option 34 for gfortran+MPI on Linux)
- Docker compose files mount host volumes, set `shm_size: 1g`, and use `network_mode: host`
- WPS builds apply patches: custom `output_module.F` is copied over the default before compilation
- The geog data container uses an init container pattern — it populates a shared volume on first run
