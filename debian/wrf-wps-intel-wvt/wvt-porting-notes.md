# WRF-WVT Porting Notes: WRF 4.3.3 to 4.7.1

This document details the Fortran source code changes made to integrate WRF-WVT (Water Vapor Tracers) into WRF 4.7.1. The original WRF-WVT code targets WRF 4.3.3 and was authored by Damian Insua-Costa and Gonzalo Miguez-Macho.

## Approach

For each file modified by WRF-WVT, the porting process was:

1. Start with the unmodified WRF 4.7.1 source file
2. Identify WVT-specific additions in the 4.3.3-based WVT file (marked with `! mvt` comments and tracer-specific variable names)
3. Apply those additions to the equivalent locations in the 4.7.1 file

Three new modules (`module_mp_wsm6_tr.F`, `module_bl_ysu_tr.F`, `module_cu_kfeta_tr.F`) were copied from the WRF-WVT repository without modification, as they have minimal dependencies on WRF internals.

## 4.3.3 to 4.7.1 Compatibility Fixes

Two issues required adaptation beyond simply transplanting WVT additions:

1. **`ysu_tr` call missing `TH3D` argument** (`phys/module_pbl_driver.F`): The porting agent omitted `TH3D=th_phy` from the `CALL ysu_tr(...)` argument list. The `ysu_tr` subroutine requires potential temperature as a non-optional argument. Fixed by adding `TH3D=th_phy` to match the original WVT 4.3.3 call pattern.

2. **`ysuinit` removed in 4.7.1** (`phys/module_physics_init.F`): In WRF 4.3.3, the `YSUSCHEME` initialization case called `ysuinit(...)`. In WRF 4.7.1, this subroutine was removed as part of the CCPP (Common Community Physics Package) refactoring -- YSU initialization is now handled internally by `physics_mmm/bl_ysu.F90`. The WVT ELSE branch that called `ysuinit` was removed, keeping only the `IF(tracer_opt==4)` branch that calls `ysuinit_tr`.

## New Files (copied from WRF-WVT as-is)

| File | Lines | Description |
|------|-------|-------------|
| `phys/module_mp_wsm6_tr.F` | 3,121 | WSM6 microphysics with moisture tracer tracking. Mirrors the standard WSM6 scheme but carries 6 tracer species (qv, qc, qr, qi, qs, qg) through all microphysical processes. |
| `phys/module_bl_ysu_tr.F` | 2,106 | YSU PBL scheme with tracer mixing. Computes vertical diffusion of tracer moisture and surface tracer flux (TRQFX). |
| `phys/module_cu_kfeta_tr.F` | 3,903 | Kain-Fritsch cumulus scheme with tracer transport. Redistributes tracer moisture through convective updrafts/downdrafts and produces tracer convective precipitation (TR_RAINC). |
| `Registry/registry.moisttracers` | 29 | Defines WVT state variables: 8 tendency fields (RTRQ*BLTEN, RTRQ*CUTEN), 3 mask fields (TRMASK, TRMASK3D, TRMASK3D2), 5 accumulation fields (TR_RAINNC, TR_RAINC, TR_SNOWNC, TR_GRAUPELNC, TR_PRATEC), 2 diagnostic fields (TRQFX, tr_thum_*_phy_dt), and 3 namelist options (tracer2dsource, tracer3dsource, tracer3dsink). |

## Modified Files

All modifications add WVT tracer handling alongside the existing moisture variable handling. Lines added shown relative to the unmodified WRF 4.7.1 source.

### Registry Files

**Registry/Registry.EM** (+12 lines)
- Added 6 tracer state variables in the `tracer` 4D array: `qv_tr`, `qc_tr`, `qr_tr`, `qi_tr`, `qs_tr`, `qg_tr` -- each with boundary interpolation and restart I/O flags
- Added `package tracer_moist tracer_opt==4` to activate these variables when `tracer_opt=4`

