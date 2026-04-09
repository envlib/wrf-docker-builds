# WRF-WVT Integration Guide

A practical guide for adding Water Vapor Tracer (WVT) support to WRF physics schemes. Written based on the experience of integrating WVT into WRF 4.7.1's WSM6 microphysics, YSU PBL, and Kain-Fritsch cumulus.

## How WVT Tracer Tracking Works

WVT tracks moisture from designated source regions through the full hydrological cycle. Six tracer species mirror the six WSM6 moisture species:

| Tracer | Base Species | Description |
|--------|-------------|-------------|
| `qv_tr` | `QVAPOR` | Water vapor |
| `qc_tr` | `QCLOUD` | Cloud water |
| `qr_tr` | `QRAIN` | Rain water |
| `qi_tr` | `QICE` | Cloud ice |
| `qs_tr` | `QSNOW` | Snow |
| `qg_tr` | `QGRAUP` | Graupel |

The fundamental constraint is: **tracer species <= base species** at all times. Tracers represent the fraction of each moisture species that originated from the tagged source region. The sum of all tracer species represents the total tagged moisture in the column.

### Source and Sink

- **Source injection**: The surface driver computes `TRQFX` (tracer surface flux) as `QFX * TRMASK * (tr_qv / qv)`, where `TRMASK` is a binary field read from `auxinput8`. Over source regions where evaporation occurs, `TRQFX = QFX * TRMASK`.
- **3D source**: Optionally, `solve_em.F` can set all tracer species equal to base moisture in a 3D source region (`TRMASK3D`).
- **3D sink**: Optionally, `solve_em.F` can zero all tracer species in a 3D sink region (`TRMASK3D2`).

### Physics Integration Principles

Each physics scheme handles tracers differently based on the physics involved:

1. **Microphysics**: Proportional mass-fraction following. Each process rate is scaled by the tracer fraction of the source species.
2. **PBL**: Passive scalar vertical diffusion with the same eddy diffusivity as moisture, plus a separate surface flux boundary condition.
3. **Cumulus**: Full tracer transport through convective updrafts, downdrafts, and compensating subsidence.
4. **Surface**: Computes tracer surface flux from base surface flux and the source mask.
5. **Dynamics**: Tracers are advected as 4D tracer fields with positive-definite advection (`tracer_adv_opt=4`).

## Architecture Overview

### Registry

Tracer species are defined as 4D `tracer` fields in `Registry/Registry.EM`:

```
state   real    qv_tr     ikjftb  tracer    1    -    irh06usdf=(bdy_interp:dt)    "qv_tr"    ...
```

The `b` flag enables boundary data and `bdy_interp:dt` enables nest boundary interpolation. The `package` line activates them when `tracer_opt==4`:

```
package   tracer_moist  tracer_opt==4    -    tracer:qv_tr,qc_tr,qr_tr,qi_tr,qs_tr,qg_tr
```

Tracer tendency fields, masks, accumulations, and namelist options are in `Registry/registry.moisttracers`.

### Data Flow Through a Timestep

```
solve_em.F
  |-- first_rk_step_part1
  |     |-- phy_prep (pack tracers for physics)
  |     |-- surface_driver (compute TRQFX)
  |     |-- pbl_driver -> ysu (mix tracers vertically)
  |     |-- cumulus_driver -> kf_eta_cps (transport tracers in convection)
  |
  |-- first_rk_step_part2
  |     |-- calculate_phy_tend (couple tracer tendencies with mu)
  |     |-- update_phy_ten -> phy_bl_ten, phy_cu_ten (apply tendencies)
  |
  |-- microphysics_driver -> wsm6/mp_wsm6_run (tracer phase changes)
  |
  |-- 3D source/sink application (if enabled)
  |
  |-- advance_ppt (accumulate TR_RAINC, zero expired CU tendencies)
```

### Files That Need Changes When Adding a New Scheme

