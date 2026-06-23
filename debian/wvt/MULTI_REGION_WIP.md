# Multi-region WVT — work-in-progress / resume doc

> Resume context for the `multi-tracer` branch (wrf-docker-builds). Captures state, the next
> stage, design invariants, and the build/test workflow so development can continue cleanly
> across a context compaction or new session. Last updated: **2026-06-23**.

## Goal
Tag **N disjoint ocean source regions simultaneously in one WRF-WVT run** so a single
simulation yields per-region precipitation attribution over NZ land (replaces N duplicate runs).
Passive tracers ⇒ exact (linearity verified). Approved plan:
`~/.claude/plans/please-read-the-docs-rosy-floyd.md`. Driven by the
[[project_wvt_ocean_area_sensitivity]] study (north −3.0% / west −10.5% are the eventual N=2
acceptance targets).

## Status (stage-by-stage)
- **Phase 0 — DONE, committed by user.** Tracer 4D array expanded to 6×MAX members (MAX=8) via
  `Registry/gen_wvt_tracers.py`; activation scales with `num_wvt_regions` through conditional
  packages (`tracer_moist` on `tracer_opt==4` for region 1 + `wvt_nr2..8` on `num_wvt_regions==N`);
  bounds check in `module_check_a_mundo.F`. Validated: compile + runtime (num_tracer scales, N=1
  bit-identical). Gemini-approved.
- **Stage E1 (diagnostics) — DONE, validated, Gemini-approved. UNCOMMITTED.** `dimspec wvtreg` +
  `PWAT_TR`/`VIMF_TR_U`/`VIMF_TR_V` → `i{wvtreg}j` + per-region loop in `module_diag_wvt_columns.F`.
- **Stage 1b (source+transport, bl_pbl=0 path) — DONE, compiles, validated, Gemini-approved.
  UNCOMMITTED (ready to commit).** `TRMASK`/`TRQFX` → `i{wvtreg}j`; surface-ET TRQFX derivation moved out of
  `module_surface_driver.F` into `module_first_rk_step_part1.F` (after the surface call, ~line 1104);
  per-region diffusion injection at both sites in `module_diffusion_em.F` (assumed-shape `trqfx` +
  reverse-map `im→region`); guards in `module_check_a_mundo.F`. Runtime check passed: region-2
  `PWAT_TR` non-zero (mean 0.20), and region1+region2 = 0.486 == the E1 single-full-ocean value
  (vapour linearity holds).
- **Stage 1c (WSM6 microphysics + cross-region clipping) — NEXT. The go/no-go gate.** See below.
- Later: cumulus (1d, `cu_ntiedtke`), `tr_thum` fluxes, then YSU (`bl_pbl=1`) + 3D paths (currently
  guarded off), then `create_trmask.py` (wrf-auto-runs) N-mask emission + cfdb-ingest downstream.

## Design invariants (MUST hold in every stage)
1. **Contiguous tracer indices.** Region n's species live at `P_QV_TR + (n-1)*6 + s`, s=0..5 for
   (qv,qc,qr,qi,qs,qg). Guaranteed by the conditional packages declaring regions contiguously.
   1b uses inline `P_QV_TR+(n-1)*6`; **1c should build an explicit `p_tr(species,n)` map** (Gemini's
   suggestion — cleaner when manipulating all 6 species × N).
2. **Region dimension** via `dimspec wvtreg 2 namelist=num_wvt_regions z wvt_regions`
   (in `Registry.EM_COMMON`). 2D fields use `i{wvtreg}j` ⇒ Fortran `grid%field(i,n,j)`.
3. **`num_wvt_regions` is a SCALAR rconfig** (required by `dimspec`). `MAX_WVT_REGIONS=8`.
4. **Single base pass.** Per-region physics loops live INSIDE the routines (base computed once,
   shared rates applied to each region). Looping the driver *call* N times is WRONG (double-advances
   the base atmosphere).