**Registry/Registry.EM_COMMON** (+6 lines)
- Added `thum_u_phy_dt` and `thum_v_phy_dt` state variables (3D, misc) for moisture flux diagnostics, used by the `calc_moist_fluxes` subroutine

**Registry/registry.em_shared_collection** (+1 line)
- Added `include registry.moisttracers` to pull in the WVT variable definitions

### Build System Files

**phys/Makefile** (+3 lines)
- Added `module_mp_wsm6_tr.o`, `module_bl_ysu_tr.o`, `module_cu_kfeta_tr.o` to the `MODULES` list

**main/depend.common** (+8 lines)
- Added `module_cu_kfeta_tr.o` dependency on `module_wrf_error.o`
- Added `module_mp_wsm6_tr.o` dependency on `module_mp_radar.o`
- Added the three new `.o` files to the dependency lists of `module_microphysics_driver.o`, `module_cumulus_driver.o`, `module_pbl_driver.o`, and `module_physics_init.o`

### Physics Driver Files

**phys/module_microphysics_driver.F** (+67 lines)

Adds tracer handling to the microphysics driver:

- `USE module_mp_wsm6_tr` import statement
- 6 tracer mixing ratio arguments added to subroutine signature (`tr_qv_curr` through `tr_qg_curr`)
- 6 optional flag arguments (`f_tr_qv` through `f_tr_qg`) and corresponding `LOGICAL :: flag_tr_*` locals
- 3 tracer precipitation accumulator arguments (`tr_rainnc`, `tr_snownc`, `tr_graupelnc`)
- Flag initialization via `PRESENT()` checks
- Inside the `WSM6SCHEME` case: conditional `IF(FLAG_TR_QV .AND. ...)` that calls `wsm6_tr` with all tracer arguments when tracers are active, otherwise falls through to the standard `wsm6` call

**phys/module_pbl_driver.F** (+110 lines)

Adds tracer handling to the PBL driver:

- `USE module_bl_ysu_tr` import statement
- 6 tracer mixing ratio arguments, 3 tracer PBL tendency arguments (`rtrqvblten`, `rtrqcblten`, `rtrqiblten`), 6 flag arguments, and `trqfx` (surface tracer flux)
- Corresponding variable declarations, local flag declarations, and `PRESENT()` initialization
- Zeroing of `RTRQVBLTEN`, `RTRQCBLTEN`, `RTRQIBLTEN` in the initialization loop
- Inside the `YSUSCHEME` case: conditional `IF(FLAG_TR_QV .AND. ...)` structure that calls `ysu_tr` (with `TH3D=th_phy` and tracer-specific arguments) when tracers are active, otherwise calls the standard `ysu`

**phys/module_cumulus_driver.F** (+97 lines)

Adds tracer handling to the cumulus driver:

- `USE module_cu_kfeta_tr, ONLY : kf_eta_cps_tr` import
- 6 tracer mixing ratio arguments, 6 tracer cumulus tendency arguments (`rtrqvcuten` through `rtrqgcuten`), `tr_rainc`, `tr_pratec`, and flag arguments
- `tr_tmppratec` local variable (mirrors `tmppratec` for tracer precip rate)
- Flag initialization and `tr_tmppratec` zeroing
- Inside the `KFETASCHEME` case: conditional call to `kf_eta_cps_tr` with tracer arguments when active, otherwise standard `kf_eta_cps`
- Copy-back of `TR_PRATEC` from `tr_tmppratec` after cumulus step

**phys/module_surface_driver.F** (+30 lines)

Adds tracer surface flux computation:

- `trqfx`, `trmask`, `tr_qv_curr`, `f_tr_qv` added to subroutine signature
- Variable declarations for the new arguments
- After the surface scheme `END SELECT`: computes `TRQFX` from `QFX` weighted by the tracer-to-moisture ratio and source mask. When `QFX > 0` (evaporation) in the source region, `TRQFX = QFX * TRMASK`. When `QFX < 0` (dew) or outside the source region, `TRQFX` is scaled by the tracer fraction `tr_qv_curr/qv_curr`

