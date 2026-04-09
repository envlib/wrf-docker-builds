# WRF-WPS Intel + WVT (Water Vapor Tracers)

WRF 4.7.1 + WPS 4.6.0 compiled with Intel oneAPI (ifx/icx) and WRF-WVT moisture tracer modifications.

## What is WRF-WVT?

WRF-WVTs is a moisture tagging tool that tracks moisture from specified source regions through the hydrological cycle within WRF simulations. It adds tracer versions of WSM6 microphysics, YSU PBL, and Kain-Fritsch cumulus schemes.

Reference: Insua-Costa, D. and Miguez-Macho, G. (2018), "A new moisture tagging capability in the Weather Research and Forecasting model", Earth Syst. Dynam., 9, 167-185.

Original repository: https://github.com/damianinsua/WRF-WVTs

## Build

```bash
docker compose build
```

## Test

```bash
bash test.sh --geog-path /path/to/WPS_GEOG --test-data /path/to/test_data
```

## WVT Usage

### Required Physics Options

- Microphysics: WSM6 (`mp_physics=6`)
- PBL: YSU (`bl_pbl_physics=1`)
- Cumulus: Kain-Fritsch (`cu_physics=1`) -- optional for convection-resolving scales

### Namelist Configuration

Add these to your `namelist.input`:

```
&time_control
 io_form_auxinput8   = 2,
 auxinput8_inname    = "trmask_d<domain>",

&physics
 scalar_pblmix       = 0,
 tracer_pblmix       = 0,

&dynamics
 tracer_adv_opt      = 4,
 tracer_opt          = 4,
 tracer2dsource      = 1,
 tracer3dsource      = 0,
 tracer3dsink        = 0,
```

### Tracer Mask File

Create a NetCDF file (`trmask_d01`) containing a `TRMASK` variable defining the moisture source region (1 = source, 0 = elsewhere). See `2Dsource.py` in the WRF-WVTs repository for an example.

### Output Variables

When `tracer_opt=4`, WRF produces additional output fields:
- `tr_qv`, `tr_qc`, `tr_qr`, `tr_qi`, `tr_qs`, `tr_qg` -- tracer mixing ratios
- `TR_RAINNC`, `TR_RAINC`, `TR_SNOWNC`, `TR_GRAUPELNC` -- tracer precipitation
- `TRQFX` -- upward moisture tracer flux at surface

## Intel-Specific Notes

See the `wrf-wps-intel` readme for Intel compiler gotchas (MPI fabric settings, stack size, JasPer workaround, etc.). Key points:

- Use `ulimit -s unlimited` before multi-core MPI runs
- Container uses `I_MPI_FABRICS=shm` for single-node operation
- Two-stage build keeps the runtime image small (~2GB vs ~20GB builder)

## WVT Porting Notes

The original WRF-WVT code targets WRF 4.3.3. For this image, the WVT modifications were ported to WRF 4.7.1 by:
1. Extracting WVT-specific additions (identified by `! gmm & dic` markers)
2. Applying them to the corresponding 4.7.1 source files
3. New tracer modules (`wsm6_tr`, `ysu_tr`, `kfeta_tr`) were copied as-is

Modified files are stored in the `wvt/` directory and overlaid onto the WRF source tree during the Docker build.
