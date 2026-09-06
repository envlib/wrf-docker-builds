# Multi-region WVT — work-in-progress / resume doc

> Design record for the multi-region WVT overlay (`debian/wvt-multi/`). Captures the design
> invariants, the stage-by-stage implementation history, and the build/test workflow.
> Last updated: **2026-06-26**.
>
> **STATUS: implementation COMPLETE + PRODUCTION-VALIDATED (2026-06-26).** A 4-region Cyclone Gabrielle
> run (production config) reproduces the independent `:1.14` single-region runs at r≈0.9999, zero NaN,
> exact conservation — see the NEXT section. Remaining work is downstream (cfdb-ingest), not the build.

## Goal
Tag **N disjoint ocean source regions simultaneously in one WRF-WVT run** so a single
simulation yields per-region precipitation attribution over NZ land (replaces N duplicate runs).
Passive tracers ⇒ exact (linearity verified). Driven by the ocean-source-area sensitivity study
(north −3.0% / west −10.5% are the eventual N=2 acceptance targets).

## Status (stage-by-stage)
- **Phase 0 — DONE.** Tracer 4D array expanded to 6×MAX members (MAX=8) via
  `Registry/gen_wvt_tracers.py`; activation scales with `num_wvt_regions` through conditional
  packages (`tracer_moist` on `tracer_opt==4` for region 1 + `wvt_nr2..8` on `num_wvt_regions==N`);
  bounds check in `module_check_a_mundo.F`. Validated: compile + runtime (num_tracer scales, N=1
  bit-identical). Independently reviewed.
- **Stage E1 (diagnostics) — DONE, validated, independently reviewed.** `dimspec wvtreg` +
  `PWAT_TR`/`VIMF_TR_U`/`VIMF_TR_V` → `i{wvtreg}j` + per-region loop in `module_diag_wvt_columns.F`.
- **Stage 1b (source+transport, bl_pbl=0 path) — DONE, compiles, validated, independently reviewed.
 ** `TRMASK`/`TRQFX` → `i{wvtreg}j`; surface-ET TRQFX derivation moved out of
  `module_surface_driver.F` into `module_first_rk_step_part1.F` (after the surface call, ~line 1104);
  per-region diffusion injection at both sites in `module_diffusion_em.F` (assumed-shape `trqfx` +
  reverse-map `im→region`); guards in `module_check_a_mundo.F`. Runtime check passed: region-2
  `PWAT_TR` non-zero (mean 0.20), and region1+region2 = 0.486 == the E1 single-full-ocean value
  (vapour linearity holds).
- **Stage 1c (WSM6 microphysics + cross-region clipping) — DONE, compiles clean, validated,
  Independently reviewed. The go/no-go gate: PASSED.** Registry precip accumulators
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
- **Stage 1d (cumulus / cu_ntiedtke) — DONE (1d-a committed 793f0ef; 1d-b validated + independently reviewed,
  uncommitted).** See the "Stage 1d" section below for the full 1d-a/1d-b record.
- **Stage tr_thum (per-region moisture-flux diagnostics) — DONE, compiles clean, validated,
  Independently reviewed.** (Bonus: gating region 1 on `p_qv_tr >=
  PARAM_FIRST_SCALAR` instead of the old `n_tracer >= PARAM_FIRST_SCALAR` also fixes a latent WRF bug
  where non-moisture tracers would be summed into tr_thum when `tracer_opt != 4`.) `calc_moist_fluxes` (module_big_step_utilities_em.F) gained an
  `ispe_start` arg (loop `ispe=ispe_start..n_moist`) so a single region's contiguous 6-species
  subrange can be summed. Registry: `tr_thum_{u,v}_phy_dt_02..08` (14 fields, identical `ikj misc 1
  - rh` to region 1). All per-region calls live in `phy_prep` next to the base call: region 1 = the
  existing call restricted to `[p_qv_tr, p_qv_tr+5]` (for N=1 == whole tracer array → bit-identical),
  regions 2..N gated `config_flags%num_wvt_regions>=n` summing `[p_qv_tr+(n-1)*6 .. +5]`. The 14
  named fields are threaded through `phy_prep` (one routine, one call site) from `first_rk_step_part1`.
  Files: registry.moisttracers, module_big_step_utilities_em.F, module_first_rk_step_part1.F;
  generator `Registry/gen_wvt_thum.py`; check `test/check_thum.py`. Validated (N=2 vs N=1):
  region-2 flux non-zero (max 127); linearity Σ(N=2)==N=1 totals to ~4e-6, unbiased symmetric FP
  (bias ratio <2.3%, 50% of cells bit-identical) — `tr_thum` accumulates `qv_tr×wind×dt` so it
  amplifies 1d-b's single-precision qv_tr noise but stays unbiased. N=1 bit-identical by construction.
- **PRODUCTION VALIDATION — DONE (2026-06-26).** `create_trmask.py` N-mask emission is in. A full
  production-config **4-region** Cyclone Gabrielle run (12 km NZ d01; FDDA + CCI SST + 28-day spin-up +
  restart chunking) was cross-checked against the **independent `:1.14`** single-region runs (identical
  lat/lon masks, different WRF build + `create_trmask`): **zero NaN**, per-region precip ratios **0.993**
  (north) / **0.989** (west) at spatial **r≈0.9999**, **exact conservation** (Σ4 ≤ total, max +0.008 mm),
  bucket + restart continuity clean. The ~1% per-region deficit is the cross-region cap apportioning
  condensate among co-present regions (conservative; scales with mixing). Bundle + analysis:
  `wrf-runs/projects/tests/wvt_multiregion_12km/analyze_bundle.py`.
  - *Note:* this independence cross-check **supersedes** the original sensitivity-reproduction acceptance
    target — the validation bands are disjoint lat/lon partitions, not the overlapping −3.0% / −10.5%
    sensitivity bands, so per-region numbers are not expected to match those.
