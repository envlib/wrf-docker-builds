#!/usr/bin/env python3
"""Packaging gate for the Registry-packaged WVT build (2026-09-18): tracer-off AND tracer-on.

    check_notracer.py A B --num-wvt-regions 1 --tracer-opt 0 [--stage 1|2a] [--stream wrfout|wrfrst]

A = output directory of the pre-change build (same compiler flags), B = the packaged build,
same namelist. Asserts, per stream:
  1. every SHARED variable is bit-identical (compare_gate0.py's NaN-aware loop);
  2. the variables A wrote and B did not are EXACTLY the Registry-derived expected-absent set
     (wvt_expected_absent.py) -- two-sided: an unlisted disappearance and a listed survivor
     are both failures;
  3. B has nothing A lacks;
  4. (--stage 2a only) no WVT-named variable remains in B except the deferred Stage-2b names.
Stage 1 packages only the per-region _0N members, so 4 is not asserted there.
Runs the comparison as a subprocess of compare_gate0.py so there is one comparison loop, not two.
"""
import argparse, glob, os, subprocess, sys, tempfile
import h5netcdf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wvt_expected_absent  # noqa: E402


def wvt_names():
    """Every WVT state name, from the registry: the fields declared in registry.moisttracers,
    the *_TR diagnostics in registry.diag_columns, and the 4-D tracer members. A regex on
    'tr_' would also catch stock fields such as TR_URB (urban roof temperature)."""
    names = set()
    reg = wvt_expected_absent.REG
    for line in open(os.path.join(reg, 'registry.moisttracers')):
        t = line.split()
        if len(t) > 7 and t[0] == 'state':
            names.add(t[2].lower())
    for line in open(os.path.join(reg, 'registry.diag_columns')):
        t = line.split()
        if len(t) > 7 and t[0] == 'state' and '_tr' in t[2].lower():
            names.add(t[2].lower())
    for line in open(os.path.join(reg, 'Registry.EM')):
        t = line.split()
        if len(t) > 4 and t[0] == 'state' and t[4] == 'tracer':
            names.add(t[2].lower())
    return names


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('A'); ap.add_argument('B')
    ap.add_argument('--num-wvt-regions', type=int, required=True)
    ap.add_argument('--tracer-opt', type=int, required=True)
    ap.add_argument('--stage', choices=['1', '2a'], default='2a')
    ap.add_argument('--stream', choices=['wrfout', 'wrfrst'], default='wrfout')
    a = ap.parse_args()

    gen = [sys.executable, os.path.join(HERE, 'wvt_expected_absent.py'), '--stream', a.stream,
           '--num-wvt-regions', str(a.num_wvt_regions), '--tracer-opt', str(a.tracer_opt), '--stage', a.stage]
    expected = subprocess.run(gen, capture_output=True, text=True, check=True).stdout
    deferred = subprocess.run(gen + ['--deferred'], capture_output=True, text=True, check=True).stdout.split()
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
        f.write(expected); lst = f.name
    n_exp = len(expected.split())
    print(f'expected-absent ({a.stream}, N={a.num_wvt_regions}, tracer_opt={a.tracer_opt}): {n_exp} names; '
          f'deferred still-written: {deferred}')
    rc = subprocess.run([sys.executable, os.path.join(HERE, 'compare_gate0.py'), a.A, a.B,
                         '--stream', a.stream, '--expect-absent', lst]).returncode
    os.unlink(lst)
    problems = []
    if rc != 0:
        problems.append('compare_gate0 FAILED (see above)')
    # POSITIVE assertion, independent of the package lines: everything the registry says this
    # namelist must write is actually in B. A wrong package condition consistently applied
    # would pass the absent-set comparison; it cannot pass this.
    present = subprocess.run(gen + ['--present'], capture_output=True, text=True, check=True).stdout.split()
    for pb in sorted(glob.glob(os.path.join(a.B, f'{a.stream}_d01_*'))):
        with h5netcdf.File(pb, 'r') as B_:
            have = {v.lower() for v in B_.variables}
        missing = sorted(n for n in present if n not in have)
        if missing:
            problems.append(f'{os.path.basename(pb)}: {len(missing)} variable(s) this namelist MUST write are absent: {missing[:8]}{"..." if len(missing) > 8 else ""}')
    print(f'expected-present: {len(present)} names checked')
    if a.stage == '2a' and a.tracer_opt != 4:
        for pb in sorted(glob.glob(os.path.join(a.B, f'{a.stream}_d01_*'))):
            with h5netcdf.File(pb, 'r') as B_:
                wvt = wvt_names()
                left = sorted(v for v in B_.variables
                              if v.lower() in wvt and v.lower() not in deferred)
            if left:
                problems.append(f'{os.path.basename(pb)}: WVT-named variables still written with tracers off: {left}')
    if problems:
        print('\nFAIL: packaging gate'); [print('  ' + p) for p in problems]; return 1
    print(f'\nOK: packaging gate ({a.stream}, stage {a.stage}, N={a.num_wvt_regions}, tracer_opt={a.tracer_opt})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