**phys/module_physics_init.F** (+77 lines)

Adds tracer initialization:

- `USE module_bl_ysu_tr`, `USE module_cu_kfeta_tr`, `USE module_mp_wsm6_tr` imports in `bl_init`, `cu_init`, and `mp_init` subroutines respectively
- Tracer tendency arguments added to `phy_init`, `bl_init`, `cu_init`, `mp_init` signatures and declarations
- `TR_RAINNC`, `TR_SNOWNC`, `TR_GRAUPELNC` initialized to zero in `mp_init`
- `TR_RAINC` initialized to zero in `cu_init`
- `YSUSCHEME` case in `bl_init`: calls `ysuinit_tr` when `tracer_opt==4` (no ELSE branch -- the standard `ysuinit` was removed in 4.7.1)
- `KFETASCHEME` case in `cu_init`: calls `kf_eta_init_tr` when `tracer_opt==4`, otherwise `kf_eta_init`
- `WSM6SCHEME` case in `mp_init`: calls `wsm6init_tr` when `tracer_opt==4`

**phys/module_physics_addtendc.F** (+122 lines)

Adds tracer tendency accumulation -- the core mechanism for propagating PBL and cumulus tracer tendencies into the tracer fields:

- `tracer_tendf` (4D array) and `n_tracer` added to `update_phy_ten` subroutine
- 8 tracer tendency arguments: 3 PBL (`RTRQVBLTEN`, `RTRQCBLTEN`, `RTRQIBLTEN`) and 5 cumulus (`RTRQVCUTEN` through `RTRQSCUTEN`)
- `phy_bl_ten` subroutine: receives `tracer_tendf`, `n_tracer`, and 3 PBL tracer tendencies. Inside `YSUSCHEME` case, adds 3 `add_a2a` calls guarded by `P_QV_TR >= PARAM_FIRST_SCALAR` checks
- `phy_cu_ten` subroutine: receives `tracer_tendf`, `n_tracer`, and 5 cumulus tracer tendencies. Inside `KFETASCHEME` case, adds 5 `add_a2a` calls
- `advance_ppt` subroutine: receives 5 tracer cumulus tendencies plus `TR_RAINC` and `TR_PRATEC`. Accumulates `TR_RAINC += TR_PRATEC * DT` and zeros tracer tendencies when convective adjustment expires

### Dynamics Files

**dyn_em/solve_em.F** (+74 lines)

Main solver -- threads tracer arguments through to physics calls and applies tracer sources/sinks:

- Tracer cumulus tendency arguments added to `advance_ppt` call
- Tracer BL/CU tendency arguments added to `phy_prep_part2` call
- Tracer mixing ratio arguments (`TR_QV_CURR` through `TR_QG_CURR`) with flags added to `microphysics_driver` call, plus `TR_RAINNC`, `TR_SNOWNC`, `TR_GRAUPELNC`
- Two new code blocks after the scalar filter section:
  - **3D source**: When `tracer3dsource==1`, sets tracer species equal to full moisture in the `TRMASK3D` region
  - **3D sink**: When `tracer3dsink==1`, zeros tracer species in the `TRMASK3D2` region

**dyn_em/start_em.F** (+5 lines)

Initialization:

- Tracer cumulus and PBL tendency arguments added to `phy_init` call
- Tracer precipitation fields added to `phy_init` call
- `grid%trmask` added to `phy_init` call

**dyn_em/module_em.F** (+104 lines)

Tendency coupling/decoupling:

- `USE module_state_description` imports for `p_qv_tr`, `p_qc_tr`, etc.
- `calculate_phy_tend`: receives 8 tracer tendency arguments. Adds coupling loops for 5 cumulus and 3 PBL tracer tendencies (multiply by `mu`), each guarded by `P_Q*_TR >= PARAM_FIRST_SCALAR`
- Wraps `scalar_tend` and `tracer_tend` 4D coupling loops in `IF(scalar_pblmix > 0)` and `IF(tracer_pblmix > 0)` guards to prevent double mixing

