#!/usr/bin/env python3
"""Gates 1, 2, 2b and 7 for the lateral-boundary face tags, on raw wrfout.

WHAT THIS SCRIPT READS, AND WHY (refactored 2026-09-07 after plan-review round
wvt-bdytags-redund-1b):

  * The shells come from the MASK FILE WRF actually ran with (trmask_d01), not from a
    re-derivation of the geometry. Earlier versions rebuilt the shells from (RELAX, we, sn) with
    an inline copy of create_trmask's corner convention -- so the gate could disagree with the
    mask generator without either being wrong on its own terms, and, worse, never looked at the
    artefact fed to auxinput8 at all. Reading the file removes the duplication AND adds the check
    that was missing: a stale, hand-edited or differently-parameterised mask in the run directory
    is now a direct assertion, not noise in gate 2.
  * The namelist is used for exactly ONE job: asserting the artefact against the configuration
    (spec_bdy_width vs the margin width inferred from the mask; num_wvt_regions vs the mask's
    region count; num_wvt_bdy_regions vs the number of shells). Those are two things that really
    can disagree, so this is not tautological. `num_wvt_bdy_regions` defaults to 0 when absent --
    namelist.input.n8 omits it deliberately, and 0 is the post-change binary's default.
  * The only geometry left in this file is a distance-to-nearest-edge grid, used for the gate 7
    profile and the clamped-cell structural assertion. It is a distance, not a partition.

MEASURED SPECIFICATION -- the first draft of this file asserted exact closure everywhere in
the shell and failed on the first real run. Measured on the 3 h 12-region test (2026-09-06):

  * where the residual is NOT clamped, closure is exact to 4.9e-9 against a peak qv of
    1.9e-2, i.e. float32 roundoff. The relabel does exactly what it was designed to do.
  * in 69 of 64000 shell cells (0.1%), advection had already pushed sum_{m/=F} tr_m ABOVE
    QVAPOR before the relabel ran. There MAX(0, qv - others) clamps to zero, the pre-existing
    excess survives, and no formulation that declines to rewrite other regions can repair it.
    Every violating cell in the run was of exactly this kind, and all were inside the margin.

So exact closure is the right assertion on the unclamped cells and the WRONG one overall. The
clamped cells are reported as a bounded trend instead: they are pre-existing violations the
relabel inherits, not ones it creates, and the next microphysics cap rescales them.

Gate 1 (domain-wide bound): sum_n qv_tr_n <= QVAPOR outside the clamped cells. Nothing in WRF
enforces this globally -- regions over-tag independently -- so it is a bound on the healthy
population, not an invariant.

Gate 2 (shell closure): inside shell F, on cells where the residual was not clamped,
sum_n qv_tr_n == QVAPOR to float32 roundoff. Three handling rules, all of which came out of
review:

  * expressed as a DIFFERENCE, never a ratio -- qv_tr/qv is NaN wherever qv -> 0 aloft;
  * evaluated on RAW wrfout, not through cfdb, whose packing quantises;
  * t = 0 is SKIPPED -- that is the initial state, where every tracer is still zero.

Environment:
  WVT_TEST_WORK      run directory on the host (default /tmp/wvt_rt_test); wrfout under out/
  WVT_TEST_TRMASK    the mask WRF ran with (default $WVT_TEST_WORK/trmask_d01)
  WVT_TEST_NAMELIST  the namelist WRF ran with (default $WVT_TEST_WORK/out/namelist.input if
                     run_n12.sh copied it back, else $WVT_TEST_WORK/namelist.input.n12)

Needs h5netcdf, numpy, scipy (NetCDF3 classic reader for the mask) and f90nml -- all in the
wrf-auto-runs environment, which is where this is documented to run.
"""
import glob
import os
import sys

import f90nml
import h5netcdf
import numpy as np
from scipy.io import netcdf_file

WORK = os.environ.get('WVT_TEST_WORK', '/tmp/wvt_rt_test')
def _default_trmask():
    ran = os.path.join(WORK, 'out', 'trmask_d01')       # copied back by run_n12.sh: the one WRF read
    return ran if os.path.exists(ran) else os.path.join(WORK, 'trmask_d01')


TRMASK_PATH = os.environ.get('WVT_TEST_TRMASK') or _default_trmask()


def _default_namelist():
    ran = os.path.join(WORK, 'out', 'namelist.input')
    if os.path.exists(ran):
        return ran
    return os.path.join(WORK, 'namelist.input.n12')


