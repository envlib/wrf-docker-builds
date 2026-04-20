# Noah-MP Lateral Flow: Architecture, Gap, and Opportunity

Working notes on how Noah-MP moves water, what it can't do, how WRF-Hydro fills the gap, and where a genuine research/engineering opportunity remains. Motivated by coupled WRF + WRF-Hydro use in steep humid terrain (New Zealand), where shallow subsurface lateral redistribution is the dominant water-balance process.

---

## 1. How Noah-MP Moves Water (Vertical / Column)

Noah-MP is a 1D column land surface model. Each grid cell is independent; the model solves the vertical water and energy budgets for a single column and writes out per-column fluxes. All processes below are column-local.

### 1.1 Above-ground partitioning

**Precipitation partitioning.** Incoming rainfall/snowfall is intercepted by the canopy (`ECANXY`, `qintrxy`/`qintsxy`) with a capacity proportional to leaf area index. Excess becomes throughfall (`qthrorxy`/`qthrosxy`). Drip from a saturated canopy is `qdriprxy`/`qdripsxy`. Canopy water evaporates (`qevacxy`) or, in cold conditions, freezes/melts.

**Snow processes.** Multi-layer snowpack (up to 3 layers) is evolved using explicit energy and mass balances. Snowfall accumulates as `SNICEXY`/`SNLIQXY`, undergoes compaction, redistribution between layers, sublimation (`qsnsubxy`), refreezing (`qsnfroxy`), melt (`qmeltxy`), and bottom drainage into the top soil layer (`qsnbotxy`). Snow albedo evolves dynamically (optionally via SNICAR radiative transfer in v5+).

### 1.2 Infiltration and surface runoff

Water reaching the soil surface partitions between infiltration and surface runoff. The split depends on `OPT_RUN` (runoff option):

| `OPT_RUN` | Scheme | Lateral flow? |
|-----------|--------|---------------|
| 1 | TOPMODEL with SIMGM groundwater (Niu et al. 2007) | Implicit via topo index; no explicit lateral water movement |
| 2 | TOPMODEL with equilibrium water table | Implicit only |
| 3 | Original Noah (free drainage) | No |
| 4 | BATS | No |
| 5 | **Miguez-Macho & Fan 2D groundwater** (Fan et al. 2007) | **Yes — deep aquifer only** |
| 6 | VIC | No |
| 7 | Xinanjiang | No |
| 8 | Dynamic VIC | No |

Infiltration-excess (Hortonian) runoff leaves the column as `SFCRUNOFF` (→ `INFXSRT` when `WRF_HYDRO=1`). Saturation-excess follows the chosen runoff scheme. None of these (except `OPT_RUN=5`, and only for deep groundwater) move water between grid cells.

### 1.3 Soil water (Richards equation, vertical only)

Soil water is evolved on 4 layers by default (configurable) via the 1D vertical Richards equation:

$$\frac{\partial \theta}{\partial t} = \frac{\partial}{\partial z}\left[K(\theta)\left(\frac{\partial \psi}{\partial z} - 1\right)\right] - S(z)$$

where `K(θ)` is unsaturated hydraulic conductivity (Campbell or van Genuchten), `ψ(θ)` is matric potential, and `S(z)` is the root water uptake sink. The solution is fully implicit in each column. There is **no lateral term** in this equation as implemented.

Soil layer thicknesses (`ZSOIL`, `SLDPTH`) default to 0.1 / 0.3 / 0.6 / 1.0 m but can be customized (e.g., Noah-MP v4.5+ supports deep soil for transpiration studies).

### 1.4 Evapotranspiration

Three ET components computed separately:

- **Canopy evaporation** (`ECANXY`) — evaporation of intercepted water, not limited by soil moisture.
- **Transpiration** (`ETRANXY`) — through canopy stomata, driven by Ball-Berry or Jarvis, limited by root-zone soil moisture weighted over layers via `ETRANIXY`.
- **Soil evaporation** (`EDIRXY`) — direct evaporation from the top soil layer.

Total latent heat flux is `LH = LAMBDA × (ECANXY + ETRANXY + EDIRXY)` + snow sublimation. The column is the only water source — no supplementary water arrives from upslope.