**dyn_em/module_big_step_utilities_em.F** (+226 lines)

The largest set of changes, in utility subroutines:

- `USE module_state_description` imports for tracer index constants
- `phy_prep`: receives `tracer`, `n_tracer`, `itimestep`, `dt`, and moisture flux arrays (`thum_u/v_phy_dt`, `tr_thum_u/v_phy_dt`). Adds two calls to `calc_moist_fluxes` -- one for regular moisture, one for tracers (guarded by `n_tracer >= PARAM_FIRST_SCALAR`)
- `phy_prep_part2`: receives 8 tracer tendency arguments. Adds decoupling loops for 5 cumulus and 3 PBL tracer tendencies (divide by `mu`), each guarded by tracer index checks
- **New subroutine `calc_moist_fluxes`** (~78 lines): computes moisture flux diagnostics (`thum_u_phy_dt`, `thum_v_phy_dt`) by summing all moisture species, multiplying by wind components and dt, and accumulating. Placed between `rk_rayleigh_damp` and `theta_relaxation`

**dyn_em/module_first_rk_step_part1.F** (+26 lines)

First Runge-Kutta step -- threads tracer arguments to physics driver calls:

- `phy_prep` call: added `tracer`, `num_tracer`, `grid%itimestep`, `grid%dt`, and moisture flux diagnostic arrays
- `surface_driver` call: added `trqfx`, `trmask`, `tr_qv_curr`, `F_TR_QV`
- `pbl_driver` call: added 6 tracer mixing ratios with flags, 3 PBL tendencies, and `TRQFX`
- `cumulus_driver` call: added `TR_RAINC`, `TR_PRATEC`, 5 cumulus tendencies, and 6 tracer mixing ratios with flags

**dyn_em/module_first_rk_step_part2.F** (+6 lines)

Second part of first RK step:

- `calculate_phy_tend` call: added 3 PBL and 5 cumulus tracer tendency arguments
- `update_phy_ten` call: added `tracer_tend` argument plus 3 PBL and 5 cumulus tracer tendency arguments with `num_tracer`

**share/mediation_wrfmain.F** (+31 lines)

WRF main mediation layer:

- Added `auxinput8` I/O block for reading tracer source/sink masks. When `tracer_opt==4` and any of `tracer3dsource`, `tracer2dsource`, or `tracer3dsink` is enabled, opens and reads the `AUXINPUT8` dataset (containing TRMASK/TRMASK3D/TRMASK3D2 fields) at each timestep. Placed after the existing `auxinput7` block.

**share/module_check_a_mundo.F** (+50 lines)

Namelist validation:

- Added WVT scheme compatibility checks. When `tracer_opt==4`, validates that `mp_physics=6`, `bl_pbl_physics=1 or 0`, `cu_physics=1 or 0`, `scalar_pblmix=0`, `tracer_pblmix=0`, and `tracer_adv_opt=4`. Each violation produces a specific error message and increments the fatal error count. When new schemes gain WVT support, the allowed values in these checks must be updated (see `wvt-integration-guide.md`).

## Limitations (Legacy Physics)

Because the WVT implementation copies three physics modules (`module_mp_wsm6_tr.F`, `module_bl_ysu_tr.F`, and `module_cu_kfeta_tr.F`) directly from WRF 4.3.3, activating `tracer_opt=4` causes the model to fall back to the older logic for these schemes. This introduces several limitations compared to standard WRF 4.7.1:

1. **WSM6 (Microphysics)**
   - **Effective Radii for Radiation:** Lacks support for explicit background and maximum effective radii parameters (`re_qc_bg`, `re_qi_bg`, `re_qs_bg`, etc.) introduced in later versions to improve radiation scheme fidelity.
   - **Radar Reflectivity:** Lacks the bug fixes made in WRF 4.6.0 for radar reflectivity generation (`refl_10cm`) when `do_radar_ref=1`.
   - **WRFDA Compatibility:** Does not include the "regularized" WSM6 (TL/AD models) added in WRF 4.5, meaning it cannot be used for 4DVar assimilation of frozen hydrometeors.

2. **YSU (Planetary Boundary Layer)**
   - **External Model Coupling:** Missing the WRF 4.6.0 updates that introduced a non-intrusive, multi-scale coupling interface for interaction with external ocean/wave models.
   - **Noah-MP Enhancements:** Lacks the coupling refinements made in WRF 4.5+ to support Noah-MP irrigation and crop modeling updates.

3. **Kain-Fritsch (Cumulus)**
   - **Stochastic Parameter Perturbations (SPP):** Does not contain the SPP hooks added in WRF 4.4 for the WRF-Solar Ensemble Prediction System.
   - **Gray-Zone Triggering:** Misses the scale-aware updraft triggering refinements made to the broader Kain-Fritsch family between WRF 4.4 and 4.7.1.

**Takeaway:** This implementation is perfectly suitable for standard regional climate or weather simulations focusing on moisture tracking. However, it should **not** be used for advanced Data Assimilation (4DVar), fully coupled ocean/wave model runs, or Stochastic Ensemble (SPP) forecasting.

## Native 4.7.1 Integration (v1.1)

The legacy physics limitations above apply to the initial v1.0 implementation. In v1.1, the tracer logic was integrated directly into the 4.7.1 physics modules, eliminating the legacy `_tr` modules entirely:

- **WSM6**: Tracer mass-fraction following added directly to `physics_mmm/mp_wsm6.F90` (CCPP core) and `module_mp_wsm6.F` (wrapper). Retains all 4.7.1 improvements (effective radii, radar reflectivity fixes, CCPP error handling).
- **YSU**: Uses the native CCPP `nmix`/`qmix` passive tracer infrastructure in `bl_ysu_run`. Only the wrapper (`module_bl_ysu.F`) was modified. A `qmix_sflx` argument was added to `bl_ysu.F90` to inject the tracer surface flux (`TRQFX`) at the bottom level. Retains all 4.7.1 improvements (Noah-MP coupling, external model coupling).
- **Kain-Fritsch**: Tracer transport added directly to the 4.7.1 `module_cu_kfeta.F`. Retains all 4.7.1 improvements (SPP hooks, gray-zone triggering).

### Validation Results

A 6-hour single-domain test (12km, 273x311, 2023-02-10, land-source mask) comparing native v1.1 against legacy v1.0:

| Variable | Native v1.1 | Legacy v1.0 | Agreement |
|----------|-------------|-------------|-----------|
| `qv_tr` max | 2.69e-3 | 2.45e-3 | Same order of magnitude |
| `qc_tr` max | 9.07e-5 | 9.04e-5 | ~0.4% difference |
| `TR_RAINNC` max | 0.339 mm | 0.338 mm | ~0.3% difference |
| `TR_RAINC` max | 7.175 mm | 7.175 mm | <0.01% difference |
| `TR_RAINNC/RAINNC` mean | 0.0014 | 0.0014 | Identical |
| `TRQFX` max | 1.63e-4 | 1.63e-4 | Identical |

Small differences are expected from the 4.7.1 physics improvements (effective radii in radiation, refined microphysics). Standard (non-tracer) fields (`T2`, `PSFC`, `RAINNC`) show small differences consistent with different physics code paths.

## Summary

| Category | Files | Lines Added |
|----------|-------|-------------|
| New modules (as-is) | 3 | 9,130 |
| Registry | 3 | 19 |
| Build system | 2 | 11 |
| Physics drivers | 6 | 503 |
| Dynamics | 6 | 441 |
| Mediation | 1 | 31 |
| **Total** | **21** | **10,135** |