NAMELIST_PATH = os.environ.get('WVT_TEST_NAMELIST') or _default_namelist()

#: Labels for shells 1..n_bdy, in the order create_trmask.BOUNDARY_FACES assigns region
#: indices. These are LABELS for the printout only: nothing here derives geometry from them.
#: Whether the MODEL agrees that shell k carries face k's inflow is exactly what the
#: composition assertion below tests, by looking at the tracers, so a permutation between the
#: mask generator and the Registry member order fails loudly (verified by mutation).
FACE_LABELS = ('west', 'east', 'south', 'north')

#: (base field, tracer prefix) for all six tagged species, in Registry order.
#: ⚠ Gate 2 used to check VAPOUR ONLY -- the species furthest from what is published. The
#: headline is a PRECIPITATION fraction (TR_RAINNC/RAINNC), which comes from the hydrometeor
#: tags. And the cumulus path indexes species with a DIFFERENT convention from the relabel
#: (1-based sparse, qv=+1 qc=+2 qi=+4), so an offset error hitting species 2-5 but not vapour
#: is exactly the defect a vapour-only gate cannot see.
SPECIES = [('QVAPOR', 'qv_tr'), ('QCLOUD', 'qc_tr'), ('QRAIN', 'qr_tr'),
           ('QICE', 'qi_tr'), ('QSNOW', 'qs_tr'), ('QGRAUP', 'qg_tr')]


# ---------------------------------------------------------------------------------------------
# the artefact and the configuration
# ---------------------------------------------------------------------------------------------

def edge_distance(sn, we):
    """Chebyshev distance (cells) to the nearest lateral edge. The only geometry in this file."""
    j = np.arange(sn)[:, None]
    i = np.arange(we)[None, :]
    return np.minimum(np.minimum(i, we - 1 - i), np.minimum(j, sn - 1 - j))


def load_mask(path):
    """TRMASK as (N, sn, we) booleans, from the NetCDF3 file create_trmask wrote."""
    if not os.path.exists(path):
        sys.exit(f'FAIL: mask file not found: {path} (set WVT_TEST_TRMASK)')
    with netcdf_file(path, 'r', mmap=False) as f:
        v = f.variables['TRMASK']
        arr = np.array(v[0] if v.data.ndim == 4 else v[:], dtype='f4')
    if arr.ndim != 3:
        sys.exit(f'FAIL: TRMASK in {path} has shape {arr.shape}; expected (regions, sn, we)')
    return arr > 0.5


def load_config(path):
    """The three namelist values the artefact is asserted against."""
    if not os.path.exists(path):
        sys.exit(f'FAIL: namelist not found: {path} (set WVT_TEST_NAMELIST)')
    nml = f90nml.read(path)

    def scalar(v):
        return v[0] if isinstance(v, list) else v

    dyn, bdy = nml['dynamics'], nml['bdy_control']
    return {
        'spec_bdy_width': int(scalar(bdy['spec_bdy_width'])),
        'num_wvt_regions': int(scalar(dyn['num_wvt_regions'])),
        # Absent means 0: the pre-change binary does not know the key and the post-change
        # binary defaults it to 0. That default is what makes the gate-0 baseline valid.
        'num_wvt_bdy_regions': int(scalar(dyn.get('num_wvt_bdy_regions', 0))),
    }