### 1.5 Bottom boundary

The soil column bottom is either:

- **Free drainage** (default for most `OPT_RUN` options): water leaving the bottom layer is lost to an implicit groundwater system. This appears as `soldrain` (→ `DRIPX` / groundwater bucket in WRF-Hydro).
- **Equilibrium water table** (`OPT_RUN=2`): bottom layer equilibrates with a prescribed water table depth.
- **MMF 2D groundwater** (`OPT_RUN=5`): the bottom is coupled to a separate 2D groundwater module that does allow lateral flow between cells *at the aquifer level*.
- **SIMGM bucket** (`OPT_RUN=1`): a lumped per-column groundwater reservoir with parameterized discharge.

### 1.6 What Noah-MP writes out per column

Beyond standard state variables (`SMOIS`, `TSLB`, `CANWAT`, `SNOW`, etc.), the Noah-MP output relevant to hydrology includes:

| Variable | Meaning |
|----------|---------|
| `SFCRUNOFF` / `INFXSRT` | Infiltration-excess surface runoff (leaves the column) |
| `UDRUNOFF` / `soldrain` | Underground drainage from soil column bottom |
| `QTDRAIN` | Tile drainage flux (if `OPT_TDRN` enabled) |
| `ZWT` / `ZWATBLE2D` | Water table depth |
| `RUNSFXY` / `RUNSBXY` | Accumulated surface / subsurface runoff |
| `QSNBOTXY` | Snowmelt reaching soil surface |
| `ETRANXY`, `EDIRXY`, `ECANXY` | ET components |

These column fluxes are what any downstream lateral / routing system has to work with.

---

## 2. What Noah-MP Cannot Do (Lateral Processes)

Because the column formulation has no inter-cell transport term, Noah-MP cannot natively represent:

| Process | Typical spatial scale | Noah-MP alone? |
|---------|----------------------|----------------|
| Overland flow (sheet / rill) | 10–100 m | ✗ |
| Shallow subsurface lateral flow (interflow / throughflow) | 10–100 m | ✗ |
| Saturated subsurface lateral flow (water-table-driven) | 100 m – 1 km | ✗ (except `OPT_RUN=5`) |
| Channel flow | 10 m – 10 km | ✗ |
| Deep groundwater lateral flow | 1–10 km | ✓ only with `OPT_RUN=5` (MMF) |
| Reservoir / lake routing | 100 m – 10 km | ✗ |

Consequences:

- Ridge columns and valley columns receive the same precipitation and drain independently. Ridges cannot be drier (no loss to downslope) nor valleys wetter (no gain from upslope).
- Riparian soil moisture is systematically underestimated because it cannot be fed by hillslope drainage between storms.
- Saturation-excess runoff via the variable-source-area mechanism is only implicit (via TOPMODEL-style topographic index adjustments in `OPT_RUN=1,2`), not a true physical representation.
- Baseflow recession shapes are wrong — the fast recession tail that comes from shallow subsurface stormflow is missing.
- Land-atmosphere feedbacks are biased: ET from riparian zones is underestimated between events, so latent heat flux and near-surface humidity are too low.

---

## 3. How WRF-Hydro Fills the Gap (Outside Noah-MP)

WRF-Hydro is architecturally a **routing add-on** that treats Noah-MP as a column-flux provider. The lateral flow computation is entirely outside Noah-MP. The key design choice is to separate process scale from LSM grid scale.

### 3.1 Data flow per timestep (coupled mode)