- **NEXT (YSU SKIPPED — user happy with bl_pbl=0 production path)**: cfdb-ingest reading the N
  `TR_RAINNC`/`TR_RAINC`/`PWAT_TR`/`TR_THUM_*` sets (per-region attribution into cfdb).

## Design invariants (MUST hold in every stage)
1. **Contiguous tracer indices.** Region n's species live at `P_QV_TR + (n-1)*6 + s`, s=0..5 for
   (qv,qc,qr,qi,qs,qg). Guaranteed by the conditional packages declaring regions contiguously.
   1b uses inline `P_QV_TR+(n-1)*6`; **1c should build an explicit `p_tr(species,n)` map** (the review's
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
  `docker build -f debian/wrf-wps-intel-wvt/Dockerfile --target builder -t wrf-wvt-mt-test:latest debian/`
  Then **verify exes** (the `./compile` exits 0 even on link failure!):
  `docker run --rm wrf-wvt-mt-test:latest bash -lc 'ls -la /WRF/main/*.exe'` — if absent, grep the
  log for the registry warning / undefined references. **Do NOT** wait with a `pgrep -f 'docker
  build...'` loop — it matches its own command line and never exits; use `run_in_background:true` or
  poll the exes.
- **Runtime test**: run real+wrf inside the builder image, mounting the test harness, a test_data
  directory (pre-built `geo_em`+`met_em`), and an out dir. See `debian/wvt-multi/test/`:
  `make_trmask.py` (region-dimensioned 2-region trmask), `namelist.input.n1`/`.n2` (WVT-enabled,
  `num_wvt_regions=1`/`2`, `bl_pbl=0`, WSM6+Tiedtke), `run_1c.sh`, `run_in_container.sh`,
  `check_*.py`. Inspecting wrfout needs h5netcdf + scipy.
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
**DECISION: Option B, and SPLIT 1d:**
- **1d-a (convective precip) — DONE, compiles, validated, independently reviewed, COMMITTED (793f0ef).**
  region-dim `TR_RAINC`/`TR_PRATEC`/`I_TR_RAINC`→`i{wvtreg}j` + per-region
  cumulus calls in cu_ntiedtke_driver yielding per-region `tr_pratec`→`tr_rainc`;
  thread tr_block+count+f_tr_qv through solve_em(first_rk_step_part1)→cumulus_driver→cu_ntiedtke_driver;
  diag_misc TR_RAINC bucket region-loop; advance_ppt tr_rainc accumulation; init. Regions 2..N's
  `rtrq*cuten` were COMPUTED but discarded (only region 1 stored) — 1d-a tagged convective precip but
  not the convective column transport (now recovered by 1d-b).
- **1d-b (convective column transport) — DONE, compiles clean, validated, independently reviewed.
 **
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
  - **APPLY**: `first_rk_step_part2` after `update_phy_ten` — `add_a2a` (already importable:
    `module_physics_addtendc` declares no `PRIVATE`) into
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
Each stage is implemented, compiled, runtime-checked and independently reviewed before the next
stage begins.

## Next stage — LATERAL-BOUNDARY TAGS (design settled 2026-09-06, not started)

**Specification: `wrf-model-eval/docs/wvt_boundary_tags_design.md`** — read it before touching the
code; this section is a pointer plus the invariants that bind the implementation.

- Regions `N−B+1..N` (B = 4 faces) are **column-relabel** regions driven by the existing
  region-dimensioned 2-D `grid%trmask(i,n,j)` over all `k`. **No 3-D mask, no `TRMASK3D_0N`
  members** — the Registry cannot region-dimension an `ikj` field, and a full-column shell does not
  need it. The legacy `tracer3dsource`/`tracer3dsink`/`TRMASK3D` path stays single-region and
  guarded off in `module_check_a_mundo.F` exactly as today.
- The relabel loop goes beside the existing region-1 block in `solve_em.F` (after the end-of-step
  filters); it must set region `n`'s six species to `moist` **and zero the other regions' six species**
  in the shell. Template: the flux loop in `module_first_rk_step_part1.F` (`iqvtr = P_QV_TR + (n-1)*6`).
- New namelist scalar (working name `num_wvt_bdy_regions`, 0..4). Boundary regions skipped in the
  surface-flux loop (`trqfx = 0`).
- `MAX_WVT_REGIONS` 8 → 12: regenerate with `gen_wvt_tracers.py 12`, `gen_wvt_cuten.py 12`,
  `gen_wvt_thum.py`; touch the guarded blocks in `solve_em.F` (1), `module_first_rk_step_part2.F` (2),
  `module_big_step_utilities_em.F` (1), the `select case` in `module_cu_ntiedtke.F` + dummies +
  `module_cumulus_driver.F` pass-through, the bound in `module_check_a_mundo.F`, and
  `MAXREG` in `module_diag_wvt_columns.F`. WSM6 is dynamic in `num_wvt_regions`.
- Masks: `create_trmask.py` gains `mask_type = "boundary"` + `face`; shells are the relaxation-ring
  cells (1–5) nearest each face, corner ties by a pinned convention; the tier-1 enclosed-water fill
  ships in the same change.
- **Gates before the first multi-shell run:** vapour-sum bound AND shell-composition check (region F
  ≈ 1, others ≈ 0 inside shell F) — the WSM6 cross-region cap would otherwise turn a missing zeroing
  into a composition error no sum can see. Validation run: the 12-region CS1 rerun. Code review
  (dual-blind) before that run is believed.
- Same cadence as every stage above: implement → compile → runtime check → independent review.
