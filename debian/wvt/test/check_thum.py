#!/usr/bin/env python3
"""tr_thum validation: per-region total-humidity moisture-flux diagnostics.

Reuses the N=2 (west+east) vs N=1 (full ocean) wrfouts from run_1c.sh.

tr_thum_{u,v}_phy_dt accumulates sum(tagged species) * wind * dt. Single-region summed ALL
regions; now region n sums only its 6 species into tr_thum_{u,v}_phy_dt_0n (region 1 = unsuffixed).

Checks (per the linearity invariant Σ_regions(N=2) == N=1 full ocean):
  region-2 SOURCED : tr_thum_*_02 non-zero.
  linearity        : tr_thum_u (N1 full) == tr_thum_u(N2) + tr_thum_u_02(N2)  (and v).
"""
import os
import numpy as np
import h5netcdf

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
P2 = os.path.join(_OUT, 'wrfout_1c_n2.nc')
P1 = os.path.join(_OUT, 'wrfout_1c_n1.nc')


def load(p, v):
    with h5netcdf.File(p, 'r') as f:
        return np.asarray(f[v][:])


for comp in ('U', 'V'):
    base = f'TR_THUM_{comp}_PHY_DT'   # WRF writes state-field names uppercased
    r1 = load(P2, base)            # N=2 region 1 (west)
    r2 = load(P2, base + '_02')    # N=2 region 2 (east)
    full = load(P1, base)          # N=1 full ocean
    n2sum = r1 + r2
    d = np.abs(n2sum - full)
    denom = np.abs(full) + 1e-30
    rel = (d / denom)[np.abs(full) > np.abs(full).max() * 1e-4]
    print(f'tr_thum_{comp}_phy_dt:')
    print(f'  region1 max|.|={float(np.abs(r1).max()):.4g}  region2 max|.|={float(np.abs(r2).max()):.4g} '
          f'nonzero2={int((np.abs(r2)>0).sum())}  -> region-2 SOURCED: {float(np.abs(r2).max())>0}')
    print(f'  linearity Σ(N2) vs N1: max|diff|={float(d.max()):.3e}  '
          f'sum(N2)={float(n2sum.sum()):.6g}  sum(N1)={float(full.sum()):.6g}'
          + (f'  max_rel(>0.01·peak)={float(rel.max()):.3e}' if rel.size else ''))
