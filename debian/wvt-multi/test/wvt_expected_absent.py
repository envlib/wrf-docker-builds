#!/usr/bin/env python3
"""Which WVT state fields does a packaged build leave OUT of a wrfout / wrfrst, for a namelist?

Derived from the Registry, never typed: a field is absent from a stream when (1) it is packaged
on a condition the namelist does not satisfy and (2) its IO string carries that stream's flag
(`h` history, `r` restart). Packages read: wvt_cuten_nrN / wvt_thum_nrN (num_wvt_regions==N,
cumulative) and wvt_state (tracer_opt==4). The 4-D tracer members are NOT listed: they were
packaged before this change, so an old-vs-new comparison never sees them differ.

    python3 wvt_expected_absent.py --stream wrfout --num-wvt-regions 8 --tracer-opt 4
    python3 wvt_expected_absent.py --stream wrfrst --num-wvt-regions 1 --tracer-opt 0

Prints one name per line, lower-cased (wrfout spells some of these upper-case; compare
case-insensitively). --deferred prints the Stage-2b names that are deliberately still written.
"""
import argparse, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(HERE, '..', 'Registry')
DEFERRED = ['rtrqvcuten', 'rtrqccuten', 'rtrqrcuten', 'rtrqicuten', 'rtrqscuten']
# Governed by the STOCK package `bucketropt bucketr_opt==1` (Registry.EM_COMMON), not by
# tracer_opt: written whenever bucket_mm > 0, tracers on or off, exactly as before packaging.
STOCK_PACKAGED = ['i_tr_rainnc', 'i_tr_rainc']


def state_io():
    """name(lower) -> IO flag string, from every state line in the WVT registry files."""
    io = {}
    for fn in ('registry.moisttracers', 'registry.diag_columns', 'Registry.EM'):
        for line in open(os.path.join(REG, fn)):
            t = line.split()
            if len(t) > 7 and t[0] == 'state':
                io[t[2].lower()] = t[7]   # state TYPE NAME DIMS USE NTL STAG IO ...
    return io


def packages():
    """package name -> (namelist var, value, [state names lower]) for the WVT packages."""
    out = {}
    for fn in ('Registry.EM',):
        for line in open(os.path.join(REG, fn)):
            t = line.split()
            if len(t) < 5 or t[0] != 'package' or not (t[1].startswith('wvt_') or t[1] == 'tracer_moist'):
                continue
            m = re.match(r'(\w+)==(\d+)$', t[2])
            names = []
            for grp in t[4].split(';'):
                if grp.startswith('state:'):
                    names += [n.lower() for n in grp[6:].split(',') if n]
            out[t[1]] = (m.group(1), int(m.group(2)), names)
    return out


def expected_absent(stream, num_wvt_regions, tracer_opt, stage='2a'):
    """stage '1' counts only the per-region packages (wvt_cuten_nrN / wvt_thum_nrN): use it to
    compare against a build made before the wvt_state package existed."""
    flag = {'wrfout': 'h', 'wrfrst': 'r'}[stream]
    io = state_io(); absent = set()
    pkgs = {k: v for k, v in packages().items() if stage != '1' or k != 'wvt_state'}
    for pkg, (var, val, names) in pkgs.items():
        active = {'num_wvt_regions': num_wvt_regions, 'tracer_opt': tracer_opt}[var] == val
        # cumulative packages: region n's names are active if ANY package with val >= n is active,
        # i.e. iff num_wvt_regions >= n. Simplest correct rule: a name is absent iff no package
        # listing it is active.
        if not active:
            for n in names:
                absent.add(n)
    for pkg, (var, val, names) in pkgs.items():
        if {'num_wvt_regions': num_wvt_regions, 'tracer_opt': tracer_opt}[var] == val:
            absent -= set(names)
    return sorted(n for n in absent if flag in io.get(n, ''))


def all_wvt_names(stream):
    """Every WVT state name carrying this stream's flag: the moisttracers file, the *_TR
    diagnostics in diag_columns, and the 4-D tracer members declared in Registry.EM."""
    flag = {'wrfout': 'h', 'wrfrst': 'r'}[stream]
    names = set()
    for fn in ('registry.moisttracers', 'registry.diag_columns', 'Registry.EM'):
        for line in open(os.path.join(REG, fn)):
            t = line.split()
            if len(t) > 7 and t[0] == 'state':
                n = t[2].lower()
                # Registry.EM also declares the STOCK tr17_* test tracers (tracer_opt==2): only
                # the WVT species members q?_tr(_NN) count.
                if fn == 'registry.moisttracers' or (fn == 'registry.diag_columns' and '_tr' in n) \
                        or (fn == 'Registry.EM' and t[4] == 'tracer' and re.match(r'^q[vcrisg]_tr(_\d\d)?$', n)):
                    if flag in t[7]:
                        names.add(n)
    return names


def expected_present(stream, num_wvt_regions, tracer_opt, stage='2a'):
    """Names a run MUST write: all WVT names with the flag, minus the expected-absent set, minus
    the tracer members of inactive regions (packaged before this change), minus the stock-packaged
    bucket counters (namelist-conditional). With tracers off this is empty except the deferred set."""
    absent = set(expected_absent(stream, num_wvt_regions, tracer_opt, stage))
    names = all_wvt_names(stream) - absent - set(STOCK_PACKAGED)
    keep = set()
    for n in names:
        m = re.search(r'_(\d\d)$', n)
        region = int(m.group(1)) if m else 1
        is_tracer_member = re.match(r'^q[vcrisg]_tr(_\d\d)?$', n) is not None
        if tracer_opt != 4:
            if n in DEFERRED:
                keep.add(n)
            continue
        if is_tracer_member and region > num_wvt_regions:
            continue
        keep.add(n)
    return sorted(keep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stream', choices=['wrfout', 'wrfrst'], required=True)
    ap.add_argument('--num-wvt-regions', type=int, required=True)
    ap.add_argument('--tracer-opt', type=int, required=True)
    ap.add_argument('--deferred', action='store_true',
                    help='print the names a tracer-off run may still write: the Stage-2b deferred '
                         'fields and the bucket counters governed by the stock bucketropt package')
    ap.add_argument('--stage', choices=['1', '2a'], default='2a', help="'1' ignores the wvt_state package")
    ap.add_argument('--present', action='store_true', help='print the names the run MUST write instead')
    a = ap.parse_args()
    if a.deferred:
        io = state_io(); flag = {'wrfout': 'h', 'wrfrst': 'r'}[a.stream]
        print('\n'.join(n for n in DEFERRED + STOCK_PACKAGED if flag in io.get(n, '')))
        return 0
    if a.present:
        print('\n'.join(expected_present(a.stream, a.num_wvt_regions, a.tracer_opt, a.stage)))
        return 0
    print('\n'.join(expected_absent(a.stream, a.num_wvt_regions, a.tracer_opt, a.stage)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
