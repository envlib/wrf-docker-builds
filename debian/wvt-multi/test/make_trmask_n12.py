#!/usr/bin/env python3
"""Region-dimensioned trmask_d01 for the 12-region lateral-boundary-tag test.

8 source regions (disjoint ocean strips, margin zeroed) + 4 boundary face shells = 12.

The shell geometry is IMPORTED from wrf-auto-runs/create_trmask.py rather than reimplemented
here. That is the point: a harness that re-derives the geometry can agree with itself while
disagreeing with the code that actually ships, and the run would still look healthy. Importing
the production function means this test exercises the real thing.

Run on the HOST with the wrf-auto-runs uv env (h5netcdf + scipy + numpy), e.g.

    WVT_AUTO_RUNS=~/git/wrf-repos/wrf-auto-runs/wrf-auto-runs \
    uv run --project ~/git/wrf-repos/wrf-auto-runs python make_trmask_n12.py
"""
import importlib.util
import os
import sys
import types

import h5netcdf
import numpy as np
import scipy.io.netcdf as nc3

GEO = os.environ.get('WVT_TEST_DATA', os.path.expanduser('~/data/wrf/test_data')) + '/geo_em.d01.nc'
OUT = os.environ.get('WVT_TEST_WORK', '/tmp/wvt_rt_test') + '/trmask_d01'
AUTO_RUNS = os.environ.get(
    'WVT_AUTO_RUNS', os.path.expanduser('~/git/wrf-repos/wrf-auto-runs/wrf-auto-runs'))
START = '2023-02-10_00:00:00'
RELAX = 5          # must equal spec_bdy_width in namelist.input.n12
N_SRC = 8          # source regions -> indices 1..8
# 0 disables the shells, giving the pure 8-region baseline mask for gate 0. The eight
# source strips are computed identically either way, so the baseline and the 12-region
# run differ ONLY by the presence of the shells.
N_FACES = int(os.environ.get('WVT_TEST_FACES', len(('west', 'east', 'south', 'north'))))
START_DATE = START


def _load_create_trmask():
    """Import create_trmask without its params side-effects (needs a parameters.toml)."""
    sys.modules.setdefault('params', types.ModuleType('params'))
    sys.modules['params'].file = {}
    spec = importlib.util.spec_from_file_location(
        'create_trmask', os.path.join(AUTO_RUNS, 'create_trmask.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ct = _load_create_trmask()

with h5netcdf.File(GEO, 'r') as f:
    lat = np.asarray(f['XLAT_M'][0])
    lon = np.asarray(f['XLONG_M'][0])
    landmask = np.asarray(f['LANDMASK'][0])
    mminlu = f.attrs.get('MMINLU', 'MODIFIED_IGBP_MODIS_NOAH')
    num_land_cat = int(f.attrs.get('NUM_LAND_CAT', 21))
if isinstance(mminlu, bytes):
    mminlu = mminlu.decode()

sn, we = lat.shape

# --- regions 1..8: disjoint ocean strips with the margin zeroed, exactly as production does
ocean = (1.0 - landmask).astype('f4')
ocean[:RELAX, :] = 0
ocean[-RELAX:, :] = 0
ocean[:, :RELAX] = 0
ocean[:, -RELAX:] = 0

faces = ct.BOUNDARY_FACES[:N_FACES]
masks = np.zeros((N_SRC + len(faces), sn, we), dtype='f4')
bnd = np.linspace(0, we, N_SRC + 1).astype(int)
for k in range(N_SRC):
    strip = np.zeros((sn, we), dtype='f4')
    strip[:, bnd[k]:bnd[k + 1]] = 1.0
    masks[k] = ocean * strip

# --- regions 9..12: the face shells, from the production geometry
for k, face in enumerate(faces):
    masks[N_SRC + k] = ct._build_boundary_mask(face, RELAX, we, sn, f'{face}_face')

# --- invariants, asserted here so a broken mask never reaches the model
margin = np.zeros((sn, we), dtype=bool)
margin[:RELAX, :] = margin[-RELAX:, :] = True
margin[:, :RELAX] = margin[:, -RELAX:] = True

coverage = (masks > 0).sum(axis=0)
assert coverage.max() <= 1, f'regions overlap on {(coverage > 1).sum()} cell(s)'

if faces:
    shell_union = (masks[N_SRC:] > 0).any(axis=0)
    assert np.array_equal(shell_union, margin), 'shells do not exactly tile the margin'
assert not (masks[:N_SRC] > 0).any(axis=0)[margin].any(), 'a source region reaches into the margin'

src_counts = [int(masks[k].sum()) for k in range(N_SRC)]
shell_counts = [int(masks[N_SRC + k].sum()) for k in range(len(faces))]
if min(src_counts) == 0:
    print(f'NOTE: {src_counts.count(0)} source strip(s) are all-land and will source nothing',
          file=sys.stderr)

nreg = masks.shape[0]
f = nc3.netcdf_file(OUT, 'w', version=1)
f.createDimension('Time', None)
f.createDimension('wvt_regions', nreg)
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

print(f'wrote {OUT}: {nreg} regions on {sn}x{we}, relax={RELAX}')
print(f'  sources 1..{N_SRC} (ocean cells): {src_counts}')
if faces:
    print(f'  shells  {N_SRC + 1}..{nreg} {list(faces)}: {shell_counts}'
          f'  (margin = {int(margin.sum())}, tiled exactly)')
else:
    print('  no shells (8-region baseline for gate 0)')
