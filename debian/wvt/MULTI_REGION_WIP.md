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
- **Stage 1c (WSM6 microphysics + cross-region clipping) — DONE, compiles clean, validated,
  Gemini-approved. The go/no-go gate: PASSED. UNCOMMITTED (ready to commit).** Registry precip accumulators
  (`TR_RAINNC`/`TR_SNOWNC`/`TR_GRAUPELNC`/`I_TR_RAINNC`) → `i{wvtreg}j`; `mp_wsm6.F90` wsm62d
  region-dimensioned (6 species + 3 precip + rate temps, per-region `do n` loops, cross-region
  frac-form caps at every base-cap site, per-region sedimentation via base-save/restore, per-region
  precip accumulation); `module_mp_wsm6.F` driver block interface (`tr_block` + `num_wvt_regions` +
  `f_tr_qv` gate, region-dim `_hv` slabs); `microphysics_driver`/`solve_em` thread the block + count;
  consumers fixed (`mp_init`/`phy_init` zeroing assumed-shape, `diag_misc` bucket region-loop).
  Validation (N=2 west+east vs N=1 full-ocean, WSM6/Tiedtke, 3 h, `-n 4`): region-2 TR_RAINNC
  non-zero (sourced); **linearity** Σregions(N=2)=0.0455634 == N=1 full 0.0455646 (rel 3e-5);
  **conservation** Σ TR_RAINNC ≤ RAINNC exactly (max excess 0.0); Σ qv_tr ≤ QVAPOR. Notes: (a) gate
  must use `f_tr_qv` (tracer_opt=4), not just block-present, or non-WVT WSM6 runs crash; (b) Docker
  needs `--shm-size=2g` for Intel-MPI multi-rank (else SIGBUS, env not code).
- **Stage 1d (cumulus / cu_ntiedtke) — DONE (1d-a committed 793f0ef; 1d-b validated, uncommitted,
  awaiting Gemini).** See the "Stage 1d" section below for the full 1d-a/1d-b record.
- **NEXT after 1d-b sign-off**: `tr_thum` fluxes (column moisture transport diagnostics), then YSU
  (`bl_pbl=1`) + 3D source/sink paths (currently guarded off), then `create_trmask.py` (wrf-auto-runs)
  N-mask emission + cfdb-ingest downstream (read the N `TR_RAINNC`/`TR_RAINC`/`PWAT_TR` sets).

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

