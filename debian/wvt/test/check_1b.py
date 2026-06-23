#!/usr/bin/env python3
"""Stage 1b check: both regions now sourced (region-2 PWAT_TR becomes non-zero)."""
import numpy as np
import h5netcdf

P = '/tmp/wvt_rt_test/out/wrfout_1b_n2.nc'
with h5netcdf.File(P, 'r') as f:
    pt = np.asarray(f['PWAT_TR'][:])          # (Time, wvt_regions, sn, we)
    pwat = np.asarray(f['PWAT'][:])           # (Time, sn, we) total column
    print(f'PWAT_TR shape = {pt.shape}')
    for n in range(pt.shape[1]):
        sl = pt[:, n]
        print(f'  region {n+1}: min={float(np.nanmin(sl)):.5g} max={float(np.nanmax(sl)):.5g} '
              f'mean={float(np.nanmean(sl)):.5g}  nonzero_cells={int((np.abs(sl)>0).sum())}')
    tot = pt.sum(axis=1)                       # region 1 + region 2
    print(f'\nregion1+region2 PWAT_TR: max={float(np.nanmax(tot)):.5g} mean={float(np.nanmean(tot)):.5g}')
    print(f'total-ocean tagged fraction (sum_tr / PWAT) mean = '
          f'{float(np.nanmean(tot)/max(np.nanmean(pwat),1e-9)):.4f}')
    print(f'\nregion 2 now SOURCED (max>0): {float(np.nanmax(pt[:,1]))>0}')
