#!/usr/bin/env python3
"""1-region (full-ocean) trmask_d01 for the Stage-1c linearity test.

The single region equals the UNION of the 2-region (west+east) mask, so
sum_regions(N=2 TR_RAINNC) should reproduce N=1 TR_RAINNC. Run with the
wrf-auto-runs uv env (h5netcdf + scipy.io.netcdf).
"""
import numpy as np
import h5netcdf
import scipy.io.netcdf as nc3
import os

GEO = os.environ.get('WVT_TEST_DATA', os.path.expanduser('~/data/wrf/test_data')) + '/geo_em.d01.nc'
OUT = os.environ.get('WVT_TEST_WORK', '/tmp/wvt_rt_test') + '/trmask_1reg_d01'
START = '2023-02-10_00:00:00'
RELAX = 5
NREG = 1

with h5netcdf.File(GEO, 'r') as f:
    lat = np.asarray(f['XLAT_M'][0])
    lon = np.asarray(f['XLONG_M'][0])
    landmask = np.asarray(f['LANDMASK'][0])
    mminlu = f.attrs.get('MMINLU', 'MODIFIED_IGBP_MODIS_NOAH')
    num_land_cat = int(f.attrs.get('NUM_LAND_CAT', 21))
if isinstance(mminlu, bytes):
    mminlu = mminlu.decode()

sn, we = lat.shape
ocean = (1.0 - landmask).astype('f4')
ocean[:RELAX, :] = 0; ocean[-RELAX:, :] = 0
ocean[:, :RELAX] = 0; ocean[:, -RELAX:] = 0

masks = np.zeros((NREG, sn, we), dtype='f4')
masks[0] = ocean  # full ocean = union of the 2-region west+east strips

f = nc3.netcdf_file(OUT, 'w', version=1)
f.createDimension('Time', None)
f.createDimension('wvt_regions', NREG)
f.createDimension('south_north', sn)
f.createDimension('west_east', we)
f.createDimension('DateStrLen', 19)

v = f.createVariable('XLAT', 'f4', ('south_north', 'west_east'))
v[:] = lat.astype('f4'); v.FieldType = np.int32(104); v.MemoryOrder = 'XY '
v.description = 'LATITUDE SOUTH IS NEGATIVE'; v.units = 'degree_north'; v.stagger = ''

v = f.createVariable('XLONG', 'f4', ('south_north', 'west_east'))
v[:] = lon.astype('f4'); v.FieldType = np.int32(104); v.MemoryOrder = 'XY '
v.description = 'LONGITUDE WEST IS NEGATIVE'; v.units = 'degree_east'; v.stagger = ''

v = f.createVariable('TRMASK', 'f4', ('Time', 'wvt_regions', 'south_north', 'west_east'))
v[0, :, :, :] = masks; v.FieldType = np.int32(104); v.MemoryOrder = 'XYZ'
v.description = 'Tracer Source Mask (1 FOR SOURCE), per WVT region'; v.units = ''; v.stagger = ''
v.coordinates = 'XLONG XLAT'

v = f.createVariable('Times', 'c', ('Time', 'DateStrLen'))
s19 = START[:19].ljust(19, ' ')
for i, ch in enumerate(s19):
    v[0, i] = ch.encode('ascii')

f.TITLE = 'OUTPUT FROM WVT TRACER MASK GENERATOR V4.0'
f.START_DATE = START
f.MMINLU = mminlu
f.NUM_LAND_CAT = np.int32(num_land_cat)
f.close()
print(f'wrote {OUT}: {NREG} region (full ocean), {sn}x{we}, ocean cells = {int(masks[0].sum())}')
