#!/usr/bin/env python3
"""Gate 0: the 12-region build at boundary_faces=[] must reproduce the 8-region build exactly.

Compares every shared variable in every matching wrfout, bit-for-bit. This isolates the
mechanical cap raise (8 -> 12) from the relabel: at num_wvt_bdy_regions = 0 the new block
never executes, and the added Registry members are never referenced, so any difference here
means the cap raise changed something it should not have.
"""
import glob, os, sys
import h5netcdf, numpy as np

import argparse
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('A', nargs='?', default='/tmp/wvt_rt_test/g0_base')
ap.add_argument('B', nargs='?', default='/tmp/wvt_rt_test/g0_new')
ap.add_argument('--stream', default='wrfout', choices=['wrfout', 'wrfrst'],
                help='which files to compare (default wrfout)')
ap.add_argument('--expect-absent', metavar='FILE',
                help='names (one per line, case-insensitive) that the NEW build must NOT write: '
                     'Registry-packaged fields inactive for this namelist, from '
                     'wvt_expected_absent.py. Every listed name must be present in A and absent '
                     'from B; any OTHER variable missing from B is still a FAIL.')
args = ap.parse_args()
A, B = args.A, args.B
fa = sorted(glob.glob(os.path.join(A, f'{args.stream}_d01_*')))
fb = sorted(glob.glob(os.path.join(B, f'{args.stream}_d01_*')))
if not fa or len(fa) != len(fb):
    sys.exit(f'FAIL: file count differs: {len(fa)} vs {len(fb)}')

EXPECTED_NONZERO_EXTRAS = {'TRMASK'}
# 2026-09-18: a build that PACKAGES fields legitimately stops writing them. The list is
# generated from the Registry (wvt_expected_absent.py), never typed; and the check is two-sided:
# a listed name that is still written is as much a failure as an unlisted one that vanished.
expect_absent = set()
if args.expect_absent:
    expect_absent = {l.strip().lower() for l in open(args.expect_absent) if l.strip()}

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
        only_a_l = {v.lower() for v in only_a}
        unexpected_missing = sorted(v for v in only_a if v.lower() not in expect_absent)
        if unexpected_missing:
            problems.append(f'{tag}: variables MISSING from the new build: {unexpected_missing}')
        still_written = sorted(n for n in expect_absent
                               if n not in only_a_l and n in {v.lower() for v in B_.variables})
        if still_written:
            problems.append(f'{tag}: expected-absent variables STILL WRITTEN by the new build: {still_written}')
        not_in_a = sorted(n for n in expect_absent if n not in {v.lower() for v in A_.variables})
        if not_in_a:
            # Not a failure: some packaged fields are also namelist-conditional in the OLD build
            # (the I_* bucket counters are only written when bucket_mm > 0). A list for the wrong
            # stream or namelist shows up as unexpected-missing / still-written instead.
            print(f'{tag}: note -- {len(not_in_a)} expected-absent name(s) the old build never wrote '
                  f'for this namelist: {not_in_a}')

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
          + (f'  absent-as-expected={len(only_a)}' if only_a and not unexpected_missing else '')
          + (f'  MISSING={unexpected_missing}' if unexpected_missing else '')
          + (f'  extra={len(only_b)} (checked zero)' if only_b else ''))

print(f'\ncompared {nvars} numeric variable instances; {ndiff} differ')
if worst_var:
    print(f'worst finite difference: {worst:.6e} in {worst_var}')
if problems or worst_var:
    print('\nFAIL: gate 0')
    for x in problems:
        print('  ' + x)
    sys.exit(1)
print(f'\nOK: gate 0 -- bit-for-bit identical on every shared variable ({args.stream}); '
      f'{len(expect_absent)} expected-absent names verified absent')
