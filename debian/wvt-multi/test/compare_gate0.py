#!/usr/bin/env python3
"""Gate 0: the 12-region build at boundary_faces=[] must reproduce the 8-region build exactly.

Compares every shared variable in every matching wrfout, bit-for-bit. This isolates the
mechanical cap raise (8 -> 12) from the relabel: at num_wvt_bdy_regions = 0 the new block
never executes, and the added Registry members are never referenced, so any difference here
means the cap raise changed something it should not have.
"""
import glob, os, sys
import h5netcdf, numpy as np

A = sys.argv[1] if len(sys.argv) > 1 else '/tmp/wvt_rt_test/g0_base'
B = sys.argv[2] if len(sys.argv) > 2 else '/tmp/wvt_rt_test/g0_new'
fa = sorted(glob.glob(os.path.join(A, 'wrfout_d01_*')))
fb = sorted(glob.glob(os.path.join(B, 'wrfout_d01_*')))
if not fa or len(fa) != len(fb):
    sys.exit(f'FAIL: file count differs: {len(fa)} vs {len(fb)}')

EXPECTED_NONZERO_EXTRAS = {'TRMASK'}

worst, worst_var, nvars, ndiff = 0.0, None, 0, 0
problems = []

for pa, pb in zip(fa, fb):
    tag = os.path.basename(pa)
    with h5netcdf.File(pa, 'r') as A_, h5netcdf.File(pb, 'r') as B_:
        shared = sorted(set(A_.variables) & set(B_.variables))
        only_a = sorted(set(A_.variables) - set(B_.variables))
        only_b = sorted(set(B_.variables) - set(A_.variables))

        # A variable the new build DROPPED is a regression, not a note. Previously these were
        # printed and the run still reported OK -- a bad Registry merge losing QVAPOR would
        # have passed (both arms, round wvt-bdytags-code-2).
        if only_a:
            problems.append(f'{tag}: variables MISSING from the new build: {only_a}')

        # Extras are expected (regions 9-12 declared but inactive) -- but only if they are
        # identically zero. "I checked that by hand" is not a gate.
        #
        # EXPECTED_NONZERO_EXTRAS is the one deliberate exception: TRMASK was moved into the
        # history stream (Registry io i8r -> i8rh) so a run records which mask it actually
        # used. It is a new DIAGNOSTIC OUTPUT, not a change in model state, and it is
        # legitimately non-zero. Anything else appearing non-zero is a regression. Keep this
        # list minimal and justified -- it is the only hole in this check.
        for v in only_b:
            if v in EXPECTED_NONZERO_EXTRAS:
                continue
            y = np.asarray(B_[v])
            if y.dtype.kind in 'fiu' and y.size:
                mx = float(np.nanmax(np.abs(y.astype('f8'))))
                if not np.all(np.isfinite(y.astype('f8'))):
                    problems.append(f'{tag}: extra variable {v} contains non-finite values')
                elif mx != 0.0:
                    problems.append(f'{tag}: extra variable {v} is NOT zero (max |.| = {mx:.3e})')

        for v in shared:
            x, y = np.asarray(A_[v]), np.asarray(B_[v])
            if x.shape != y.shape:
                problems.append(f'{tag}: {v} shape {x.shape} vs {y.shape}')
                continue
            if x.dtype.kind not in 'fiu':
                continue
            nvars += 1
            xf, yf = x.astype('f8'), y.astype('f8')
            # NaN handling is the point: d.max() is NaN if any element is NaN, and NaN > 0 is
            # False, so a NaN introduced by the new build used to read as "identical".
            nan_a, nan_b = np.isnan(xf), np.isnan(yf)
            if not np.array_equal(nan_a, nan_b):
                problems.append(f'{tag}: {v} NaN pattern differs '
                                f'({int(nan_a.sum())} vs {int(nan_b.sum())} NaNs)')
                ndiff += 1
                continue
            d = np.abs(np.where(nan_a, 0.0, xf) - np.where(nan_b, 0.0, yf))
            m = float(d.max()) if d.size else 0.0
            if m > 0:
                ndiff += 1
                if m > worst:
                    worst, worst_var = m, f'{tag}:{v}'
    print(f'{tag}: {len(shared)} shared'
          + (f'  MISSING={only_a}' if only_a else '')
          + (f'  extra={len(only_b)} (checked zero)' if only_b else ''))

print(f'\ncompared {nvars} numeric variable instances; {ndiff} differ')
if worst_var:
    print(f'worst finite difference: {worst:.6e} in {worst_var}')
if problems or worst_var:
    print('\nFAIL: gate 0')
    for x in problems:
        print('  ' + x)
    sys.exit(1)
print('\nOK: gate 0 -- bit-for-bit identical at 8 regions')
