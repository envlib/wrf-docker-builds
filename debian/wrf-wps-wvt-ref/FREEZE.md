# Frozen reference: WRF 4.3.3 + original WVT

This image is the **provenance / origin reference** for the WVT source-attribution work — WRF 4.3.3 with the
**original, unmodified water-vapour-tracer modules from the method's authors**. It is kept as a clear,
citable, reproducible artifact (notably for the planned GMD paper's *Code and data availability* section),
not a production build. gfortran + serial WPS, by design.

## ⚠ What "frozen" means after 1.3 (2026-09-15)

The **WVT modules are still the authors' unmodified tarball** — untouched, SHA-verified, and that is
what this image exists to preserve. WRF 4.3.3 and WPS 4.6.0 remain pinned by version, the Debian base
by digest.

**The Python orchestration is now vendored at `wrf-auto-runs/gfortran_wvt_ref/pipeline/`** rather
than copied from the working tree, and carries **exactly two forward-ported fixes**. Both were
applied because the image was failing, and both are absences rather than choices: `84c610d` and the
bbox commit bumped the `intel_wvt` and `gfortran_wvt` compose files but never `gfortran_wvt_ref`, so
this image was never rebuilt against fixes that predated it.

| file | change | commit | why |
|---|---|---|---|
| `run_geogrid.py` | taken wholesale: domain bbox from the full `XLAT_M`/`XLONG_M` rather than the four corner attributes | the corner-bbox fix | On a Lambert domain the extreme latitudes sit *between* corners. Measured on this domain: corners give −51.848, the true grid reaches **−52.305**. ERA5 was requested short, and metgrid died with `Missing values encountered in interpolated fields` at (i,j)=(170,1) and (189,1) — lat −52.14 and −52.26, both inside that 0.46° gap. |
| `run_metgrid.py` | the three stack lines only | `84c610d` | metgrid exhausted the default 8 MB stack. ⚠ That commit **also** switched metgrid to `mpirun -n n_cores_metgrid`; deliberately **not** taken — WPS is serial in this image and this pipeline has no such setting. |

**Nothing else was taken.** A straight rebuild against current `wrf-auto-runs` is not possible and
should not be attempted: `set_params.py` emits `num_wvt_regions` / `num_wvt_bdy_regions` whenever
`tracer_opt = 4`, and neither exists in the authors' registry, so WRF would reject the namelist;
and `create_trmask.py` rejects the flat `min_lat`/`max_lat`/`min_lon`/`max_lon` keys this image's
configs use.

### Properties of this pipeline a user should expect

- **No restart/chunking support.** A `[restart]` section in `parameters.toml` is silently ignored —
  the run is one continuous invocation with no checkpoint and nothing to resume from. Size the
  walltime for the whole simulation.
- **No `':' → '_'` filename rename.** `wrfout` files keep colons. Readers must accept both spellings
  (`wrf-model-eval/src/wvt_precip.py` does, and takes timestamps from the `Times` variable rather
  than the filename).
- **`real.exe` runs at a hardcoded `mpirun -n 4`**; `metgrid.exe` runs serial with no `mpirun`.
- **`params.py` reads only `n_cores` from the environment** — `n_cores_preprocess` and
  `n_cores_metgrid` were added later and are ignored here.
- ⚠ `era5_to_int` is on PATH from the **base** image at `0.3.0` (`uv tool install`), which is what
  `run_era5_to_int.py` invokes; `pyproject.toml` separately pins `0.4.0` as a library dependency.
  Two mechanisms, two versions — the command-line one is what runs.

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