def shells_from_mask(masks, n_bdy):
    """Split the mask into (source masks, shell list, margin, inferred relax width).

    The shells are the LAST n_bdy regions -- the ordering create_trmask enforces by appending
    them. Structural assertions on the artefact itself: shells are pairwise disjoint, and their
    union is exactly the outermost `relax` rings (no gap, no escape). A gap is a permanent
    untagged source; an escape overlaps a source region.
    """
    n = masks.shape[0]
    n_src = n - n_bdy
    if n_bdy <= 0:
        sys.exit('FAIL: the namelist declares no boundary regions; these gates have nothing to check')
    if n_bdy > len(FACE_LABELS):
        sys.exit(f'FAIL: {n_bdy} boundary regions but only {len(FACE_LABELS)} lateral faces exist')
    if n_src < 1:
        sys.exit(f'FAIL: {n_bdy} boundary regions but only {n} regions in the mask')
    shells = [masks[n_src + k] for k in range(n_bdy)]
    stack = np.stack(shells)
    if (stack.sum(axis=0) > 1).any():
        sys.exit('FAIL: boundary shells overlap in the mask file')
    margin = stack.any(axis=0)
    if not margin.any():
        sys.exit('FAIL: boundary shells are EMPTY in the mask file -- grid%trmask would source nothing')
    sn, we = masks.shape[1:]
    dist = edge_distance(sn, we)
    relax = int(dist[margin].max()) + 1
    ring = dist < relax
    escapes = int((margin & ~ring).sum())
    if escapes:
        sys.exit(f'FAIL: {escapes} shell cell(s) lie outside the outermost {relax} rings')
    gaps = int((ring & ~margin).sum())
    # Production's own rule (create_trmask): with ALL faces listed the shells must tile the margin
    # exactly and a gap is a bug; with fewer faces a gap is the untagged inflow of the unlisted
    # faces -- a legitimate cost choice, reported rather than refused (review round redund-code-1
    # found the earlier version refusing a 2-face run with a message that blamed the artefact).
    if n_bdy == len(FACE_LABELS) and gaps:
        sys.exit(f'FAIL: all {n_bdy} faces present but {gaps} margin cell(s) are in no shell -- '
                 'a tiling defect in the mask, not a configuration choice')
    if gaps:
        print(f'NOTE: {n_bdy} of {len(FACE_LABELS)} faces tagged; {gaps} margin cell(s) are in no '
              'shell (inflow there stays untagged by design)')
    return n_src, shells, margin, relax, dist


def cross_assert(cfg, masks, n_bdy_from_mask, relax):
    """Artefact vs configuration -- NAMED failures for the mismatch that used to surface only
    as gate-2 noise (measured: a width mismatch of one cell moves gate 2 by ~1.6e-2 with no
    message saying why)."""
    fails = []
    if cfg['num_wvt_regions'] != masks.shape[0]:
        fails.append(f'namelist num_wvt_regions={cfg["num_wvt_regions"]} but the mask holds '
                     f'{masks.shape[0]} regions')
    if cfg['num_wvt_bdy_regions'] != n_bdy_from_mask:
        fails.append(f'namelist num_wvt_bdy_regions={cfg["num_wvt_bdy_regions"]} but '
                     f'{n_bdy_from_mask} shell(s) were checked')
    if cfg['spec_bdy_width'] != relax:
        fails.append(f'mask built at margin width {relax} but namelist spec_bdy_width='
                     f'{cfg["spec_bdy_width"]}: the shells do not line up with the boundary zone')
    return fails


# ---------------------------------------------------------------------------------------------
# the closure computation -- ONE implementation for every species
# ---------------------------------------------------------------------------------------------

def tracer_names(f, prefix, n_reg):
    names = [prefix] + [f'{prefix}_{n:02d}' for n in range(2, n_reg + 1)]
    missing = [n for n in names if n not in f]
    if missing:
        sys.exit(f'FAIL: wrfout is missing tracer members: {missing}')
    return names


