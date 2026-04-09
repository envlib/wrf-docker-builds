# WRF-WVT Moisture Tracking: Effectiveness and Integrity Assessment

This document provides a detailed assessment of the mathematical and structural integrity of the WRF-WVT (Water Vapor Tracers) implementation ported to WRF 4.7.1.

## Overall Assessment

The WRF-WVT moisture tracking code is highly effective and mathematically sound. It functions as a perfect, passive "dye" that precisely mirrors the physical and thermodynamic pathways of the host moisture fields without altering the model's underlying meteorology.

The implementation achieves this by strictly enforcing proportional scaling of the tracer fields during all phase changes and utilizing the exact same transport fluxes during sub-grid scale parameterizations.

## Component Breakdown

### 1. Dynamics and Advection (The Core)

By defining the moisture tracers (e.g., `qv_tr`, `qc_tr`, `qr_tr`, `qi_tr`, `qs_tr`, `qg_tr`) as part of the `tracer` 4D array group in `Registry.EM`, WRF's dynamical core automatically handles the 3D advection of these variables.
* **Mechanism:** The model utilizes the exact same robust scalar advection mechanisms (Runge-Kutta integration, positive-definite filtering) used for the actual moisture fields.
* **Effectiveness:** This ensures that the passive advection of tracer mass perfectly matches the advection of the total moisture mass, maintaining grid-scale conservation.

### 2. Surface Forcing and PBL Mixing (`module_surface_driver.F` & `module_bl_ysu_tr.F`)

The surface and planetary boundary layer (PBL) schemes govern how tracer mass is injected into and vertically mixed within the atmosphere.
* **Sourcing (Evaporation):** The code correctly injects tracer mass into the atmosphere. If the surface source mask (`TRMASK`) is active in a grid cell and evaporation is occurring (`QFX > 0`), 100% of the evaporated moisture is tagged as tracer flux (`TRQFX = QFX`).
* **Sinking (Dew/Deposition):** If condensation or dew is occurring at the surface (`QFX < 0`), the code mathematically scales the downward flux based on the *current* tracer fraction in the lowest model layer (`TR_QV_CURR / QV_CURR`). This accurately removes tracer mass proportionally and prevents unphysical "negative tracer" anomalies.
* **Vertical Diffusion:** The surface flux (`TRQFX`) is passed into the YSU PBL scheme, which solves the implicit vertical diffusion equation for the tracer variables using the exact same eddy diffusivity coefficients ($K_h$) computed for the total moisture.

### 3. Microphysics and Phase Changes (`module_mp_wsm6_tr.F`)

The WSM6 microphysics scheme handles complex phase changes (e.g., autoconversion of cloud to rain, freezing of rain to graupel, melting, and evaporation). The WVT implementation handles these non-linear processes elegantly and conservatively.
* **Mechanism:** The WVT implementation does not attempt to compute independent microphysical rates for the tracers. Instead, it computes the phase change rate for the *total* moisture field first. It then scales that rate for the tracer based on the instantaneous ratio of tracer mass to total mass for that specific hydrometeor in the grid cell.
* **Example:** `tr_praut = praut * (tr_qci / qci)`. If 10% of the total cloud water converts to rain via autoconversion, exactly 10% of the *tracer* cloud water is converted to *tracer* rain.
* **Effectiveness:** This approach guarantees linear mass conservation during all microphysical phase changes and ensures the tracer explicitly follows the microphysical pathways of the bulk water.

### 4. Convective Transport (`module_cu_kfeta_tr.F`)

The Kain-Fritsch cumulus scheme uses a mass-flux approach to parameterize sub-grid scale convection. The WVT implementation successfully adds identical mass conservation equations for the tracer fields within this framework.
* **Mechanism:** The tracers are pulled into the convective updraft (`UDR`), entrained from the surrounding environment (`UER`), and pushed into convective downdrafts (`DDR`) using the exact same mass fluxes as the total moisture.
* **Effectiveness:** It correctly tracks the conversion of tracer vapor to tracer liquid/ice within the updraft and computes a separate convective tracer precipitation variable (`TR_RAINC`) that reaches the surface, ensuring the sub-grid transport of the tracer is perfectly consistent with the host model.

### 5. Diagnostics for Budgeting

A critical addition to the implementation is the custom subroutine `calc_moist_fluxes` in the dynamical core (`module_big_step_utilities_em.F`).
* **Mechanism:** It explicitly tracks the advective fluxes of both total moisture (`thum_u_phy_dt`, `thum_v_phy_dt`) and the tracers (`tr_thum_u_phy_dt`, `tr_thum_v_phy_dt`).
* **Effectiveness:** This allows researchers to accurately close the moisture budget offline (verifying that Precipitation - Evaporation = Advective Flux Convergence) for both the total moisture and the tracer specifically.

## Conclusion

The code is a textbook example of a rigorous, linear Eulerian tracer implementation. Because it rigidly enforces proportional scaling during phase changes and uses identical transport fluxes during sub-grid scale parameterizations, users can be highly confident that the `TR_RAINNC` and `TR_RAINC` outputs accurately represent the fraction of precipitation that originated from the defined `TRMASK` source regions.