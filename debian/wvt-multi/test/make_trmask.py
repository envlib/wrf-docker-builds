#!/usr/bin/env python3
"""Region-dimensioned trmask_d01 for the multi-region WVT test.

Writes TRMASK(Time, wvt_regions, south_north, west_east) -- the i{wvtreg}j layout WRF's
auxinput8 reads into grid%trmask(i,n,j). Ocean (1-LANDMASK, relax zone zeroed) is partitioned
into NREG disjoint longitudinal strips, so the strips are disjoint and their union is the full
tagged ocean (enabling the qv_tr + qv_tr_02 == single-all-ocean linearity check). Run with the
wrf-auto-runs uv env (h5netcdf + scipy.io.netcdf).
"""
import numpy as np
import h5netcdf
import scipy.io.netcdf as nc3

GEO = '/home/mike/data/wrf/test_data/geo_em.d01.nc'
OUT = '/tmp/wvt_rt_test/trmask_d01'
START = '2023-02-10_00:00:00'
RELAX = 5
NREG = 2

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

# NREG disjoint longitudinal (west-east) ocean strips
masks = np.zeros((NREG, sn, we), dtype='f4')
bnd = np.linspace(0, we, NREG + 1).astype(int)
for k in range(NREG):
    strip = np.zeros((sn, we), dtype='f4')
    strip[:, bnd[k]:bnd[k + 1]] = 1.0
    masks[k] = ocean * strip

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
print(f'wrote {OUT}: {NREG} regions, {sn}x{we}, ocean cells per region = {[int(masks[k].sum()) for k in range(NREG)]}')