## Stage 1d (cumulus / Tiedtke) — MAPPED; awaiting design decision on tendency storage
Scheme = `phys/physics_mmm/cu_ntiedtke.F90` (cu_ntiedtke_run; cu_physics=16). WRF-side driver =
`phys/module_cu_ntiedtke.F` (cu_ntiedtke_driver). Tendency-based (unlike WSM6's in-place state):
driver packs tr_qv/qc/qi_curr → 2D `_hv` (reversed k-order `kte-k+kts`), calls cu_ntiedtke_run, then
`rtrq{v,c,i}cuten = (tr_*_hv − tr_*_curr)/(dt*stepcu)`; `tr_pratec` from the core; `tr_rainc`
accumulated in advance_ppt. **cu_ntiedtke_run declares pu,pv,pt,pqv,pqc,pqi `intent(inout)` (adjusts
base in place)** → per-region calls need base column save/restore (raincv reset by `=`, so base
outputs deterministic — like WSM6 sedimentation).

Feasible parts (mirror 1c): `TR_RAINC`/`TR_PRATEC`/`I_TR_RAINC` → `i{wvtreg}j`; per-region cumulus
calls w/ base save-restore; `diag_misc` TR_RAINC bucket region-loop (lines ~350-366); first_rk_step_part1
cumulus_driver call threads tr_block+count; `module_cumulus_driver.F` threads block.

**BLOCKER (invalidates plan §D4):** the convective tracer tendencies `RTRQ{V,C,I}CUTEN` are 3D (`ikj`),
applied to `tracer_tendf(.,P_*_TR)` via `add_a2a` in `module_physics_addtendc.F` (sites ~1317-1345,
1435-1463, 1754-1768; zeroed ~2546) and PERSIST between cumulus steps (restart flag `r`). Region-
dimensioning them needs a 4D field, but **WRF registry has NO 3D+namelist-category layout** (0 of 240
`i{cat}j` fields are `ik{cat}j`; 4D uses the separate `ikjf` package mechanism). And persistence rules
out region-looping the cumulus on the fly (single storage can't hold N regions for between-step reuse).
Options for per-region convective tracer tendencies: **(B)** named members `RTRQVCUTEN_02..NN` ×3
species ×MAX (consistent w/ Phase-0 tracer members; verbose; awkward to apply in a loop — needs
generated/unrolled add_a2a); **(C)** new 4D `ikjf` package array for tendencies (clean looping, more
machinery); **(D)** rejected — single reused storage breaks between-step reuse.
**DECISION (user + Gemini): Option B, and SPLIT 1d:**
- **1d-a (convective precip) — DONE, compiles, validated, Gemini-approved, COMMITTED (793f0ef).**
  region-dim `TR_RAINC`/`TR_PRATEC`/`I_TR_RAINC`→`i{wvtreg}j` + per-region
  cumulus calls in cu_ntiedtke_driver yielding per-region `tr_pratec`→`tr_rainc`;
  thread tr_block+count+f_tr_qv through solve_em(first_rk_step_part1)→cumulus_driver→cu_ntiedtke_driver;
  diag_misc TR_RAINC bucket region-loop; advance_ppt tr_rainc accumulation; init. Regions 2..N's
  `rtrq*cuten` were COMPUTED but discarded (only region 1 stored) — 1d-a tagged convective precip but
  not the convective column transport (now recovered by 1d-b).
- **1d-b (convective column transport) — DONE, compiles clean, validated, Gemini-approved.
  UNCOMMITTED (ready to commit).**
  Option B named members `RTRQ{V,C,I}CUTEN_02..08` (3 species × 7 regions = 21 fields) via
  `Registry/gen_wvt_cuten.py`. Key simplification vs the original plan: the named fields' couple/
  apply/decouple are done **in-place where `grid` is in scope** (NOT threaded through
  calculate_phy_tend/phy_prep_part2/phy_cu_ten), so only the SET path needs new dummies:
  - **Registry** (`registry.moisttracers`): `RTRQ{V,C,I}CUTEN_02..08` declared identically to region 1
    (`ikj misc 1 - r`) → inherit identical alloc / default-init / restart / IO. ntiedtkeinit doesn't
    zero region-1 RTRQVCUTEN (relies on default state init), so 2..N need NO init code.
  - **SET**: `cu_ntiedtke_driver` gets 21 optional dummies + an `n_wvt>=2` select-case store (region 1
    untouched); `cumulus_driver` (has `TYPE(domain) grid`) passes `grid%rtrq*cuten_0n` to the
    cu_ntiedtke call — no cumulus_driver signature change.
  - **COUPLE**: `first_rk_step_part2` after `calculate_phy_tend` — `×(c1h·mut+c2h)`, patch loop.
  - **APPLY**: `first_rk_step_part2` after `update_phy_ten` — `add_a2a` (made importable) into
    `tracer_tend(P_*_TR+(n-1)·6)`, gated on cu_physics∈{NTIEDTKE,TIEDTKE}. (Only cu_ntiedtke is
    multi-region; kfeta/mskf/other schemes stay region-1, matching 1d-a.)
  - **DECOUPLE**: `solve_em` after the `phy_prep_part2` tile loop — `÷(c1h·muts+c2h)`, patch loop.
  Files: registry.moisttracers, module_cu_ntiedtke.F, module_cumulus_driver.F,
  module_first_rk_step_part2.F (+ `#else INTEGER i,j,k` — i,j,k were only declared under
  `#if WRF_DFI_RADAR==1`), solve_em.F. Validation (N=2 west+east vs N=1 full ocean, 3h, RAINC=9.1mm
  so cumulus active): **qv_tr linearity bit-exact in convective columns** (mean 5.7e-13, max 1.2e-9;
  conv/nonconv error ratio 0.00 — a transport bug would make convective columns the WORST);
  `qc_tr_02`/`qi_tr_02` populated by convective detrainment (region-2 transport live); signed qv_tr
  diff unbiased (mean 3e-10, 50% of cells bit-identical). No regression: TR_RAINC linearity 1.3e-6,
  TR_RAINNC 1.8e-12, conservation exact. N=1 bit-identical by construction (all `>=2` guards false).

## Cadence
Implement a stage → compile-build → runtime-check → **PAUSE** → user runs Gemini code-review on the
diff → incorporate feedback → next stage. The **user commits to git** themselves. Each pause is a
hard stop.