5. **CROSS-REGION CLIPPING (the 1c critical fix).** Every WSM6 site that caps a tracer against the
   base (`tr_qc>qc → tr_q+=excess; tr_qc=qc`, the `tr_q=min(tr_q,q)` cap, post-sedimentation caps)
   must act on the **sum** `Σ_n tr_X_n`: if `Σ > base_X`, scale all regions by `base_X/Σ` and route
   the aggregate excess to the vapor tracers. Independent per-region clipping silently breaks
   `Σ regions = all-ocean` whenever a cap fires. **Linear** proportional updates stay simple per-region
   loops; only the **nonlinear caps** need the cross-region reduction.
6. **Scope:** wired for `bl_pbl_physics=0` (diffusion path) + 2D source only. YSU (`bl_pbl=1`) and
   3D source/sink are guarded off in `module_check_a_mundo.F` (`num_wvt_regions>1` requires
   `bl_pbl_physics=0`, `tracer3dsource=tracer3dsink=0`).

## Stage 1c plan (NEXT)
1. Build `p_tr(species,n)` index map (init routine or local helper).
2. Region-dimension the precip accumulators in `registry.moisttracers`:
   `TR_RAINNC`, `TR_RAINC`, `TR_SNOWNC`, `TR_GRAUPELNC`, `I_TR_RAINNC`, `I_TR_RAINC` → `i{wvtreg}j`.
3. `phys/physics_mmm/mp_wsm6.F90`: extend the local `tr_*` arrays with a region dimension; loop the
   *linear* tracer updates per region (reuse shared base rates); convert every *nonlinear base-cap*
   site to cross-region sum-based clipping (invariant 5); accumulate per-region precip.
   `nislfv_rain_plm_tr` sedimentation invoked per region. Driver: `phys/module_mp_wsm6.F` +
   `phys/module_microphysics_driver.F` pass the tr_ slices — make region-aware (loop / map).
4. Validation: N=1 bit-match (hard gate); N=2 region-2 `TR_RAINNC` non-zero; conservation
   `Σ_n TR_RAINNC ≤ RAINNC` pointwise and `Σ_n tr_qv ≤ qv`; linearity `Σ regions == single-all-ocean`.

## Build / test workflow (exact)
- **Compile test** (cache warm, ~few min): from repo root —
  `docker build -f /home/mike/git/wrf-repos/wrf-docker-builds/debian/wrf-wps-intel-wvt/Dockerfile --target builder -t wrf-wvt-mt-test:latest /home/mike/git/wrf-repos/wrf-docker-builds/debian/`
  Then **verify exes** (the `./compile` exits 0 even on link failure!):
  `docker run --rm wrf-wvt-mt-test:latest bash -lc 'ls -la /WRF/main/*.exe'` — if absent, grep the
  log for the registry warning / undefined references. **Do NOT** wait with a `pgrep -f 'docker
  build...'` loop — it matches its own command line and never exits; use `run_in_background:true` or
  poll the exes.
- **Runtime test**: run real+wrf inside the builder image, mounting the test harness, the test_data
  (pre-built `geo_em`+`met_em` at `~/data/wrf/test_data`), and an out dir. See
  `debian/wvt/test/` (copied from `/tmp/wvt_rt_test/`): `make_trmask.py` (region-dimensioned 2-region
  trmask), `namelist.input.n1`/`.n2` (WVT-enabled, `num_wvt_regions=1`/`2`, `bl_pbl=0`, WSM6+Tiedtke),
  `run_n2.sh`, `check_*.py`. Inspect wrfout with
  `uv run --project ~/git/wrf-repos/wrf-auto-runs python <check>.py` (has h5netcdf + scipy).
- Test domain: 99×111 single domain, WSM6/Tiedtke/SMS-3DTKE, 3-h run, `met_em` for 2023-02-10.

## Cadence
Implement a stage → compile-build → runtime-check → **PAUSE** → user runs Gemini code-review on the
diff → incorporate feedback → next stage. The **user commits to git** themselves. Each pause is a
hard stop.
