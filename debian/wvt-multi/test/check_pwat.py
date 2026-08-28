#!/usr/bin/env python3
"""Confirm PWAT_TR is region-dimensioned: region 1 sourced (>0), region 2 inert (==0)."""
import numpy as np
import h5netcdf
import os

P = os.environ.get('WVT_TEST_WORK', '/tmp/wvt_rt_test') + '/out/wrfout_p1n2.nc'
with h5netcdf.File(P, 'r') as f:
    for v in ['PWAT_TR', 'VIMF_TR_U', 'PWAT']:
        if v in f.variables:
            var = f[v]
            print(f'{v}: dims={var.dimensions}  shape={var.shape}')
    pt = np.asarray(f['PWAT_TR'][:])  # expect (Time, wvt_regions, sn, we)
    print()
    print(f'PWAT_TR shape = {pt.shape}  (region dim present = {pt.ndim == 4})')
    if pt.ndim == 4:
        nreg = pt.shape[1]
        for n in range(nreg):
            sl = pt[:, n, :, :]
            print(f'  region {n+1}: min={float(np.nanmin(sl)):.6g}  max={float(np.nanmax(sl)):.6g}  '
                  f'mean={float(np.nanmean(sl)):.6g}')
        print()
        print(f'region 1 max > 0 (sourced): {float(np.nanmax(pt[:,0])) > 0}')
        print(f'region 2 all zero (inert):  {float(np.nanmax(np.abs(pt[:,1]))) == 0}')