```
┌──────────────────────────────────────────────────────────────┐
│ Noah-MP (LSM grid, typically 1–4 km) — 1D column physics     │
│   inputs: forcing (T, q, u, v, P, SW, LW, precip)            │
│   outputs per column: SMC, INFXSRT, soldrain,                 │
│                       sfcheadrt, ZWATBLE2D, ...               │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼  disaggregation (time-step-weighted mapping)
┌──────────────────────────────────────────────────────────────┐
│ Routing grid (typically 100 m)                                │
│   subsurface_routing  (Noah_distr_routing_subsurface.F90)     │
│   overland_routing    (Noah_distr_routing_overland.F90)       │
│   channel_routing     (module_channel_routing.F90)            │
│   groundwater_bucket  (module_GW_baseflow.F90)                │
│   gw2d (optional)     (module_gw_gw2d.F90)                    │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼  aggregation back to LSM grid
┌──────────────────────────────────────────────────────────────┐
│ Updated soil moisture → Noah-MP for next timestep             │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 WRF-Hydro's subsurface lateral flow scheme

Enabled by `SUBRTSWCRT=1`. The core routine chain:

- `subsurfaceRouting` (`Noah_distr_routing_subsurface.F90`)
- `FINDZWAT` — locates water table from saturation state per column
- `SUBSFC_RTNG` — Boussinesq-style saturated lateral flow driven by water-table gradients on the routing grid
- `CWATAVAIL` — the water available to lateral transport (saturated portion only)

Characteristics:

- Operates on the **routing grid** (not the LSM grid).
- Treats the saturated portion of each column as a **lumped bucket** — does not move water per Noah-MP soil layer.
- Represents **saturated** lateral flow only. Unsaturated wet-soil lateral flow (interflow) is not represented.
- Exfiltration from over-saturated columns is added to surface head and enters overland flow.

This scheme captures the first-order signal of hillslope-scale subsurface redistribution and is a large improvement over Noah-MP alone. But it has structural limitations discussed next.

### 3.3 Overland, channel, groundwater, reservoirs

- **Overland flow** — diffusive-wave approximation on the routing grid, sourced from infiltration excess (`INFXSRT`) and exfiltration.
- **Channel routing** — Muskingum-Cunge or gridded options; receives water from overland and subsurface lateral flow that reaches the channel network.
- **Groundwater bucket** — per-catchment lumped conceptual bucket receiving `soldrain` from columns, discharging baseflow to channels.
- **2D groundwater** (`gw2d`) — optional gridded alternative to the bucket, with explicit lateral aquifer flow.
- **Reservoirs** — level-pool or controlled-release routing in the channel network.

---

## 4. Architectural Limitations of the WRF-Hydro Approach

The separation of column LSM at atmospheric scale from lateral flow at hillslope scale is pragmatic and has produced a working operational system (National Water Model). But it leaves real physics on the table:

### 4.1 The disaggregation seam

Noah-MP computes soil moisture at ~1–4 km. WRF-Hydro disaggregates that single value to the 100 m routing grid using a time-step-weighted mapping. The lateral routing operates on the fine grid, then aggregates back. The disaggregation step assumes **uniform moisture within the LSM cell** — the very assumption that hillslope-scale lateral flow is supposed to break. Information about within-cell heterogeneity is lost at the seam and can only be recovered statistically.

### 4.2 Saturated-zone-only lateral flow

WRF-Hydro's subsurface routing only moves water in the saturated portion of the column. In humid vegetated terrain, a large fraction of lateral transport actually happens as **interflow in the wet-but-unsaturated zone** — water moving laterally through wet soils above a restrictive layer (bedrock contact, fragipan, organic-mineral boundary) without full saturation. Storm stormflow and the fast recession tail of hydrographs are often interflow-dominated. WRF-Hydro misses this mechanism entirely.

### 4.3 Column-lumped subsurface bucket

The saturated portion is treated as a single bucket per column. Per-Noah-MP-layer lateral flow (e.g., perched lateral flow above a compact subsoil) cannot be represented. This also means lateral flow has no way to affect root-zone soil moisture directly — it can only do so through the saturation state of the overall column.

### 4.4 LSM blind to lateral feedback within its own timestep

Noah-MP runs, completes, and hands off column fluxes. Lateral redistribution happens after Noah-MP finishes. The updated soil moisture only reaches Noah-MP at the next timestep, so within-timestep coupling (e.g., lateral redistribution → immediately modified ET → immediately modified energy balance) is not possible. For short Noah-MP timesteps (minutes) this is minor; for longer coupling intervals the loss is real.

### 4.5 Scale mismatch in parameterizations

Noah-MP's column parameterizations (canopy, radiation, turbulence, stomatal resistance) were calibrated at km-scale. WRF-Hydro's routing is at 100 m. The mapping treats every sub-cell routing pixel as sharing the same Noah-MP column state, which is reasonable for energy fluxes but increasingly wrong for topographically-varying water balance.

### 4.6 Where it matters most

These limitations are largest in:

- Humid, forested, steep terrain (NZ, Pacific Northwest, Appalachian, Alpine)
- Systems with shallow restrictive layers driving interflow
- Mountain riparian zones with strong ridge-valley moisture contrasts
- Seasonal-scale baseflow and drought-persistence studies

They are smaller in flat, arid, or Hortonian-dominated landscapes, where overland flow is the dominant redistribution process and WRF-Hydro's overland-flow module captures it well.

---

## 5. The Opportunity: Subgrid Hillslope Structure in Noah-MP (Path C)

Two dead-end alternatives set the stage:

- **Path A (status quo)** — leave routing outside. Accepts the limitations above.
- **Path B (hyperresolution)** — run Noah-MP itself at 100 m. Solves the grid mismatch but breaks parameterizations calibrated at km-scale, is 100–1600× more expensive, and creates a new mismatch against km-scale atmospheric forcing.

**Path C** is the emerging elegant alternative: represent each LSM grid cell as a **chain of hillslope position classes (HRUs / sub-columns)**, each running Noah-MP column physics, connected by lateral flow. The LSM stays at its natural atmospheric scale; hillslope-scale lateral redistribution happens **inside** the LSM cell using sub-column structure derived from high-resolution topography.

### 5.1 Reference implementation: CLM5 hillslope hydrology

Swenson et al. (2019, *JAMES*) implemented this in CLM5. Each grid cell contains up to ~5 HRUs representing hillslope positions (e.g., summit, shoulder, backslope, footslope, toeslope). Each HRU:

- Covers a distinct elevation band / topographic position within the cell
- Carries its own soil column, canopy, snowpack, energy balance
- Is connected to its down-chain neighbor by a lateral subsurface flow equation (kinematic-wave or similar)
- Receives atmospheric forcing from the parent LSM cell (possibly topographically adjusted)
- Produces area-weighted surface fluxes that feed back to the atmosphere

The per-cell hillslope geometry (number of HRUs, area fractions, hillslope length, slope, connection topology) is derived once offline from a high-res DEM and stored as a static input file.

Benefits:

- Captures ridge-valley moisture contrast inside the LSM timestep
- Retains column parameterizations at their validated scale
- Computational cost is O(N_HRU) per cell — typically 3–5× a standard column, not 100× or 1600×
- No disaggregation seam — lateral flow and column physics share the same timestep and the same spatial discretization

Open-source CLM5 code in the CTSM repository is a practical template.

### 5.2 Other relevant references

- **HydroBlocks** (Chaney et al.) — clusters hillslope pixels by hydrological similarity rather than explicit position chains, cheaper and scales to large domains.
- **tRIBS-VEGGIE** — TIN-based multi-scale model with explicit hillslope representation.
- **Meng, Jin, Zhang (2023)**, *J. Hydrology 620:129410* — simpler per-layer Darcy lateral term inside Noah-MP. More incremental than Path C but a useful halfway step; relevant reference for the within-Richards lateral term.
- **Zhang et al. (2024)**, *Hydrological Processes*, doi:10.1002/hyp.70021 — lateral flow scheme in the Noah-MP inside WRF-Hydro specifically. Closest to what we want.

None of these are in the NCAR mainline Noah-MP.

---

## 6. Rough Implementation Plan for Path C in Noah-MP

What a working Noah-MP + subgrid hillslope implementation would need. This is a sketch, not a design document — every item below would need to be worked out concretely before coding.

### 6.1 Inputs: hillslope geometry file

Offline pre-processing from a high-res DEM (30 m or finer) to produce, per LSM grid cell:

- `N_HRU` — number of hillslope position classes in this cell (fixed, e.g., 5, or variable up to a max)
- Per HRU: `area_fraction`, `elevation`, `slope`, `aspect`, `hillslope_length`, `down_neighbor_index` (which HRU in the cell this one drains to; toeslope drains to the channel / grid cell outlet)
- Per HRU: dominant soil type, land cover, vegetation (inherited from high-res maps)
- Optional: topographic wetness index, curvature, contributing area

Stored as a NetCDF static input (`hrldas.HILLSLOPE.nc` or added to `geo_em`).

### 6.2 Data structures

Noah-MP's existing arrays are dimensioned `(ids:ide, jds:jde, ...)` — per LSM cell. Path C requires a fourth dimension for HRU:

```
! New dimension: N_HRU per cell, ragged or padded to max
! Existing:
REAL, DIMENSION(ims:ime, 1:num_soil_layers, jms:jme) :: SMOIS
! New:
REAL, DIMENSION(ims:ime, 1:num_soil_layers, jms:jme, 1:max_hru) :: SMOIS_hru
REAL, DIMENSION(ims:ime, jms:jme, 1:max_hru) :: area_frac_hru, ...
```

This would be a sweeping change — every Noah-MP state variable needs an HRU index, and every loop that iterates over soil/column state needs to also iterate over HRU.

Registry changes in WRF: add `HRU` as a dimension in `Registry/Registry.EM`, define per-HRU state variables. This is similar in scope to how WRF handles nested-domain variables.

### 6.3 Column physics per HRU

Inside each LSM cell, for each HRU, call the existing `noahmplsm()` once with that HRU's area, slope, soil, vegetation, and state. Each HRU advances its own 1D column physics for the full timestep.

Atmospheric forcing is applied from the parent LSM cell, optionally topographically adjusted (e.g., lapse-rate temperature correction for elevation, radiation slope/aspect correction).

### 6.4 Lateral flow between HRUs

After each HRU has advanced its column physics, apply lateral subsurface flow between connected HRUs. Following CLM5:

For each HRU `i` with down-neighbor `j`:

$$Q_{ij} = K_{lat}(\theta_i) \cdot w_{ij} \cdot \frac{z_i - z_j}{L_{ij}}$$

where `K_lat` is the saturated hydraulic conductivity (optionally θ-dependent for interflow), `w_ij` is the connecting width, and `z_i - z_j` / `L_ij` is the hydraulic gradient (elevation or water table slope).

Apply the resulting lateral flux as a per-layer source/sink, possibly distributed across layers by saturation state. Solve for the updated `SMOIS_hru` in all HRUs simultaneously (tridiagonal in the hillslope chain direction, since each HRU has one upstream and one downstream connection).

Overland flow between HRUs follows an analogous kinematic-wave scheme driven by surface head.

### 6.5 Aggregation back to the LSM cell

Surface fluxes (`HFX`, `QFX`, `LH`, `SH`, `ALBEDO`, `TSK`) are aggregated as area-weighted sums over HRUs to produce the grid-cell values needed by WRF's atmosphere:

```
HFX(i,j) = Σ_hru area_frac_hru(i,j,hru) × HFX_hru(i,j,hru)
```

This is the one-way communication back to WRF's radiation, PBL, and surface layer schemes.

### 6.6 Interface with WRF-Hydro

The toeslope HRU in each cell is the "outlet" — its `INFXSRT`, `soldrain`, `sfcheadrt` fluxes are what WRF-Hydro's routing sees. Channel routing then proceeds as today. Overland flow and (optionally) saturated subsurface routing on the WRF-Hydro routing grid become redundant *within* a cell (since Path C handles it), but are still needed *between* cells unless the hillslope chains are stitched across cell boundaries.

One architectural choice: either (a) let WRF-Hydro handle everything between cells as today, treating each LSM cell as a lumped source; or (b) extend the HRU chain across cell boundaries and let Path C handle all lateral flow, retaining WRF-Hydro only for channel routing and reservoirs. Option (b) is cleaner but requires halo/ghost-cell communication across MPI domain decomposition.

### 6.7 Computational cost

Per-timestep cost scales as `N_HRU` times current Noah-MP cost. With `N_HRU = 5` the LSM roughly quintuples. In a typical WRF simulation the LSM is a small fraction of total runtime (dynamics and radiation dominate), so overall cost increase is usually 20–40%. The hillslope geometry preprocessing is a one-time offline cost.

### 6.8 Validation strategy

- **Conservation**: total water and energy conserved summed over HRUs in each cell. Trivial instrumented test.
- **Reduction to column**: with `N_HRU = 1`, results must be bit-identical to standard Noah-MP. First smoke test.
- **Analytical hillslope**: match Boussinesq or Philip infiltration solutions on idealized hillslopes. Unit test.
- **Observational sites**: HRU soil moisture at SCAN/SNOTEL stations or cosmic-ray neutron sensor networks that resolve hillslope positions.
- **Streamflow**: compare streamflow at outlets against gauge records for basins with high-quality DEM and long records.
- **Coupled**: verify that the improved soil moisture heterogeneity propagates into latent heat flux and PBL moisture as documented in the WRF-Hydro literature.

### 6.9 Effort estimate

- **Hillslope preprocessing tool**: 2–4 weeks (Python, builds on existing tools like TauDEM, pysheds)
- **Registry and data structure changes in WRF**: 2–3 weeks
- **Noah-MP HRU loop and lateral flow**: 4–6 weeks (bulk of the work, including testing)
- **WRF-Hydro interface updates**: 2 weeks
- **Validation and benchmarking**: 4–8 weeks

Total: 3–5 months for a competent developer familiar with WRF and Noah-MP. A first functional prototype (single-domain, serial, no WRF-Hydro) could be standing up in 6–8 weeks.

The scope is larger than the WVT integration in this repo (~10k lines, ~2 months of focused work per the WVT porting notes) but of comparable complexity. A worthwhile investment if shallow hillslope hydrology is central to the research agenda.

---

## 7. Relationship to This Repository

This repository already ships a coupled `wrf-wps-hydro-coupled` build with `WRF_HYDRO=1`, which gets you Path A (status quo) with the full WRF-Hydro routing stack including subsurface lateral flow (saturated only). For most applications this is the right tool.

Path C would be a separate, more invasive build with significant Noah-MP source changes. If pursued, it would likely live as a new image alongside the existing ones (`wrf-wps-hydro-hillslope` or similar), not as a modification to the existing build.

The WVT (Water Vapor Tracers) work in `wrf-wps-intel-wvt` is architecturally analogous: adding a new dimension (tracers there, HRUs here) to existing state variables, threading through the physics drivers, validating against a reference. The WVT porting notes (`wvt-porting-notes.md`) and integration guide (`wvt-integration-guide.md`) are useful references for how to approach a similar-scale modification to the WRF code base.

---

## References

- Niu, G.-Y., et al. (2011). The community Noah land surface model with multiparameterization options (Noah-MP): 1. Model description and evaluation with local-scale measurements. *JGR: Atmospheres*, 116, D12109.
- Fan, Y., et al. (2007). Incorporating water table dynamics in climate modeling: 1. Water table observations and equilibrium water table simulations. *JGR: Atmospheres*, 112, D10125.
- Miguez-Macho, G., et al. (2007). Incorporating water table dynamics in climate modeling: 2. Formulation, validation, and soil moisture simulation. *JGR: Atmospheres*, 112, D13108.
- Swenson, S. C., et al. (2019). Representing intra-hillslope lateral subsurface flow in the Community Land Model. *JAMES*, 11, 4044–4065.
- Chaney, N. W., et al. (2016). HydroBlocks: a field-scale resolving land surface model for application over continental extents. *Hydrological Processes*, 30, 3543–3559.
- Meng, C., Jin, H., Zhang, W. (2023). Lateral terrestrial water flow schemes for the Noah-MP land surface model on both natural and urban land surfaces. *J. Hydrology*, 620, 129410.
- Zhang, et al. (2024). Developing a Lateral Terrestrial Water Flow Scheme to Improve the Representation of Land Surface Hydrological Processes in the Noah-MP of WRF-Hydro. *Hydrological Processes*, doi:10.1002/hyp.70021.
- He, C., et al. (2023). Modernizing the open-source community Noah-MP land surface model (version 5.0). *GMD*, 16, 5131–5155.
- Gochis, D. J., et al. (2020). The WRF-Hydro Modeling System Technical Description, Version 5.2. NCAR.
- Arnault, J., et al. (2016). Role of runoff-infiltration partitioning and resolved overland flow on land-atmosphere feedbacks. *JGR: Atmospheres*, 121.
