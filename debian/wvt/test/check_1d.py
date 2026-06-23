#!/usr/bin/env python3
"""Stage 1d-b validation: per-region convective (cu_ntiedtke) tracer column transport.

Reuses the N=2 (west+east) vs N=1 (full ocean) wrfouts from run_1c.sh.

1d-a tagged convective PRECIP (TR_RAINC) but DISCARDED the convective column transport
(RTRQ*CUTEN) for regions 2..N. 1d-b stores + couples + applies + decouples per-region
RTRQ*CUTEN_0n so regions 2..N's tagged qv/qc/qi get convectively transported too.

Checks (all per the linearity invariant: sum_regions(N=2) == N=1 full ocean):
  (A) convection ACTIVE   : max(RAINC) > 0  -> the 1d-b cumulus path is actually exercised.
  (B) qv_tr LINEARITY      : sum_n qv_tr(N=2) == qv_tr(N=1).  <-- the stringent 1d-b signal:
        if region-2 convective transport were still discarded (1d-a), this breaks in
        convective columns. Holding tightly => region-2 transport correctly applied.
  (C) TR_RAINC  (1d-a)     : region-2 sourced + linearity + conservation (no regression).
  (D) TR_RAINNC (1c)       : region-2 sourced + linearity + conservation (no regression).
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


def has(p, v):
    with h5netcdf.File(p, 'r') as f:
        return v in f.variables


def linearity(name, n2_sum, n1_full, thresh=1e-6):
    d = np.abs(n2_sum - n1_full)
    denom = np.abs(n1_full) + 1e-12
    rel = (d / denom)[np.abs(n1_full) > thresh]
    print(f'  {name} linearity: max|diff|={float(d.max()):.3e}  '
          f'sum(N2)={float(n2_sum.sum()):.6g}  sum(N1)={float(n1_full.sum()):.6g}'
          + (f'  max_rel={float(rel.max()):.3e}' if rel.size else '  (no cells>thresh)'))
    return float(d.max())


# ---------- (A) convection active ----------
rainc2 = load(P2, 'RAINC')
print(f'(A) convection active: max(RAINC) N=2 = {float(rainc2.max()):.5g}  '
      f'mean = {float(rainc2.mean()):.5g}  -> {"ACTIVE" if rainc2.max() > 0 else "NONE (1d-b path not exercised!)"}')

# ---------- (B) qv_tr linearity (the 1d-b discriminator) ----------
print('\n(B) qv_tr (convectively-transported tracer) linearity:')
qv1 = load(P1, 'qv_tr')                                   # (Time, k, sn, we) full ocean
qv2_sum = load(P2, 'qv_tr') + load(P2, 'qv_tr_02')        # west + east
linearity('qv_tr', qv2_sum, qv1)
# magnitude of the tagged field (context for the diff scale)
print(f'      max(qv_tr N=1) = {float(qv1.max()):.5g}  total(qv_tr N=1) = {float(qv1.sum()):.6g}')

# ---------- (C) TR_RAINC convective precip (1d-a regression) ----------
print('\n(C) TR_RAINC (convective tagged precip, 1d-a):')
trc2 = load(P2, 'TR_RAINC')      # (Time, 2, sn, we)
trc1 = load(P1, 'TR_RAINC')      # (Time, 1, sn, we)
rc2 = load(P2, 'RAINC')
for n in range(trc2.shape[1]):
    s = trc2[:, n]
    print(f'    region {n+1}: max={float(s.max()):.5g} mean={float(s.mean()):.5g} nonzero={int((np.abs(s)>0).sum())}')
print(f'    region-2 SOURCED: {float(trc2[:,1].max())>0}')
linearity('TR_RAINC', trc2.sum(axis=1), trc1[:, 0])
print(f'    conservation max(sum_tr - RAINC) = {float((trc2.sum(axis=1) - rc2).max()):.3e}  (<=0 ideal)')

# ---------- (D) TR_RAINNC grid-scale precip (1c regression) ----------
print('\n(D) TR_RAINNC (grid-scale tagged precip, 1c):')
trn2 = load(P2, 'TR_RAINNC')
trn1 = load(P1, 'TR_RAINNC')
rn2 = load(P2, 'RAINNC')
for n in range(trn2.shape[1]):
    s = trn2[:, n]
    print(f'    region {n+1}: max={float(s.max()):.5g} mean={float(s.mean()):.5g} nonzero={int((np.abs(s)>0).sum())}')
print(f'    region-2 SOURCED: {float(trn2[:,1].max())>0}')
linearity('TR_RAINNC', trn2.sum(axis=1), trn1[:, 0])
print(f'    conservation max(sum_tr - RAINNC) = {float((trn2.sum(axis=1) - rn2).max()):.3e}  (<=0 ideal)')
