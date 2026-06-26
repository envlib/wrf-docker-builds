# WRF-WPS + WVT (Water Vapor Tracers)

WRF 4.7.1 + WPS 4.6.0 with WVT moisture tracer modifications. Available in Intel oneAPI (ifx/icx) and gfortran builds.

**v2.0** adds **multi-region tagging** — up to 8 disjoint source regions tracked simultaneously in a single run (see [Multi-Region Tagging](#multi-region-tagging-v20)). `num_wvt_regions = 1` reproduces the original single-region behaviour bit-for-bit.

## What is WVT?

WVT (Water Vapor Tracers) is a moisture tagging tool for the WRF model. It tracks moisture from designated source regions through the full hydrological cycle -- evaporation, vertical mixing, advection, cloud formation, and precipitation. This allows you to answer questions like "what fraction of this rainfall originated from oceanic evaporation?" or "how much moisture in this storm came from the Tasman Sea?"

Six tracer species mirror the WSM6 moisture categories (vapor, cloud water, rain, cloud ice, snow, graupel). As moisture undergoes phase changes, the tracer follows proportionally. When tagged moisture precipitates, it appears in tracer precipitation fields (`TR_RAINNC`, `TR_RAINC`).

Based on: Insua-Costa, D. and Miguez-Macho, G. (2018), "A new moisture tagging capability in the Weather Research and Forecasting model", Earth Syst. Dynam., 9, 167-185.

Original repository: https://github.com/damianinsua/WRF-WVTs

## Multi-Region Tagging (v2.0)

Version 2.0 tracks **N disjoint source regions in one run**. Set `num_wvt_regions = N` (1..8) and supply
`N` disjoint masks; each region's moisture is followed independently through the full hydrological cycle,
so a single simulation yields per-region precipitation attribution (replacing the older one-run-per-region
workflow). Because the tracers are passive and linear, the result is exact — the sum over regions
reproduces a single all-regions run to numerical precision.

`num_wvt_regions = 1` is fully backward-compatible (original single-region behaviour, bit-for-bit).

### Regions must be disjoint

No grid cell may belong to more than one region's mask — `create_trmask.py` errors on overlap. This is
a requirement of the **attribution semantics**, not a WRF limitation (WRF would run with overlapping
masks; the result would just be meaningless). Each region tags the surface evaporation from its masked
cells (`TRQFX_n = QFX × TRMASK_n`); a cell in two regions has its moisture tagged **twice** — once per
region — so the per-region amounts double-count and "fraction from A" + "fraction from B" can exceed 1.
That is no longer a partition, and "what fraction of the rain came from where" is a partition question.
With disjoint regions the per-region precip sums **exactly** to the single all-source run — the linearity
property that makes the attribution exact rather than approximate. (The cross-region microphysics clipping
also assumes `Σ_n tracer ≤ base`, which overlapping source injection violates at the source.)

Practical consequence: you do **not** subtract one region's tagged precip from another's to get a
difference — each region already **is** the isolated contribution from its own source area. To combine
areas you **add** them (the disjoint set sums to the total). To compare genuinely overlapping or nested
fetches (e.g. "broad Tasman" vs "a sub-box inside it"), run them as separate single-region simulations and
read each on its own.

**Scope** (enforced by `check_a_mundo` — a non-conforming namelist aborts at startup). Multi-region
(`num_wvt_regions > 1`) currently requires:

| Requirement | Reason |
|-------------|--------|
| `tracer_opt = 4` | WVT must be active |
| `mp_physics = 6` (WSM6) | as for all WVT |
| `bl_pbl_physics = 0` (SMS-3DTKE) | multi-region YSU not yet wired |
| `tracer2dsource = 1`; `tracer3dsource = 0`, `tracer3dsink = 0` | only the 2D surface source is multi-region |
| `1 ≤ num_wvt_regions ≤ 8` | compiled member count (`MAX_WVT_REGIONS`) |

Convective tagging is implemented for `cu_physics = 16` (New Tiedtke) and `cu_physics = 0` (no cumulus,
convection-resolving). With other cumulus schemes (KF, MSKF) only region 1's convection is tagged.

### Per-region output representation

Two conventions appear, because the WRF registry can region-dimension 2D fields but not 3D fields:

- **Region-dimensioned** — one variable with an extra `wvt_regions` axis. Applies to the 2D accumulators
  and column diagnostics: `TRMASK`, `TRQFX`, `TR_RAINNC`, `TR_RAINC`, `TR_SNOWNC`, `TR_GRAUPELNC`,
  `TR_PRATEC`, `I_TR_RAINNC`, `I_TR_RAINC`, `PWAT_TR`, `VIMF_TR_U`, `VIMF_TR_V`. In the output these gain
  a leading region dimension, e.g. `TR_RAINNC(Time, wvt_regions, south_north, west_east)`; region `n` is
  index `n-1`.
- **Named members** — one variable per region, region 1 unsuffixed plus `_02`..`_NN` suffixes. Applies to
  the 3D tracer species `qv_tr`/`qc_tr`/…/`qg_tr` (→ `qv_tr_02`, …) and the 3D moisture-flux diagnostics
  `tr_thum_u_phy_dt`/`tr_thum_v_phy_dt` (→ `tr_thum_u_phy_dt_02`, …).

Region `n`'s six tracer species occupy a contiguous block in WRF's tracer array at `P_QV_TR + (n-1)*6`.

### Cost and scaling

Adding regions does **not** re-run the simulation per region — the base atmosphere is integrated **once**
and the per-region tracers ride on top of it (the "single base pass" design invariant). So wall-clock is
roughly `T_base + N · T_tracer`: a large fixed cost plus a per-region increment.

- **Fixed (`T_base`, independent of N):** dynamics/pressure solver, radiation, surface, PBL, and the base
  microphysics *rate* computation (the per-region loops only *apply* those shared rates).
- **Scales ~linearly with `num_wvt_regions` (`T_tracer`):** advection + vertical diffusion of each region's
  six tracer species, the per-region WSM6 microphysics tracer updates + sedimentation, and the per-region
  cumulus pass. Memory and wrfout size scale the same way (six 3D species/region + the region-dimensioned
  2D accumulators + the `qv_tr_0n` members).

The upshot — and the reason for this feature: one N-region run is far cheaper than N separate single-region
runs. The latter recompute the identical base atmosphere N times (`N · (T_base + T_tracer)`); the
multi-region run pays `T_base` once, so each extra region costs a *fraction* of a full run, not a whole one.

### Validation

The implementation was checked **per development stage** (N=1 bit-match against the single-region build;
N=2 region linearity, conservation, and convective/flux diagnostics — recorded in
`../wvt-multi/MULTI_REGION_WIP.md`) and then **end-to-end on a production-config run** (2026-06-26).

A 4-region Cyclone Gabrielle case (12 km NZ d01; FDDA nudging + CCI SST + 28-day spin-up + restart
chunking) was cross-checked against the **independent legacy image** (`:1.14` — a different WRF build and a
different `create_trmask`) running the **identical lat/lon masks** as standalone single-region simulations:

- **Zero NaN** in the tracer fields (the `Σ_n tracer ≤ base` cap `0/0` that previously masqueraded as a
  ~13% deficit is fixed by the `.and. tr_sum > 0.` guard).
- **Per-region independence** — the multi-region north and west regions reproduce their standalone
  counterparts: domain-total precip ratios **0.993** / **0.989** at spatial correlation **r ≈ 0.9999**. The
  ~1% deficit is the cross-region microphysics cap apportioning condensate among co-present regions (a
  standalone run, having no competing tracer, slightly over-attributes); it is conservative and scales with
  how much a region mixes with its neighbours (west > north).
- **Conservation exact** — Σ over all 4 regions ≤ total precip at every cell and frame (max excess
  +0.008 mm, i.e. floating-point).
- **Bucket reconstruction** correct (the storm ticked the 100 mm `I_*RAINNC` counters) and **restart
  continuity** clean across the `wrfrst` at the spin-up/output boundary.

→ multi-region attribution is trustworthy for production (multi-decade) runs.

## Supported Physics Schemes

| Component | Schemes | Notes |
|-----------|---------|-------|
| Microphysics | WSM6 (`mp_physics=6`) | Required -- tracer mass-fraction tracking integrated into WSM6 |
| PBL | YSU (`bl_pbl_physics=1`) | Tracer mixing via native qmix infrastructure |
| PBL | SMS-3DTKE (`bl_pbl_physics=0, km_opt=5`) | Tracer surface flux injected into implicit diffusion solver |
| Cumulus | Kain-Fritsch (`cu_physics=1`) | Tracer transport through convective mass flux |
| Cumulus | New Tiedtke (`cu_physics=16`) | Tracer flux-divergence with cloud detrainment |
| Cumulus | Multi-scale KF (`cu_physics=11`) | KF pattern with automatic scale-awareness |
| Cumulus | None (`cu_physics=0`) | For convection-resolving domains (dx < ~4 km) |

## Source and Sink Mechanisms

WVT provides three independent mechanisms for controlling where moisture is tagged and untagged. They can be used individually or in combination.

### 2D Surface Source (`tracer2dsource=1`)

Tags moisture as it evaporates from the surface in designated regions. The tracer surface flux (`TRQFX`) is computed as `QFX × TRMASK` -- wherever the surface mask is 1 and evaporation occurs, that moisture enters the atmosphere as tagged tracer moisture. The tracer then mixes, advects, and precipitates naturally through the physics.

**Use case**: Track how much precipitation in New Zealand originated from Tasman Sea evaporation. Set `mask_type = "ocean"` to tag all oceanic evaporation.

**Mask variable**: `TRMASK` (2D, read from `trmask_d<domain>` via auxinput8)

### 3D Atmospheric Source (`tracer3dsource=1`)

Continuously forces tracer equal to base moisture throughout a 3D atmospheric volume. At every timestep, wherever `TRMASK3D=1`, all six tracer species are set equal to their base moisture counterparts (`tr_qv = QVAPOR`, `tr_qc = QCLOUD`, etc.). This is a much stronger forcing than the 2D source -- it tags ALL moisture present in the volume, not just newly evaporated moisture.

**Use case**: Track the total moisture content of a specific atmospheric region. For example, tag all moisture in the lower troposphere over the ocean to study how it contributes to downstream precipitation.

**Mask variable**: `TRMASK3D` (3D, read from `trmask_d<domain>` via auxinput8)

### 3D Atmospheric Sink (`tracer3dsink=1`)

Continuously removes tracer tags throughout a 3D atmospheric volume. At every timestep, wherever `TRMASK3D2=1`, all six tracer species are set to zero. This "untags" moisture without removing it from the simulation -- the moisture remains but is no longer counted as tracer moisture.

**Use cases**:

- **Isolating an atmospheric layer**: Combine a full-column 3D source with a sink above 500 hPa. Only lower-tropospheric moisture retains its tag -- any tracer that gets lofted above 500 hPa is untagged. This separates the contribution of low-level moisture from upper-level moisture to precipitation.

- **Studying moisture recycling**: Tag all moisture in a region (3D source) and simultaneously place a 3D sink in the same region. Only moisture that LEFT the source region and RETURNED via advection or precipitation recycling retains its tracer tag, isolating the recycled component.

- **Removing boundary artifacts**: The WRF relaxation zone doesn't conserve tracers well. A 3D sink at the lateral boundaries cleans up spurious tracer values.

- **Removing stratospheric contamination**: A sink above the tropopause prevents tracer from accumulating in the stratosphere where mixing timescales are very long and physics is different.

**Mask variable**: `TRMASK3D2` (3D, read from `trmask_d<domain>` via auxinput8). Note: this is a separate variable from `TRMASK3D`, so source and sink regions can be defined independently.

### Combining Mechanisms

All three mechanisms are independent and controlled by separate namelist flags:

| Configuration | Effect |
|--------------|--------|
| `tracer2dsource=1` only | Tag surface evaporation from masked region. Most common for moisture source attribution. |
| `tracer3dsource=1` only | Tag all moisture in a 3D volume. Strongest forcing. |
| `tracer2dsource=1, tracer3dsource=1` | Tag both surface evaporation AND atmospheric moisture. The 3D source dominates in the overlap region. |
| `tracer3dsource=1, tracer3dsink=1` | Tag moisture in one region, untag in another. Useful for layer isolation or recycling studies. |
| All three enabled | Full flexibility -- surface tagging + atmospheric tagging + selective removal. |

## Namelist Configuration

```
&time_control
 io_form_auxinput8   = 2,
 auxinput8_inname    = "trmask_d<domain>",

&physics
 mp_physics          = 6,
 bl_pbl_physics      = 1,          ! or 0 for SMS-3DTKE
 cu_physics          = 16,         ! or 1, 11, 0
 sf_sfclay_physics   = 1,
 scalar_pblmix       = 0,          ! 0 with PBL scheme, 1 with bl_pbl_physics=0
 tracer_pblmix       = 0,          ! 0 with PBL scheme, 1 with bl_pbl_physics=0

&dynamics
 tracer_adv_opt      = 4,
 tracer_opt          = 4,
 num_wvt_regions     = 1,          ! 1..8 simultaneous source regions (v2.0); >1 requires bl_pbl_physics=0 + 2D source only
 tracer2dsource      = 1,
 tracer3dsource      = 0,
 tracer3dsink        = 0,
```

### SMS-3DTKE Configuration

When using `bl_pbl_physics=0` with `km_opt=5`:
```
 bl_pbl_physics      = 0,
 km_opt              = 5,
 diff_opt            = 2,
 scalar_pblmix       = 1,          ! required -- diffusion module handles mixing
 tracer_pblmix       = 1,          ! required -- diffusion module handles mixing
```

## Tracer Mask File

The `trmask_d<domain>` file is a NetCDF file containing the source/sink mask variables. When using the `wrf-auto-runs` pipeline, this file is generated automatically by `create_trmask.py` based on the `[wvt]` section in `parameters.toml`:

```toml
[wvt]
mask_type = "land"       # "land", "ocean", "bbox", or "all"
relax_width = 5          # grid points to exclude at domain edges
# For bbox only:
# min_lat = -42.0
# max_lat = -38.0
# min_lon = 168.0
# max_lon = 175.0
```

The pipeline creates `TRMASK` when `tracer2dsource=1` and `TRMASK3D` when `tracer3dsource=1`. Both can coexist in the same file.

For manual creation, see `2Dsource.py` in the WRF-WVTs repository as a template.

**Multi-region masks (v2.0).** When `num_wvt_regions = N > 1`, `TRMASK` is region-dimensioned —
`TRMASK(Time, wvt_regions, south_north, west_east)` — and the file must supply `N` **disjoint** masks
(region `n` at index `n-1`); the IO layer reads the region dimension transparently (no extra Fortran).
`create_trmask.py` emits the `N` bands. The masks should not overlap — a cell tagged by two regions would
be double-counted, breaking the `Σ regions = single-run` linearity property.

## Output Variables

When `tracer_opt=4`, WRF produces additional output fields. For `num_wvt_regions > 1` each appears
per-region via one of the two conventions in [Per-region output representation](#per-region-output-representation):
**named members** (`_02`..`_NN` suffix) for 3D fields, or a **region dimension** (`wvt_regions` axis) for
2D accumulators and column diagnostics.

**3D tracer species** — named members (region 1 unsuffixed, regions 2..N suffixed `_0n`):

| Variable | Description |
|----------|-------------|
| `qv_tr` | Tracer water vapor mixing ratio |
| `qc_tr` | Tracer cloud water mixing ratio |
| `qr_tr` | Tracer rain water mixing ratio |
| `qi_tr` | Tracer cloud ice mixing ratio |
| `qs_tr` | Tracer snow mixing ratio |
| `qg_tr` | Tracer graupel mixing ratio |

**Accumulators and column diagnostics** — region-dimensioned (leading `wvt_regions` axis when `num_wvt_regions > 1`):

| Variable | Base dims | Description |
|----------|-----------|-------------|
| `TR_RAINNC` | 2D | Accumulated grid-scale tracer precipitation (mm) |
| `TR_RAINC` | 2D | Accumulated cumulus tracer precipitation (mm) |
| `TR_SNOWNC` | 2D | Accumulated tracer snow + ice (mm) |
| `TR_GRAUPELNC` | 2D | Accumulated tracer graupel (mm) |
| `TR_PRATEC` | 2D | Cumulus tracer precipitation rate (mm/s) |
| `I_TR_RAINNC`, `I_TR_RAINC` | 2D | Bucket counters for the precip accumulators |
| `TRQFX` | 2D | Upward moisture tracer flux at surface (kg/m²/s) |
| `PWAT_TR` | 2D | Tracer precipitable water (column-integrated tagged vapor) |
| `VIMF_TR_U`, `VIMF_TR_V` | 2D | Vertically integrated tracer moisture flux (x, y) |

**Moisture-flux diagnostics** — 3D, named members (region 1 unsuffixed + `_0n`):

| Variable | Description |
|----------|-------------|
| `tr_thum_u_phy_dt`, `tr_thum_v_phy_dt` | Tagged total-humidity × wind × dt (x, y transport flux) |

The ratio `TR_RAINNC / RAINNC` gives the fraction of grid-scale precipitation originating from a tagged
region. When the precip bucket is enabled (`bucket_mm` in the namelist, typically 100), reconstruct the
true total before taking the ratio: `TR_RAINNC + bucket_mm·I_TR_RAINNC` (and likewise for `TR_RAINC`).

## Build

```bash
docker compose build
```

**Source overlay.** This image overlays `debian/wvt-multi/` (the multi-region WVT source) onto a stock WRF
4.7.1 tree. The original **single-region** WVT source lives in `debian/wvt-single/` and is built by the
`wrf-wps-wvt` (gfortran) and `wrf-wps-intel-wvt-sr` (Intel) images — kept as a frozen independent reference
(multi-region at `num_wvt_regions=1` reproduces it bit-for-bit). The two overlays were split from a single
`debian/wvt/` so both variants can be maintained from one branch. See the build matrix in the repo
`CLAUDE.md` for the full variant × compiler grid.

## Test

```bash
bash test.sh --geog-path /path/to/WPS_GEOG --test-data /path/to/test_data
```

## Intel-Specific Notes

See the `wrf-wps-intel` readme for Intel compiler gotchas (MPI fabric settings, stack size, JasPer workaround, etc.). Key points:

- Use `ulimit -s unlimited` before multi-core MPI runs
- Container uses `I_MPI_FABRICS=shm` for single-node operation
- Two-stage build keeps the runtime image small (~2GB vs ~20GB builder)

## Documentation

- `wvt-porting-notes.md` -- Implementation details and validation results
- `wvt-integration-guide.md` -- How to add WVT support to additional physics schemes
- `sms-3dtke-wvt-status.md` -- SMS-3DTKE integration details

## Reference

Insua-Costa, D. and Miguez-Macho, G. (2018), "A new moisture tagging capability in the Weather Research and Forecasting model: formulation, validation and application to the 2014 Great Lake-effect snowstorm", Earth Syst. Dynam., 9, 167-185.