def closure(path, base, prefix, shells, margin, n_src, n_reg, tol_rel=1e-6):
    """Everything gates 1/2/2b need for one species in one file.

    Returns dict(q, tot, tr, clamped, own, tol). A cell is CLAMPED where the OTHER regions already
    summed above the base before the relabel ran, so MAX(0,.) drove this face to zero.
    ⚠ TOLERANCE on that test: without it, cells exceeding by one ulp count as clamped, which
    inflates the excluded population with pure roundoff (a review arm measured 1141 such cells
    on a synthetic case). The excluded set must be the REAL ones only. The tolerance is scaled to
    THIS species -- hydrometeors are orders of magnitude smaller than vapour, so one absolute
    tolerance would be vacuous for them.

    Raises (via sys.exit) rather than returning 0.0 when NO cell is healthy: an all-clamped
    field must fail gate 1, not silently pass it with a zero.
    """
    with h5netcdf.File(path, 'r') as f:
        if base not in f:
            return None
        names = tracer_names(f, prefix, n_reg)
        q = np.asarray(f[base][0]).astype('f8')
        tr = np.stack([np.asarray(f[n][0]).astype('f8') for n in names])
    tot = tr.sum(axis=0)
    tol = tol_rel * max(float(np.max(q)), 1e-12)
    clamped = np.zeros(q.shape, dtype=bool)
    own = np.zeros(q.shape)          # this cell's OWN face tag, whichever face owns it
    for k, m in enumerate(shells):
        o = tr[n_src + k][:, m]
        others = tot[:, m] - o
        idx = np.where(m)
        clamped[:, idx[0], idx[1]] = others > q[:, m] + tol
        own[:, idx[0], idx[1]] = o
    # The population that matters is the SHELL: `clamped` is only ever set there, so testing
    # the whole domain (as a first version did) is unreachable -- the interior is always healthy.
    # An all-clamped margin must FAIL, not pass with a vacuous 0.0 (round redund-code-1: an
    # injected corruption over every margin cell passed gate 2b through exactly that fallback).
    n_margin = int(margin.sum()) * q.shape[0]
    n_clamped_margin = int(clamped[:, margin].sum())
    if n_clamped_margin >= n_margin:
        sys.exit(f'FAIL: {os.path.basename(path)} {base}: every margin cell is clamped -- '
                 'no healthy shell cell to check closure on')
    # Calibrated bound on the clamped population itself: healthy output measures 0-69 of 64000
    # vapour margin cell-steps (~0.1%) and 0 for the hydrometeors. 5% is 50x that.
    if n_clamped_margin > 0.05 * n_margin:
        sys.exit(f'FAIL: {os.path.basename(path)} {base}: {n_clamped_margin} of {n_margin} margin '
                 'cell-steps clamped (>5%) -- the clamped population is not the structural one')
    return {'q': q, 'tot': tot, 'tr': tr, 'clamped': clamped, 'own': own, 'tol': tol}


# ---------------------------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------------------------