| File | What to change |
|------|---------------|
| Physics scheme module | Add tracer logic (scheme-specific) |
| `module_*_driver.F` | Pass tracer args to scheme call |
| `module_physics_init.F` | Pass tracer args to scheme init (if needed) |
| `module_physics_addtendc.F` | Add tendency accumulation case (CU/PBL only) |
| `module_first_rk_step_part1.F` | Pass tracer args through driver call |
| `share/module_check_a_mundo.F` | Update validation to allow the new scheme |
| `main/depend.common` | Update dependencies (if new files added) |
| `phys/Makefile` | Update module list (if new files added) |

## Integration Pattern 1: Microphysics

### Principle

Every microphysical process that transfers mass between moisture species must proportionally transfer tracer mass. The pattern is:

```fortran
! Base process: autoconversion of cloud water to rain
praut(i,k) = <autoconversion rate computation>

! Tracer process: proportional to tracer fraction of source species
if (l_tracers .and. qci(i,k,1) > qmin) then
  tr_praut(i,k) = praut(i,k) * tr_qci(i,k,1) / qci(i,k,1)
endif
```

After all processes are computed, tracer fields are updated:

```fortran
if (l_tracers) then
  tr_qci(i,k,1) = max(tr_qci(i,k,1) - tr_praut(i,k)*dtcld, 0.0)
  tr_qrs(i,k,1) = max(tr_qrs(i,k,1) + tr_praut(i,k)*dtcld, 0.0)
  ! Cap: tracers never exceed base
  tr_qci(i,k,1) = min(tr_qci(i,k,1), qci(i,k,1))
  tr_qrs(i,k,1) = min(tr_qrs(i,k,1), qrs(i,k,1))
endif
```

### WSM6 Implementation Reference

The WSM6 integration modifies `physics_mmm/mp_wsm6.F90` (CCPP core) and `module_mp_wsm6.F` (wrapper).

**CCPP core (`mp_wsm6_run`):**
- Added optional arguments: `tr_q, tr_qc, tr_qi, tr_qr, tr_qs, tr_qg` (2D), `tr_rain, tr_snow, tr_graupel` (1D), `do_tracers` (logical)
- Added ~28 tracer production rate arrays (`tr_praut`, `tr_pracw`, etc.)
- Added tracer sedimentation routines (`nislfv_rain_plm_tr`, `nislfv_rain_plm6_tr`)
- All tracer code guarded by `if (l_tracers)` flag

**Wrapper (`module_mp_wsm6.F`):**
- Added optional 3D tracer arguments (`tr_qv_curr` through `tr_qg_curr`, `tr_rainnc`, `tr_snownc`, `tr_graupelnc`, flags)
- Packs 3D->2D tile slices before calling `mp_wsm6_run`, unpacks after

### Recipe: Adding WVT to a New Microphysics Scheme

1. **Identify all process rates** in the scheme (condensation, evaporation, autoconversion, accretion, melting, freezing, sedimentation, etc.)

2. **Add optional tracer arguments** to the scheme's main subroutine. Use 6 tracer species matching the scheme's hydrometeor categories. If the scheme has fewer categories (e.g., no graupel), omit the corresponding tracer.

3. **For each process rate**, add a proportional tracer line immediately after:
   ```fortran
   if (l_tracers .and. source_species > qmin) then
     tr_rate = rate * tr_source / source_species
   endif
   ```

4. **Update tracer fields** with the production terms in the same location as the base field updates.

5. **Add tracer sedimentation** using the same fall velocities as base species. The tracer falls at the same speed as its base species.

6. **Accumulate tracer precipitation** at the surface (`tr_rain`, `tr_snow`, `tr_graupel`).

7. **Cap tracers** after all updates: `tr_species = min(tr_species, base_species)`.

8. **Update the wrapper** to pass tracer arguments through.

9. **Update `module_microphysics_driver.F`**: Add the tracer keyword arguments to the scheme's call site.

### Pitfall: Fortran Statement Functions

In WRF 4.7.1, some CCPP physics modules use **Fortran statement functions** (e.g., `cpmcal(x) = ...`). These must appear after all variable declarations but before any executable statements. If you add tracer variable initialization code (like `l_tracers = .false.`) before the statement functions, the compiler will error with "This name has not been declared as an array or a function." Move all executable initialization after the statement functions.

## Integration Pattern 2: PBL Scheme

### Principle

