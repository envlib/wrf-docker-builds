#!/usr/bin/env python3
"""Region-dimensioned trmask_d01 for the lateral-boundary-tag tests, driven by a NAMELIST.

N_SRC disjoint ocean strips (margin zeroed) + N_BDY boundary face shells, where both counts and
the margin width come from the namelist the run will use -- so the mask and the namelist cannot
disagree by construction, and the 8-region gate-0 baseline is simply the same script pointed at
namelist.input.n8 (which omits num_wvt_bdy_regions; absent means 0, the binary's default).
This replaced the WVT_TEST_FACES env var on 2026-09-07: that variable was the only producer of
base/trmask_d01 and nothing recorded which namelist it was meant to match.

The shell geometry is IMPORTED from wrf-auto-runs/create_trmask.py rather than reimplemented
here. That is the point: a harness that re-derives the geometry can agree with itself while
disagreeing with the code that actually ships, and the run would still look healthy. Importing
the production function means this test exercises the real thing -- and the path of the module
actually loaded is printed, because "which create_trmask.py defined the geometry" is otherwise
invisible in the log.

Run on the HOST with the wrf-auto-runs uv env (h5netcdf + scipy + numpy + f90nml), e.g.

    WVT_AUTO_RUNS=~/git/wrf-repos/wrf-auto-runs/wrf-auto-runs \
    uv run --project ~/git/wrf-repos/wrf-auto-runs python make_trmask_n12.py

Environment:
  WVT_TEST_DATA      directory holding geo_em.d01.nc        (default ~/data/wrf/test_data)
  WVT_TEST_WORK      OUTPUT directory for trmask_d01         (default /tmp/wvt_rt_test)
  WVT_TEST_NAMELIST  the namelist to size the mask from      (default: namelist.input.n12 beside
                     this script -- NOT under WVT_TEST_WORK, which is where the output goes)
  WVT_AUTO_RUNS      the wrf-auto-runs package directory     (default ~/git/wrf-repos/wrf-auto-runs/wrf-auto-runs)
"""
import importlib.util
import os
import sys
import types

import f90nml
import h5netcdf
import numpy as np
import scipy.io.netcdf as nc3

HERE = os.path.dirname(os.path.abspath(__file__))
GEO = os.environ.get('WVT_TEST_DATA', os.path.expanduser('~/data/wrf/test_data')) + '/geo_em.d01.nc'
OUT = os.environ.get('WVT_TEST_WORK', '/tmp/wvt_rt_test') + '/trmask_d01'
NAMELIST = os.environ.get('WVT_TEST_NAMELIST', os.path.join(HERE, 'namelist.input.n12'))
AUTO_RUNS = os.environ.get(
    'WVT_AUTO_RUNS', os.path.expanduser('~/git/wrf-repos/wrf-auto-runs/wrf-auto-runs'))
START = '2023-02-10_00:00:00'


def _load_create_trmask():
    """Import create_trmask without its params side-effects (needs a parameters.toml).

    The stub is installed only if no real `params` module is already imported -- an earlier
    version overwrote whatever was there.
    """
    if 'params' not in sys.modules:
        stub = types.ModuleType('params')
        stub.file = {}
        sys.modules['params'] = stub
    if AUTO_RUNS not in sys.path:
        sys.path.insert(0, AUTO_RUNS)          # create_trmask does `import defaults`
    spec = importlib.util.spec_from_file_location(
        'create_trmask', os.path.join(AUTO_RUNS, 'create_trmask.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _scalar(v):
    return v[0] if isinstance(v, list) else v


ct = _load_create_trmask()
print(f'geometry from: {ct.__file__}')

nml = f90nml.read(NAMELIST)
RELAX = int(_scalar(nml['bdy_control']['spec_bdy_width']))
N_REG = int(_scalar(nml['dynamics']['num_wvt_regions']))
N_BDY = int(_scalar(nml['dynamics'].get('num_wvt_bdy_regions', 0)))   # absent == 0 (n8 baseline)
N_SRC = N_REG - N_BDY
if N_SRC < 1:
    sys.exit(f'FAIL: {NAMELIST}: num_wvt_regions={N_REG} leaves no source region after {N_BDY} face(s)')
print(f'namelist {NAMELIST}: spec_bdy_width={RELAX} num_wvt_regions={N_REG} num_wvt_bdy_regions={N_BDY}')

with h5netcdf.File(GEO, 'r') as f:
    lat = np.asarray(f['XLAT_M'][0])
    lon = np.asarray(f['XLONG_M'][0])
    landmask = np.asarray(f['LANDMASK'][0])
    mminlu = f.attrs.get('MMINLU', 'MODIFIED_IGBP_MODIS_NOAH')
    num_land_cat = int(f.attrs.get('NUM_LAND_CAT', 21))
if isinstance(mminlu, bytes):
    mminlu = mminlu.decode()

sn, we = lat.shape

# --- regions 1..N_SRC: disjoint ocean strips with the margin zeroed, exactly as production does
ocean = (1.0 - landmask).astype('f4')
ocean[:RELAX, :] = 0
ocean[-RELAX:, :] = 0
ocean[:, :RELAX] = 0
ocean[:, -RELAX:] = 0

faces = ct.BOUNDARY_FACES[:N_BDY]
masks = np.zeros((N_REG, sn, we), dtype='f4')
bnd = np.linspace(0, we, N_SRC + 1).astype(int)
for k in range(N_SRC):
    strip = np.zeros((sn, we), dtype='f4')
    strip[:, bnd[k]:bnd[k + 1]] = 1.0
    masks[k] = ocean * strip

# --- the face shells, from the production geometry
for k, face in enumerate(faces):
    masks[N_SRC + k] = ct._build_boundary_mask(face, RELAX, we, sn, f'{face}_face')

# --- invariants, asserted here so a broken mask never reaches the model. The margin below is
#     written as literal slices ON PURPOSE: it is the independent witness against
#     ct.margin_geometry, the same role tests/test_create_trmask.py:500 plays in wrf-auto-runs.
margin = np.zeros((sn, we), dtype=bool)
margin[:RELAX, :] = margin[-RELAX:, :] = True
margin[:, :RELAX] = margin[:, -RELAX:] = True

coverage = (masks > 0).sum(axis=0)
assert coverage.max() <= 1, f'regions overlap on {(coverage > 1).sum()} cell(s)'

if N_BDY:
    shell_union = (masks[N_SRC:] > 0).any(axis=0)
    assert np.array_equal(shell_union, margin), 'shells do not exactly tile the margin'
assert not (masks[:N_SRC] > 0).any(axis=0)[margin].any(), 'a source region reaches into the margin'

src_counts = [int(masks[k].sum()) for k in range(N_SRC)]
shell_counts = [int(masks[N_SRC + k].sum()) for k in range(N_BDY)]
if min(src_counts) == 0:
    print(f'NOTE: {src_counts.count(0)} source strip(s) are all-land and will source nothing',
          file=sys.stderr)

f = nc3.netcdf_file(OUT, 'w', version=1)
f.createDimension('Time', None)
f.createDimension('wvt_regions', N_REG)
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

print(f'wrote {OUT}: {N_REG} regions on {sn}x{we}, relax={RELAX}')
print(f'  sources 1..{N_SRC} (ocean cells): {src_counts}')
if N_BDY:
    print(f'  shells  {N_SRC + 1}..{N_REG} {list(faces)}: {shell_counts}'
          f'  (margin = {int(margin.sum())}, tiled exactly)')
else:
    print(f'  no shells ({N_REG}-region baseline, e.g. for gate 0)')