def main():
    files = sorted(glob.glob(os.path.join(WORK, 'out', 'wrfout_d01_*')))
    if not files:
        sys.exit(f'FAIL: no wrfout in {WORK}/out')

    masks = load_mask(TRMASK_PATH)
    cfg = load_config(NAMELIST_PATH)
    n_bdy = cfg['num_wvt_bdy_regions']
    if cfg['num_wvt_regions'] != masks.shape[0]:
        sys.exit(f'FAIL: artefact does not match configuration: namelist num_wvt_regions='
                 f'{cfg["num_wvt_regions"]} but the mask {TRMASK_PATH} holds {masks.shape[0]} regions')
    n_src, shells, margin, relax, dist = shells_from_mask(masks, n_bdy)
    n_reg = masks.shape[0]
    faces = FACE_LABELS[:n_bdy]
    print(f'mask     : {TRMASK_PATH}  -> {n_reg} regions, {n_bdy} shell(s), inferred margin width {relax}')
    print(f'namelist : {NAMELIST_PATH}  -> spec_bdy_width={cfg["spec_bdy_width"]} '
          f'num_wvt_regions={cfg["num_wvt_regions"]} num_wvt_bdy_regions={cfg["num_wvt_bdy_regions"]}')
    fails = cross_assert(cfg, masks, n_bdy, relax)
    if fails:
        print('\nFAIL: artefact does not match configuration')
        for x in fails:
            print('  ' + x)
        return 1
    print(f'artefact == configuration: OK')
    print(f'checking {len(files)} output time(s)\n')

    worst_over = 0.0
    worst_shell = 0.0

    for path in files:
        stamp = os.path.basename(path).replace('wrfout_d01_', '')
        c = closure(path, 'QVAPOR', 'qv_tr', shells, margin, n_src, n_reg)
        qv, tot, tr, clamped, own, tol = c['q'], c['tot'], c['tr'], c['clamped'], c['own'], c['tol']
        first = files.index(path) == 0 and float(tot.max()) == 0.0   # genuinely t=0: no tracer yet
        n_clamp = int(clamped.sum())
        clamp_excess = float(np.max((tot - qv)[clamped])) if n_clamp else 0.0

        # ⚠ THE EXCLUDED POPULATION MUST ITSELF BE CHECKED. Both arms of round
        # wvt-bdytags-code-2 broke the earlier version by hiding a defect inside it: one wrote
        # an absurd value into a clamped cell, the other swapped two face identities (which
        # made 16216 cells "clamped" and swallowed the swap). Excluding cells without
        # asserting anything about them is not a gate, it is a hole. Two structural
        # assertions, both measured on healthy output:
        #   (a) the face tag is EXACTLY zero there -- that is what MAX(0, .) must have done;
        #   (b) they lie only at distance 0, the specified row microphysics skips.
        if n_clamp:
            bad_own = float(np.max(own[clamped]))
            if bad_own != 0.0:
                fails.append(f'{stamp}: clamped cell with NON-ZERO face tag ({bad_own:.3e}) -- '
                             'the relabel did not clamp where the gate assumed it did')
            far = int((np.broadcast_to(dist, qv.shape)[clamped] > 0).sum())
            if far:
                fails.append(f'{stamp}: {far} clamped cell(s) away from the specified row -- '
                             'the clamped population is not the structural one it is assumed to be')

        # --- Gate 1: the bound on the healthy population (unguarded max: closure() has already
        #     refused an all-clamped field)
        healthy = ~clamped
        over = float(np.max((tot - qv)[healthy]))
        worst_over = max(worst_over, over)
        g1 = over <= tol
        if not g1:
            fails.append(f'{stamp}: gate 1 exceeded by {over:.3e} (tol {tol:.3e})')

        # --- Gate 2: exact closure in the shells, unclamped cells only (skip t=0)
        if first:
            print(f'{stamp}  gate1 max(sum-qv) = {over:+.3e}   [gate2 skipped: t=0]')
            continue
        sel = margin[None, :, :] & healthy
        if not sel.any():
            fails.append(f'{stamp}: no healthy shell cell for gate 2')
            print(f'{stamp}  gate1 {over:+.3e} {"OK" if g1 else "FAIL"}   gate2 NO HEALTHY SHELL CELL')
            continue
        d = float(np.max(np.abs(tot - qv)[sel]))
        worst_shell = max(worst_shell, d)
        g2 = d <= tol
        if not g2:
            fails.append(f'{stamp}: gate 2 shell closure off by {d:.3e} (tol {tol:.3e})')

        # COMPOSITION -- asserted, not merely printed. The design record required "region F
        # ~ 1, others ~ 0 inside shell F"; printing it meant a face-order mismatch between
        # create_trmask.BOUNDARY_FACES and the Registry member order passed every gate while
        # relabelling west inflow as east. Two assertions, neither needing a magnitude
        # threshold tuned to the weather:
        #   (a) each face must OWN its shell -- more tagged vapour there than any other face;
        #   (b) a floor of 0.5, well below the 0.906 minimum measured on healthy output.
        parts = []
        for k, face in enumerate(faces):
            m = shells[k]
            q = qv[:, m]
            wet = q > 1e-8
            o = tr[n_src + k][:, m]
            share = float(np.mean(o[wet] / q[wet])) if wet.any() else float('nan')
            parts.append(f'{face[0].upper()}={share:.3f}')
            rivals = [float(np.mean(tr[n_src + j][:, m][wet] / q[wet]))
                      for j in range(n_bdy) if j != k] if wet.any() else []
            if wet.any() and rivals and share <= max(rivals):
                fails.append(f'{stamp}: in the {face} shell another face holds more tagged '
                             f'vapour ({share:.3f} vs {max(rivals):.3f}) -- face identities '
                             'look permuted between the mask and the region mapping')
            elif wet.any() and share < 0.5:
                fails.append(f'{stamp}: {face} shell own-face share {share:.3f} < 0.5 -- '
                             'the shell is not tagging its own inflow')
        print(f'{stamp}  gate1 {over:+.3e} {"OK" if g1 else "FAIL"}   '
              f'gate2 |sum-qv| shells {d:.3e} {"OK" if g2 else "FAIL"}   '
              f'clamped {n_clamp:5d} (max excess {clamp_excess:.2e})   '
              f'own-face [{" ".join(parts)}]')

    # --- gate 2b: every tagged species, one representative time (the per-step vapour gates
    #     cover the rest). Explicit, not `for ...: break`: with a single output time the old
    #     loop silently printed a header and no rows.
    print('\ngate 2b -- shell closure for EVERY tagged species (unclamped cells)')
    print(f'  {"species":>8s} {"bound excess":>14s} {"shell closure":>14s} {"tol":>10s} {"clamped":>8s}')
    if len(files) < 2:
        sys.exit('FAIL: gate 2b needs at least two output times (t=0 carries no tracer)')
    path = files[1]
    for base, prefix in SPECIES:
        c = closure(path, base, prefix, shells, margin, n_src, n_reg)
        if c is None:
            continue
        healthy = ~c['clamped']
        bound = float(np.max((c['tot'] - c['q'])[healthy]))
        sel = margin[None, :, :] & healthy
        if not sel.any():                   # closure() already refuses this; belt and braces
            fails.append(f'{os.path.basename(path)}: {base}: no healthy shell cell for gate 2b')
            continue
        close = float(np.max(np.abs(c['tot'] - c['q'])[sel]))
        nclamp, tol = int(c['clamped'].sum()), c['tol']
        flag = 'OK' if (bound <= tol and close <= tol) else 'FAIL'
        if flag == 'FAIL':
            fails.append(f'{os.path.basename(path)}: {base} closure {close:.3e} / bound '
                         f'{bound:+.3e} exceeds tol {tol:.3e}')
        print(f'  {base:>8s} {bound:>+14.3e} {close:>14.3e} {tol:>10.2e} {nclamp:>8d}  {flag}')

    print()
    print(f'gate 1  worst overshoot (unclamped)   : {worst_over:+.3e}')
    print(f'gate 2  worst shell closure (unclamped): {worst_shell:.3e}')
    print('clamped cells are pre-existing violations the relabel inherits, not ones it makes;')
    print('watch their COUNT and MAX EXCESS across runs rather than gating on them.')
    if fails:
        print('\nFAIL:')
        for x in fails:
            print('  ' + x)
        return 1
    print('\nOK: both gates pass')
    return 0


