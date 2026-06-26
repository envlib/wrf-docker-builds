# Frozen reference: WRF 4.3.3 + original WVT

This image is the **provenance / origin reference** for the WVT source-attribution work — WRF 4.3.3 with the
**original, unmodified water-vapour-tracer modules from the method's authors**. It is kept as a clear,
citable, reproducible artifact (notably for the planned GMD paper's *Code and data availability* section),
not a production build. gfortran + serial WPS, by design.

## What it contains
- WRF **4.3.3** (`ARG WRF_VERSION=4.3.3`) + WPS **4.6.0** (`ARG WPS_VERSION=4.6.0`).
- The original WVT overlay `debian/wvt-ref/modules_tracers_4.3.3.tar` ("unmodified 4.3.3 tar from the
  authors"), untarred over the WRF source tree.
- Base: Debian 11 (GCC 10) — WRF 4.3.3 does not compile cleanly with GCC 13+.
- Pipeline image: `wrf-auto-runs-wvt-ref` (build context `wrf-auto-runs/gfortran_wvt_ref/`).

## Provenance
- Original online WVT method: **Insua-Costa, D. and Miguez-Macho, G. (2018)**, "A new moisture tagging
  capability in the Weather Research and Forecasting model: formulation, validation and application to the
  2014 Great Lake-effect snowstorm", *Earth Syst. Dynam.*, **9**, 167–185.
- Source repo: the authors' own `github.com/damianinsua/WRF-WVTs` (cloned locally at
  `~/git/wrf-repos/WRF-WVTs`), from which `modules_tracers_4.3.3.tar` is taken. **Confirmed byte-identical**
  to their committed copy (SHA-256 matches), i.e. the base WVT scheme is used unmodified.
- Overlay tar SHA-256: `c425928f439f441629530f90a35a720af05eb546d063f4c25faa80d85dda17c0`
  (`debian/wvt-ref/modules_tracers_4.3.3.tar`). Verify: `sha256sum debian/wvt-ref/modules_tracers_4.3.3.tar`.

## Pinned inputs (for byte-stable rebuilds)
- Base digest-pinned in the Dockerfile:
  `debian:11-slim@sha256:7d5a9679452f9a25d9c8ef2fcb3b9ba0cd1653799a998591292aec1679fad7a2`
  (linux/amd64, observed 2026-06-26). Re-derive with `docker manifest inspect debian:11-slim`.
- `uv` 0.8.15 and `era5_to_int` 0.3.0 are already pinned in the Dockerfile.
- WRF and WPS are pulled from GitHub release tarballs by version (stable URLs); the WVT overlay is vendored
  in-repo (above).

## Reproducibility caveats
- Debian 11 is oldstable; its apt repositories may move to `archive.debian.org`. If a future rebuild fails
  during `apt-get`, point sources.list at the archive.
- `curl https://rclone.org/install.sh | bash` installs the latest rclone (not pinned) — non-scientific
  tooling; pin a version or drop it for a strictly byte-frozen rebuild.

## Freeze + archive procedure (on demand, for citation)
1. Build: `docker build -t mullenkamp/wrf-wps-wvt-ref-debian:ref-4.3.3 -f debian/wrf-wps-wvt-ref/Dockerfile debian/`
2. Push, then record the immutable digest: `docker inspect --format='{{index .RepoDigests 0}}' mullenkamp/wrf-wps-wvt-ref-debian:ref-4.3.3`
3. Archive the image + this repo state (including the overlay tar) to Zenodo; cite the Zenodo DOI and the
   recorded image digest in the GMD *Code and data availability* section (resolves the paper draft's §2
   provenance TODO and §6.5).
