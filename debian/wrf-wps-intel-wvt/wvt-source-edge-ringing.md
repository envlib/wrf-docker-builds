# WVT: Spurious Far-Field Tracer from Sharp Source Edge

## Issue

When a WVT moisture tracer is seeded with a hard on/off spatial mask (e.g. a 3D source "everywhere north of −23° latitude"), trace amounts of tracer appear in the output far outside the source region almost immediately — well before any physical advection could have transported mass there.

The effect was first noticed in a 12 km d01 run (`v02_33_levels_wvt_nudging`, 33 levels, source = all cells north of −23°N) as very faint pwat_tr features south of the source edge on the first few 3-hourly output frames. It is only visible on a log/symlog colour scale; linear-scale plots show a clean source edge.

## Diagnostic Summary

Measured on `wrfout_d01_2023-02-09_00:00:00.nc` and the derived `wvt_composite_d01.cfdb`:

At t = +3 h (first output step after initialization):

| region | columns with pwat_tr > 0 | typical magnitudes |
|---|---|---|
| north of −23° (source)       | ~18 000 | 1 – 80 kg m⁻² (physical) |
| −23° → −26°                  | ~3 000  | 0.01 – 10 kg m⁻² (physical, source-edge diffusion) |
| south of −30°                | 11 140  | **all < 10⁻⁸ kg m⁻²**; 2 132 columns below the float32 subnormal threshold (1.18×10⁻³⁸); some cells at 10⁻⁴² |

Integrated mass at t = +3 h:

- total column tracer in domain: **1.28 × 10¹⁴ kg**
- mass south of −30°: **3.17 kg** → **2.5 × 10⁻¹² %** of the total

The 3D `qv_tr` field at t = +3 h has 119 099 subnormal cells distributed across all 32 vertical levels and the full domain width, plus small negatives (min = −8 × 10⁻⁹ kg kg⁻¹). By t = +21 h, genuine physical advection has carried the tracer to ~−30° (≈7° of southward spread in 21 h, consistent with ~10 m s⁻¹ flow), while a thin fringe at 10⁻⁶–10⁻⁴ kg m⁻² extends as far as −45°; that fringe remains numerical.

## Root Cause

Relevant namelist / global attributes on this run:

- `MOIST_ADV_OPT = 1`, `SCALAR_ADV_OPT = 1` (positive-definite, **not monotonic**)
- `DIFF_OPT = 2`, `KM_OPT = 5`
- `DIFF_6TH_OPT = 0`

The tracer source is a spatial step function at −23°. WRF's default 5th-order Runge–Kutta scalar advection is non-monotonic near discontinuities: it produces Gibbs-style over/undershoot ripples. `moist_adv_opt = 1` (positive-definite) keeps the final cell mean ≥ 0 and conserves mass, but it does **not** suppress the small over/undershoot that the flux-divergence stencil leaves immediately adjacent to a sharp gradient. Once a neighbouring cell holds any non-zero value — even a float32 denormal — the diffusion and advection stencils of the next step propagate it outward. The apparent "wavefront" is not advancing at the wind speed; it is advancing at the rate the stencil footprint reaches, which is much faster than any physical signal.

The horizontal mixing filter in use here (`diff_opt = 2`, `km_opt = 5`) is a variable-eddy-viscosity scheme. The WRF users guide notes that variable-K filters are **not guaranteed to be positive-definite or monotonic**, and therefore provide another pathway for small-magnitude ripples to be spread outward even when the advection operator is positive-definite. (`diff_6th_opt = 0` on this run, so the 6th-order filter is not contributing.)

The values involved are at or below float32 machine precision (float32 epsilon relative to a ~50 kg m⁻² peak is ~6×10⁻⁶), so the far-field signal is below the storage precision of `pwat_tr` anyway.

## Impact on Analysis

Negligible. Specifically:

- **Mass budgets / source attribution**: phantom mass south of −30° at +3 h is 10⁻¹² of the total. No measurable shift in any budget.
- **Tracer fraction ratios (`pwat_tr / pwat`)**: safe as long as you don't divide by near-zero `pwat`; apply a small floor or mask below ~10⁻³ kg m⁻².
- **Area thresholds** (e.g. "area where tracer > X"): `X ≥ 10⁻³` kg m⁻² excludes essentially all of the noise; `X ≥ 10⁻⁴` still removes the large majority.
- **Figures**: only visible on log / symlog colour scales. Linear plots are fine as-is.

No reason to rerun the simulation on account of this artifact.

## Recommended Handling

**Default stance: do nothing at the model level. Handle at analysis time.**

Given that the artifact is 10⁻¹² of the total mass and below the float32 precision of the stored field, it is not worth altering the model configuration to remove it. The model-level mitigations below (monotonic advection, source-edge taper) would each require revalidating the run against the current baseline — and in the case of monotonic advection, would change the transport of the actual moisture field (QVAPOR, QCLOUD, …), potentially shifting convection triggering, precipitation, and cloud cover by amounts far larger than the artifact itself. The risk/benefit is not worth paying unless a concrete downstream problem appears.

### Primary mitigation — analysis-time only

**Mask / floor the field when plotting or computing metrics.** Drop `pwat_tr` values below ~10⁻³ kg m⁻² (or 10⁻⁴ for a more permissive threshold). Use linear colour scales for general-purpose figures. This is sufficient for essentially all downstream use of this run.

### Model-level options — only if a concrete issue surfaces

These are documented for completeness. Do not apply preemptively; only consider them if analysis-time masking is demonstrably insufficient for a specific question.

1. **Soften the source edge.** Replace the hard `lat > −23°` step with a smooth taper (cosine or tanh ramp over ~3–5 grid cells) when setting `TRMASK` / the injection coefficient. Does not excite the ringing in the first place. Changes tracer behaviour near the source boundary, so any source-edge attribution would need to be re-interpreted.

2. **Switch to monotonic advection for moist / scalar tracers.** Set `moist_adv_opt = 2`, `scalar_adv_opt = 2`, `tke_adv_opt = 2` in `&dynamics`. (`tracer_adv_opt` only takes effect with WRF-Chem active, which is not the case for this WVT build — the tracers ride on the moist/scalar transport path.) This is the highest-risk option because it changes transport for the entire moisture field, not just the tracers.

   Per the WRF users guide, when making this change:

   - **Integration sequence changes.** Physics tendencies (excluding microphysics) are applied before transport rather than alongside it, so the advection scheme sees the physics-updated field; microphysics then runs on the transported field. Switch all `*_adv_opt` together rather than piecemeal.
   - **Extra smoothing.** Monotonic transport adds noticeable smoothing wherever active. The guide suggests considering turning off the 2nd- and 6th-order horizontal filters for scalars; on this run `diff_6th_opt = 0` already, and `diff_opt = 2` / `km_opt = 5` cannot be disabled for scalars only via namelist (would require a code edit).
   - **Validation cost.** Precipitation, cloud cover, and convection in the host moisture field may shift measurably. Any such run is a new baseline and cannot be directly compared to runs using `*_adv_opt = 1`.

## Reproduction

Data used for this assessment:

- `~/data/wrf/sst/v02_33_levels_wvt_nudging/wrfout_d01_2023-02-09_00:00:00.nc`
- `~/data/wrf/sst/v02_33_levels_wvt_nudging/wvt_composite_d01.cfdb`

Key checks to re-run on another case:

- Count of columns with `pwat_tr > 0` south of the source at the first output step — if >> 0, the ringing is present.
- Count of float32 subnormal cells in the 3D `qv_tr` field — non-zero count confirms the mechanism.
- Domain-integrated tracer mass outside the source region vs. inside — ratio should be ~10⁻¹² or smaller for the artifact (physical advection at later times will grow this naturally).