def gate7_profile():
    """Gate 7: tagged fraction vs distance from the lateral boundary, split by ROLE.

    Settles with a number the one thing the two plan-review arms disagreed about: whether a
    5-cell shell tags inflow before it reaches the interior. The two roles must have OPPOSITE
    profiles -- boundary tags highest at the edge and decaying inward, source tags lowest at
    the edge -- and a flat boundary profile would mean the shells are not tagging at all.
    """
    files = sorted(glob.glob(os.path.join(WORK, 'out', 'wrfout_d01_*')))
    path = files[-1]
    masks = load_mask(TRMASK_PATH)
    cfg = load_config(NAMELIST_PATH)
    n_reg = masks.shape[0]
    n_src = n_reg - cfg['num_wvt_bdy_regions']
    with h5netcdf.File(path, 'r') as f:
        names = tracer_names(f, 'qv_tr', n_reg)
        qv = np.asarray(f['QVAPOR'][0]).astype('f8')
        tr = np.stack([np.asarray(f[n][0]).astype('f8') for n in names])
    sn, we = qv.shape[-2:]
    dist = edge_distance(sn, we)

    src = tr[:n_src].sum(axis=0)
    bdy = tr[n_src:].sum(axis=0)
    print(f'\ngate 7 -- tagged fraction vs distance from boundary  ({os.path.basename(path)})')
    print(f'  {"cells from edge":>16s} {"boundary":>9s} {"source":>8s} {"untagged":>9s}')
    edges = [0, 5, 10, 15, 20, 30, 9999]
    prof = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (dist >= lo) & (dist < hi)
        if not m.any():
            continue
        q = qv[:, m].sum()
        if q <= 0:
            continue
        fb, fs = float(bdy[:, m].sum() / q), float(src[:, m].sum() / q)
        prof.append((lo, fb))
        lab = f'{lo}-{hi-1}' if hi < 9999 else f'{lo}+'
        print(f'  {lab:>16s} {fb:9.4f} {fs:8.4f} {1-fb-fs:9.4f}')
    # ⚠ `edge >= max(inland)` alone passes with DEAD shells, because 0.0 >= 0.0 (round
    # wvt-bdytags-code-2). Require a real signal at the edge as well: healthy output measures
    # 0.9955 there, so a floor of 0.5 is far below anything physical and far above nothing.
    if len(prof) < 2:
        print('  -> FAIL: fewer than two distance bins with vapour; cannot form a profile')
        return 1
    edge = prof[0][1]
    inland = max(f for _, f in prof[1:])
    ok = edge >= inland and edge > 0.5
    print(f'  -> boundary fraction highest at the edge: {"YES" if ok else "NO"}'
          f'   (edge {edge:.4f} vs max inland {inland:.4f}; floor 0.5)')
    if not ok and edge <= 0.5:
        print('     FAIL: shells are tagging little or nothing -- check trmask against '
              'num_wvt_bdy_regions.')
    return 0 if ok else 1


if __name__ == '__main__':
    rc = main()
    rc |= gate7_profile()
    sys.exit(rc)
