#!/usr/bin/env python3
"""Stage 1c validation: per-region WSM6 tracer precip + cross-region clipping.

(1) region-2 sourced: TR_RAINNC(:,2,:) non-zero.
(2) linearity: sum_regions(N=2 TR_RAINNC) reproduces N=1 full-ocean TR_RAINNC.
(3) conservation: sum_regions TR_RAINNC <= RAINNC pointwise; sum_n tr_qv <= qv.
"""
import numpy as np
import h5netcdf

def load(p, v):
    with h5netcdf.File(p, 'r') as f:
        return np.asarray(f[v][:])

P2 = '/work/out/wrfout_1c_n2.nc'
P1 = '/work/out/wrfout_1c_n1.nc'

tr2 = load(P2, 'TR_RAINNC')     # (Time, wvt_regions=2, sn, we)
rain2 = load(P2, 'RAINNC')      # (Time, sn, we)
tr1 = load(P1, 'TR_RAINNC')     # (Time, 1, sn, we)

print(f'TR_RAINNC N=2 shape {tr2.shape} ; N=1 shape {tr1.shape}')
for n in range(tr2.shape[1]):
    s = tr2[:, n]
    print(f'  region {n+1}: max={float(np.nanmax(s)):.5g} mean={float(np.nanmean(s)):.5g} nonzero={int((np.abs(s)>0).sum())}')

reg2_max = float(np.nanmax(tr2[:, 1]))
print(f'\n(1) region-2 SOURCED (max>0): {reg2_max>0}  (max={reg2_max:.5g})')

n2_sum = tr2.sum(axis=1)        # (Time, sn, we)
n1_full = tr1[:, 0]             # (Time, sn, we)
d = np.abs(n2_sum - n1_full)
denom = np.abs(n1_full) + 1e-9
rel = (d / denom)[n1_full > 1e-6]
print(f'(2) linearity  sum_regions(N=2) vs N=1 full:')
print(f'      max|abs diff| = {float(d.max()):.3e} ; mean|abs diff| = {float(d.mean()):.3e}')
print(f'      N=2 sum total = {float(n2_sum.sum()):.6g} ; N=1 full total = {float(n1_full.sum()):.6g}')
if rel.size:
    print(f'      max rel diff (where N1>1e-6) = {float(rel.max()):.3e}')

excess = n2_sum - rain2
print(f'(3) conservation  sum_regions TR_RAINNC <= RAINNC:')
print(f'      max(sum_tr - RAINNC) = {float(excess.max()):.3e}  (<=0 ideal; tracer precip uses uncapped density)')

# vapor conservation
try:
    qv2 = load(P2, 'QVAPOR')
    qtr = sum(load(P2, f'qv_tr' if n == 0 else f'qv_tr_{n+1:02d}') for n in range(tr2.shape[1]))
    ex = qtr - qv2
    print(f'      max(sum_n qv_tr - QVAPOR) = {float(ex.max()):.3e}  (<=0 ideal)')
except Exception as e:
    print(f'      (qv conservation skipped: {e})')