PBL tracer mixing uses the same vertical diffusivity coefficients as moisture. Tracers are passive scalars in the boundary layer with their own surface flux boundary condition (`TRQFX`).

### YSU Implementation Reference (Wrapper-Only)

WRF 4.7.1's YSU CCPP core (`bl_ysu_run`) already has a native passive tracer infrastructure:
- `nmix`: number of extra scalars to mix vertically
- `qmix(its:ite, kts:kte, nmix)`: tracer input fields
- `qmixtnp(its:ite, kts:kte, nmix)`: tracer tendency output

The wrapper integration required **zero changes to the CCPP physics code** -- all changes are in `module_bl_ysu.F`:

1. Changed `nmix` from `integer, parameter :: nmix = 0` to a runtime variable
2. Set `nmix = 3` (qv, qc, qi tracers) when tracer flags are present
3. Changed `qmix`/`rqmixblten`/`qmix_hv`/`rqmixblten_hv` from static arrays to `ALLOCATABLE`
4. Pack tracer fields into `qmix` before the `bl_ysu_run` call
5. Unpack tracer tendencies from `rqmixblten_hv` after the call

### Recipe: Adding WVT to a New PBL Scheme

**If the scheme has `nmix`/`qmix` infrastructure (CCPP pattern):**
- Follow the YSU pattern -- wrapper-only changes, set `nmix` based on tracer flags, pack/unpack
- **Critical:** The CCPP `qmix` loop typically does NOT inject surface fluxes. You must add a `qmix_sflx` argument to the CCPP run subroutine and inject `TRQFX` into the RHS of the tridiagonal system at the bottom level (see Pitfall #8). Only `qv_tr` (index 1) gets the surface flux; `qc_tr` and `qi_tr` have no direct surface emission.

**If the scheme does NOT have `qmix` infrastructure:**
1. Add optional tracer arguments to the scheme's subroutine
2. Inside the scheme, apply the same vertical diffusion to tracers as to moisture:
   - Use the same exchange coefficients (`exch_h`)
   - Solve the same tridiagonal system for tracers
   - Apply `TRQFX` as the surface boundary condition for `qv_tr` -- add it to the **RHS array** (`r1`/`r2`) at `k=1`, not to the solution array (`f1`/`f2`), since tridiagonal solvers overwrite the solution from the RHS
3. Return tracer tendencies (`rtrqvblten`, `rtrqcblten`, `rtrqiblten`)

**Schemes likely to have `nmix`/`qmix` support (check their signatures):**
- MYNN (`module_bl_mynn`) -- may already support `nmix`
- ACM2 (`module_bl_acm`) -- check for passive scalar mixing
- MYJ (`module_bl_myjpbl`) -- older, likely needs manual integration

### Pitfall: Allocatable Arrays with nmix=0

When `nmix=0`, arrays declared as `dimension(its:ite, kts:kte, nmix)` become zero-sized. This is valid Fortran but some compilers may warn. Use `ALLOCATABLE` arrays and allocate with `max(nmix, 1)` to avoid zero-sized allocations, then guard access with `if (nmix >= 1)`.

## Integration Pattern 3: Cumulus Scheme

### Principle

Cumulus tracer transport follows the convective mass flux. Tracers enter updrafts via entrainment, exit via detrainment and precipitation, and are modified by compensating subsidence. This is the most complex integration because the tracer logic must be woven throughout the convective column calculation.

### Kain-Fritsch Implementation Reference

The KF scheme is self-contained in `module_cu_kfeta.F` (not refactored to CCPP). Tracer logic was added directly:

**`KF_eta_CPS` (outer routine):**
- Added optional arguments: `TR_QV` (3D input), `TR_PRATEC` (2D output), 5 tracer tendency arrays, 5 flag logicals
- Extracts 1D tracer column, passes to `KF_eta_PARA`
- Writes back tendency output

**`KF_eta_PARA` (column calculation):**
- Added ~20 local tracer working arrays (`TR_Q0`, `TR_QU`, `TR_QD`, `TR_QG`, `TR_QL0`, `TR_QLG`, etc.)
- **Updraft**: Tracer entrainment proportional to mass flux, condensation tracked via `TPMIX2_tracer`
- **Freezing**: Tracer ice fraction follows the same `DTFRZNEW` calculation
- **Downdraft**: Tracer mixing in downdraft air proportional to moisture mixing
- **Subsidence**: Tracer advection by compensating omega field
- **Tendencies**: `DTRQDT(K) = (TR_QG(K) - TR_Q0(K)) / TIMEC`
- **Precipitation**: `TR_PRATEC = TR_PPTFLX * (1-FBFRC) / DXSQ`

**New helper subroutines:**
- `TPMIX2_tracer`: Tracer-aware parcel temperature/moisture mixing
- `CONDLOAD_tracer`: Tracer precipitation fallout with separate liquid/ice tracking

### Recipe: Adding WVT to a New Cumulus Scheme

1. **Understand the scheme's mass flux framework**: Identify updraft, downdraft, entrainment, detrainment, and subsidence calculations.

2. **Add optional tracer arguments** to the scheme's main subroutine and its column subroutine:
   - Input: `TR_QV` (3D tracer vapor from grid)
   - Output: `TR_PRATEC` (2D tracer precipitation rate)
   - Output: `RTRQVCUTEN` through `RTRQSCUTEN` (3D tracer tendencies)
   - Flags: `F_TR_QV` through `F_TR_QS`

3. **Initialize tracer column** from environment:
   ```fortran
   TR_Q0(K) = min(TR_QV(I,K,J), Q0(K))  ! cap to base moisture
   ```

4. **Updraft tracer entrainment**: At each level, mix environmental tracer air into updraft using the same entrainment rate:
   ```fortran
   TR_QU(K) = (TR_QU(K-1) * MU_old + TR_Q_env * dMU) / MU_new
   ```

5. **Tracer condensation/precipitation**: When the scheme condenses moisture, apply the same fraction to tracers.

6. **Downdraft tracer mixing**: Same pattern as updraft but for downdraft mass flux.

7. **Compensating subsidence**: Advect tracer profiles with the same omega field.

8. **Compute tracer tendencies** as the net change over the convective timestep:
   ```fortran
   DTRQDT(K) = (TR_QG(K) - TR_Q0(K)) / TIMEC
   ```

9. **Accumulate tracer precipitation**:
   ```fortran
   TR_PRATEC(I,J) = TR_PPTFLX * (1.-FBFRC) / DXSQ
   ```

10. **Update driver and tendency accumulation** (see below).

### Pitfall: Argument Ordering in `kf_eta_init`

When adding optional tracer arguments to an init subroutine, ensure the call site in `module_physics_init.F` passes arguments in the exact order declared in the subroutine signature. Fortran positional arguments must match. We hit this as a type-mismatch error where `P_QI` (integer) was passed where `RTRQVCUTEN` (real array) was expected because the tracer args were added in a different position than the call assumed.

### Cumulus Schemes to Consider

For adding WVT to other cumulus schemes, candidates roughly ordered by integration difficulty:

| Scheme | `cu_physics` | CCPP? | Complexity | Notes |
|--------|-------------|-------|------------|-------|
| Kain-Fritsch (done) | 1 | No | High | Full mass-flux framework |
| Grell-Freitas | 3 | No | High | Dual mass-flux (deep+shallow) |
| New Tiedtke | 16 | No | High | Mass-flux with CAPE closure |
| BMJ | 2 | No | Moderate | Adjustment scheme (simpler) |
| KSAS/NSAS | 4/14 | No | High | SAS mass-flux framework |

For mass-flux schemes (GF, Tiedtke, KSAS), the KF integration pattern applies directly. For adjustment schemes (BMJ), the approach is simpler since there's no explicit mass flux -- you'd proportionally adjust tracer fields based on the moisture adjustment profile.

## Driver-Level Plumbing

When adding a new scheme, these driver files need updates:

### `module_*_driver.F` (Physics Driver)

Add tracer keyword arguments to the scheme's `CALL` statement. All tracer args are OPTIONAL so the driver always passes them -- the scheme ignores them when tracers are not active.

```fortran
! In the CASE (YOUR_SCHEME) block:
CALL your_scheme(                                                 &
    <existing base arguments...>                                  &
   ,tr_qv_curr=tr_qv_curr, tr_qc_curr=tr_qc_curr               & ! mvt
   ,rtrqvblten=rtrqvblten                                       & ! mvt
   ,f_tr_qv=flag_tr_qv, f_tr_qc=flag_tr_qc                     & ! mvt
   ... )
```

### `module_physics_addtendc.F` (Tendency Accumulation)

For PBL and cumulus schemes, you need a `CASE` block in `phy_bl_ten` or `phy_cu_ten` that calls `add_a2a` for each tracer tendency:

```fortran
CASE (YOUR_SCHEME)
  IF (P_QV_TR .ge. PARAM_FIRST_SCALAR) &
    CALL add_a2a(tracer_tendf(ims,kms,jms,P_QV_TR), RTRQVBLTEN, ...)
  IF (P_QC_TR .ge. PARAM_FIRST_SCALAR) &
    CALL add_a2a(tracer_tendf(ims,kms,jms,P_QC_TR), RTRQCBLTEN, ...)
```

For cumulus, also update `advance_ppt` to accumulate `TR_RAINC` and zero expired tracer tendencies.

### `module_physics_init.F` (Initialization)

If your scheme has an init subroutine that zeros tendency arrays, add the tracer tendencies. If the scheme's init doesn't need tracer-specific work (common for CCPP schemes), no changes needed.

### `module_first_rk_step_part1.F` (RK Step)

Pass tracer arguments through the driver call. This file just threads the `grid%tr_*` fields to the driver subroutine.

## Pitfalls and Lessons Learned

### 1. NetCDF File Format for trmask

WRF v4+ validates input files by checking the `TITLE` global attribute for the string `' V4.'` (space, V4, period). If the trmask file doesn't contain this, WRF fatals with "input data appears to be from a pre-v4 version." The trmask must also be in **NetCDF3 Classic** format, not NetCDF4/HDF5 -- WRF's auxinput reader rejects NetCDF4 files with string-type attributes.

### 2. `km_opt` Incompatibility with YSU PBL

WRF's default `km_opt=5` (SMS-3DTKE) requires `bl_pbl_physics=0`. If you use YSU PBL (`bl_pbl_physics=1`), you must set `km_opt=4` (2D Smagorinsky) or another compatible option. WRF will fatal at real.exe with "SMS-3DTKE scheme can only work with bl_pbl_physics=0."

### 3. Fortran Statement Functions in CCPP Modules

CCPP physics modules in `physics_mmm/` use old-style Fortran statement functions (e.g., `cpmcal(x) = cpd*(1.-max(x,qmin))+...`). These must come after all `IMPLICIT`, `USE`, and variable declarations, but before any executable statement. If you add an executable like `l_tracers = .false.` before the statement functions, the compiler sees the statement functions as undeclared names. Always add executable initialization AFTER the statement function block.

### 4. Keyword Argument Names Must Match

When the driver calls a scheme with keyword arguments (`tr_qv_curr=tr_qv_curr`), the keyword name must exactly match the dummy argument name in the subroutine signature. The agents initially used shortened names (`TR_Q=...`) that didn't match the wrapper's actual parameter names (`tr_qv_curr=...`), causing "not a dummy argument name" errors.

### 5. `os.rename` Same-Path Error

In the auto-runs pipeline, `os.rename(src, dst)` fails when `src == dst` on some systems. This happens when running a single domain (`run=[1]`) from a multi-domain config -- the geogrid rename loop tries to rename `geo_em.d01.nc` to itself. Fixed with `if src_file_path != dst_file_path`.

### 6. Pendulum DateTime vs String

The `start_date` returned by the auto-runs pipeline is a `pendulum.DateTime` object, not a string. Calling `.replace(' ', '_')` on it invokes pendulum's `replace()` method (which expects integer args for year/month/day), not string replace. Use `.format('YYYY-MM-DD_HH:mm:ss')` instead.

### 7. Docker BuildKit Cache

Docker BuildKit aggressively caches layers even when source files change, especially with multi-stage builds. A `COPY` layer may be cached if the file content hash matches a previous build (even a failed one). Use a cache-busting `ARG` before the copy/compile steps:

```dockerfile
ARG WVT_CACHE_BUST=1  # increment to force rebuild from here
```

### 8. YSU `qmix` Surface Flux Injection: Use `r1`, Not `f1`

The CCPP `bl_ysu_run` has a `qmix`/`qmixtnp` infrastructure for vertically mixing passive tracers. However, this loop does **not** inject a surface flux for `qmix` species -- it only applies vertical diffusion. Moisture gets its surface flux injected via `f1(i,1) = qvx(i,1) + qfx*g/del*dt2` before the tridiagonal solve, but the `qmix` loop just sets `f1(i,k) = qmix(i,k,n)` with no flux term.

To fix this, we added an optional `qmix_sflx` argument to `bl_ysu_run` and inject it at the bottom level. **Critical detail:** the tridiagonal solver `tridin_ysu` uses `r2` (mapped to `r1` in the caller) as the right-hand side -- it **overwrites** `f2` from `r2` in the forward elimination step:

```fortran
f2(i,1,it) = fk*r2(i,1,it)   ! f2 is overwritten from r2, not preserved
```

This means adding the surface flux to `f1` has no effect. The flux must be added to **`r1`**:

```fortran
! WRONG (f1 is overwritten by tridin_ysu):
f1(i,1) = f1(i,1) + (1.0-bepswitch)*qmix_sflx(i,n)*g/del(i,1)*dt2

! CORRECT (r1 is the RHS used by tridin_ysu):
r1(i,1) = r1(i,1) + (1.0-bepswitch)*qmix_sflx(i,n)*g/del(i,1)*dt2
```

Without this fix, `qv_tr` is ~6 orders of magnitude too small because the surface evaporation never enters the tracer field through PBL mixing. This is the single most important detail to get right for any PBL scheme integration that uses a tridiagonal solver.

## Namelist Validation

WRF validates namelist settings in `share/module_check_a_mundo.F` before the simulation starts. The WVT overlay adds checks that enforce compatible scheme selections when `tracer_opt=4`. If a user configures an unsupported scheme, WRF fatals at `real.exe` with a specific error message.

### Current checks (when `tracer_opt==4`)

| Setting | Allowed Values | Error if wrong |
|---------|---------------|----------------|
| `mp_physics` | 6 (WSM6) | `tracer_opt=4 (WVT) requires mp_physics=6 (WSM6)` |
| `bl_pbl_physics` | 1 (YSU) or 0 | `tracer_opt=4 (WVT) requires bl_pbl_physics=1 (YSU) or 0` |
| `cu_physics` | 1 (Kain-Fritsch) or 0 | `tracer_opt=4 (WVT) requires cu_physics=1 (Kain-Fritsch) or 0` |
| `scalar_pblmix` | 0 | `tracer_opt=4 (WVT) requires scalar_pblmix=0` |
| `tracer_pblmix` | 0 | `tracer_opt=4 (WVT) requires tracer_pblmix=0` |
| `tracer_adv_opt` | 4 | `tracer_opt=4 (WVT) requires tracer_adv_opt=4` |

### Updating when adding a new scheme

When you add WVT support to a new scheme, update the corresponding check in `module_check_a_mundo.F` to allow the new option. For example, after adding WVT to Thompson microphysics (`mp_physics=8`), change:

```fortran
! Before:
IF ( model_config_rec % mp_physics(i) .NE. 6 ) THEN

! After:
IF ( model_config_rec % mp_physics(i) .NE. 6 .AND. &
     model_config_rec % mp_physics(i) .NE. 8 ) THEN
```

Similarly for cumulus: after adding WVT to Grell-Freitas (`cu_physics=3`):

```fortran
IF ( model_config_rec % cu_physics(i) .NE. 1 .AND. &
     model_config_rec % cu_physics(i) .NE. 3 .AND. &
     model_config_rec % cu_physics(i) .NE. 0 ) THEN
```

The validation block is near the end of `subroutine check_nml_consistency`, just before the "MUST BE AFTER ALL OF THE PHYSICS CHECKS" comment. Search for `mvt: WVT` to find it.

## Testing Checklist

After integrating WVT into a new scheme:

1. **Compilation**: `docker compose build` succeeds with no errors
2. **File existence**: All 4 WRF executables present (`wrf.exe`, `real.exe`, `ndown.exe`, `tc.exe`)
3. **Standard test**: Run the test suite (`test.sh`) -- geogrid, metgrid, real.exe, wrf.exe all pass
4. **Tracer output**: With `tracer_opt=4`, wrfout contains tracer variables (`tr_qv`, `TR_RAINNC`, etc.)
5. **Value ranges**:
   - `qv_tr` should be 0 at t=0, non-zero at later timesteps
   - `qv_tr <= QVAPOR` everywhere
   - `TR_RAINNC <= RAINNC`
   - `TRQFX` positive over source regions (evaporation)
   - NaN count should be tiny (<0.1%, typically at boundaries)
6. **Non-tracer output unchanged**: Run with `tracer_opt=0` and verify base output matches standard WRF 4.7.1
7. **Conservation**: For a closed domain, total tracer moisture should approximately equal accumulated surface flux minus tracer precipitation (allow for boundary effects)

## Reference: Tracer Variable Summary

### 4D Tracer Array (in `tracer` field, activated by `tracer_opt=4`)

| Variable | Index | Description |
|----------|-------|-------------|
| `qv_tr` | `P_QV_TR` | Tracer water vapor mixing ratio |
| `qc_tr` | `P_QC_TR` | Tracer cloud water |
| `qr_tr` | `P_QR_TR` | Tracer rain water |
| `qi_tr` | `P_QI_TR` | Tracer cloud ice |
| `qs_tr` | `P_QS_TR` | Tracer snow |
| `qg_tr` | `P_QG_TR` | Tracer graupel |

### Tendency Fields (in `registry.moisttracers`)

| Variable | Physics | Description |
|----------|---------|-------------|
| `RTRQVBLTEN` | PBL | Coupled tracer qv tendency from PBL |
| `RTRQCBLTEN` | PBL | Coupled tracer qc tendency from PBL |
| `RTRQIBLTEN` | PBL | Coupled tracer qi tendency from PBL |
| `RTRQVCUTEN` | Cumulus | Coupled tracer qv tendency from cumulus |
| `RTRQCCUTEN` | Cumulus | Coupled tracer qc tendency from cumulus |
| `RTRQRCUTEN` | Cumulus | Coupled tracer qr tendency from cumulus |
| `RTRQICUTEN` | Cumulus | Coupled tracer qi tendency from cumulus |
| `RTRQSCUTEN` | Cumulus | Coupled tracer qs tendency from cumulus |

### Diagnostic/Accumulation Fields

| Variable | Description |
|----------|-------------|
| `TRQFX` | Surface tracer moisture flux (kg/m2/s) |
| `TR_RAINNC` | Accumulated grid-scale tracer precipitation (mm) |
| `TR_RAINC` | Accumulated cumulus tracer precipitation (mm) |
| `TR_SNOWNC` | Accumulated tracer snow (mm) |
| `TR_GRAUPELNC` | Accumulated tracer graupel (mm) |
| `TR_PRATEC` | Tracer precipitation rate from cumulus (mm/s) |
| `TRMASK` | 2D source mask |
| `TRMASK3D` | 3D source mask |
| `TRMASK3D2` | 3D sink mask |

### Namelist Parameters

| Parameter | Section | Description |
|-----------|---------|-------------|
| `tracer_opt = 4` | `&dynamics` | Activate WVT moisture tracers |
| `tracer_adv_opt = 4` | `&dynamics` | Positive-definite RK3 tracer advection |
| `tracer2dsource = 1` | `&dynamics` | Enable 2D source regions |
| `tracer3dsource = 0` | `&dynamics` | Enable 3D source regions |
| `tracer3dsink = 0` | `&dynamics` | Enable 3D sink regions |
| `scalar_pblmix = 0` | `&physics` | Prevent double scalar diffusion |
| `tracer_pblmix = 0` | `&physics` | Prevent double tracer diffusion |
| `io_form_auxinput8 = 2` | `&time_control` | NetCDF format for trmask file |
| `auxinput8_inname` | `&time_control` | Tracer mask filename pattern |
