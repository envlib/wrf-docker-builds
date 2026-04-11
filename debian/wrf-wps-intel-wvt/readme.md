# WRF-WPS + WVT (Water Vapor Tracers)

WRF 4.7.1 + WPS 4.6.0 with WVT moisture tracer modifications. Available in Intel oneAPI (ifx/icx) and gfortran builds.

## What is WVT?

WVT (Water Vapor Tracers) is a moisture tagging tool for the WRF model. It tracks moisture from designated source regions through the full hydrological cycle -- evaporation, vertical mixing, advection, cloud formation, and precipitation. This allows you to answer questions like "what fraction of this rainfall originated from oceanic evaporation?" or "how much moisture in this storm came from the Tasman Sea?"

Six tracer species mirror the WSM6 moisture categories (vapor, cloud water, rain, cloud ice, snow, graupel). As moisture undergoes phase changes, the tracer follows proportionally. When tagged moisture precipitates, it appears in tracer precipitation fields (`TR_RAINNC`, `TR_RAINC`).

Based on: Insua-Costa, D. and Miguez-Macho, G. (2018), "A new moisture tagging capability in the Weather Research and Forecasting model", Earth Syst. Dynam., 9, 167-185.

Original repository: https://github.com/damianinsua/WRF-WVTs

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

## Output Variables

When `tracer_opt=4`, WRF produces additional output fields:

| Variable | Dimensions | Description |
|----------|-----------|-------------|
| `qv_tr` | 3D | Tracer water vapor mixing ratio |
| `qc_tr` | 3D | Tracer cloud water mixing ratio |
| `qr_tr` | 3D | Tracer rain water mixing ratio |
| `qi_tr` | 3D | Tracer cloud ice mixing ratio |
| `qs_tr` | 3D | Tracer snow mixing ratio |
| `qg_tr` | 3D | Tracer graupel mixing ratio |
| `TR_RAINNC` | 2D | Accumulated grid-scale tracer precipitation (mm) |
| `TR_RAINC` | 2D | Accumulated cumulus tracer precipitation (mm) |
| `TR_SNOWNC` | 2D | Accumulated tracer snow (mm) |
| `TR_GRAUPELNC` | 2D | Accumulated tracer graupel (mm) |
| `TRQFX` | 2D | Upward moisture tracer flux at surface (kg/m²/s) |

The ratio `TR_RAINNC / RAINNC` gives the fraction of grid-scale precipitation that originated from the tagged source region.

## Build

```bash
docker compose build
```

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
