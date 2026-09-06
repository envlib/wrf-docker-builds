#!/usr/bin/env python3
"""Gates 1 and 2 for the lateral-boundary face tags, on raw wrfout.

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

Run on the host against /work/out/wrfout_d01_*.
"""
import glob
import os
import sys

import h5netcdf
import numpy as np

WORK = os.environ.get('WVT_TEST_WORK', '/tmp/wvt_rt_test')
N_SRC = 8
FACES = ('west', 'east', 'south', 'north')
RELAX = 5


#: (base field, tracer prefix) for all six tagged species, in Registry order.
#: ⚠ Gate 2 used to check VAPOUR ONLY -- the species furthest from what is published. The
#: headline is a PRECIPITATION fraction (TR_RAINNC/RAINNC), which comes from the hydrometeor
#: tags. And the cumulus path indexes species with a DIFFERENT convention from the relabel
#: (1-based sparse, qv=+1 qc=+2 qi=+4), so an offset error hitting species 2-5 but not vapour
#: is exactly the defect a vapour-only gate cannot see.
SPECIES = [('QVAPOR', 'qv_tr'), ('QCLOUD', 'qc_tr'), ('QRAIN', 'qr_tr'),
           ('QICE', 'qi_tr'), ('QSNOW', 'qs_tr'), ('QGRAUP', 'qg_tr')]


def tracer_names(f, prefix='qv_tr'):
    names = [prefix] + [f'{prefix}_{n:02d}' for n in range(2, N_SRC + len(FACES) + 1)]
    missing = [n for n in names if n not in f]
    if missing:
        sys.exit(f'FAIL: wrfout is missing tracer members: {missing}')
    return names


def species_closure(path, shells, margin, tol_rel=1e-6):
    """Shell closure and the domain bound for EVERY tagged species, not just vapour.

    Returns {species: (bound_excess, shell_closure, n_clamped)} on unclamped cells.
    """
    out = {}
    with h5netcdf.File(path, 'r') as f:
        for base, prefix in SPECIES:
            if base not in f:
                continue
            names = tracer_names(f, prefix)
            q = np.asarray(f[base][0]).astype('f8')
            tr = np.stack([np.asarray(f[n][0]).astype('f8') for n in names])
            tot = tr.sum(axis=0)
            # tolerance scaled to THIS species -- hydrometeors are orders of magnitude
            # smaller than vapour, so one absolute tolerance would be vacuous for them.
            tol = tol_rel * max(float(np.max(q)), 1e-12)
            clamped = np.zeros(q.shape, dtype=bool)
            for k, face in enumerate(FACES):
                m = shells[face]
                others = tot[:, m] - tr[N_SRC + k][:, m]
                idx = np.where(m)
                clamped[:, idx[0], idx[1]] = others > q[:, m] + tol
            healthy = ~clamped
            bound = float(np.max((tot - q)[healthy])) if healthy.any() else 0.0
            sel = margin[None, :, :] & healthy
            close = float(np.max(np.abs(tot - q)[sel])) if sel.any() else 0.0
            out[base] = (bound, close, int(clamped.sum()), tol)
    return out


def shell_masks(sn, we):
    j = np.arange(sn)[:, None]
    i = np.arange(we)[None, :]
    d_w, d_e, d_s, d_n = i, we - 1 - i, j, sn - 1 - j
    d_we, d_sn = np.minimum(d_w, d_e), np.minimum(d_s, d_n)
    margin = np.minimum(d_we, d_sn) < RELAX
    mer = d_we <= d_sn
    return {
        'west': margin & mer & (d_w <= d_e),
        'east': margin & mer & (d_e < d_w),
        'south': margin & (~mer) & (d_s <= d_n),
        'north': margin & (~mer) & (d_n < d_s),
    }, margin


def main():
    files = sorted(glob.glob(os.path.join(WORK, 'out', 'wrfout_d01_*')))
    if not files:
        sys.exit(f'FAIL: no wrfout in {WORK}/out')
    print(f'checking {len(files)} output time(s)\n')

    worst_over = 0.0
    worst_shell = 0.0
    fails = []

    for path in files:
        stamp = os.path.basename(path).replace('wrfout_d01_', '')
        with h5netcdf.File(path, 'r') as f:
            names = tracer_names(f)
            qv = np.asarray(f['QVAPOR'][0]).astype('f8')
            tr = np.stack([np.asarray(f[n][0]).astype('f8') for n in names])
        sn, we = qv.shape[-2:]
        shells, margin = shell_masks(sn, we)
        tot = tr.sum(axis=0)
        first = files.index(path) == 0
        tol = 1e-6 * max(float(np.max(qv)), 1e-12)   # ~50x the measured roundoff floor

        # A cell is CLAMPED where the other regions already summed above the base before the
        # relabel ran, so MAX(0,.) drove this face to zero. Identify it per shell, then treat
        # those cells as a reported population rather than as gate failures.
        clamped = np.zeros(qv.shape, dtype=bool)
        own = np.zeros(qv.shape)          # this cell's OWN face tag, whichever face owns it
        for k, face in enumerate(FACES):
            m = shells[face]
            o = tr[N_SRC + k][:, m]
            others = tot[:, m] - o
            # ⚠ TOLERANCE. Without it, cells exceeding by one ulp count as clamped, which
            # inflates the excluded population with pure roundoff (a review arm measured 1141
            # such cells on a synthetic case). The excluded set must be the REAL ones only.
            sub = others > qv[:, m] + tol
            idx = np.where(m)
            clamped[:, idx[0], idx[1]] = sub
            own[:, idx[0], idx[1]] = o
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
            dist = np.minimum(np.minimum(np.arange(we)[None, :], we - 1 - np.arange(we)[None, :]),
                              np.minimum(np.arange(sn)[:, None], sn - 1 - np.arange(sn)[:, None]))
            far = int((np.broadcast_to(dist, qv.shape)[clamped] > 0).sum())
            if far:
                fails.append(f'{stamp}: {far} clamped cell(s) away from the specified row -- '
                             'the clamped population is not the structural one it is assumed to be')

        # --- Gate 1: the bound on the healthy population
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
        d = float(np.max(np.abs(tot - qv)[sel]))
        worst_shell = max(worst_shell, d)
        g2 = d <= tol
        if not g2:
            fails.append(f'{stamp}: gate 2 shell closure off by {d:.3e} (tol {tol:.3e})')

        # COMPOSITION -- asserted, not merely printed. The design record required "region F
        # ~ 1, others ~ 0 inside shell F"; printing it meant a face-order mismatch between
        # create_trmask.BOUNDARY_FACES and wvt_regions.BOUNDARY_REGIONS passed every gate while
        # relabelling west inflow as east. Two assertions, neither needing a magnitude
        # threshold tuned to the weather:
        #   (a) each face must OWN its shell -- more tagged vapour there than any other face;
        #   (b) a floor of 0.5, well below the 0.906 minimum measured on healthy output.
        parts = []
        for k, face in enumerate(FACES):
            m = shells[face]
            q = qv[:, m]
            wet = q > 1e-8
            o = tr[N_SRC + k][:, m]
            share = float(np.mean(o[wet] / q[wet])) if wet.any() else float('nan')
            parts.append(f'{face[0].upper()}={share:.3f}')
            rivals = [float(np.mean(tr[N_SRC + j][:, m][wet] / q[wet]))
                      for j in range(len(FACES)) if j != k] if wet.any() else []
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

    # --- all six species, not just vapour
    print('\ngate 2b -- shell closure for EVERY tagged species (unclamped cells)')
    print(f'  {"species":>8s} {"bound excess":>14s} {"shell closure":>14s} {"tol":>10s} {"clamped":>8s}')
    for path in files[1:]:
        with h5netcdf.File(path, 'r') as f:
            sn2, we2 = np.asarray(f['QVAPOR'][0]).shape[-2:]
        sh, mg = shell_masks(sn2, we2)
        res = species_closure(path, sh, mg)
        for base, (bound, close, nclamp, tol) in res.items():
            flag = 'OK' if (bound <= tol and close <= tol) else 'FAIL'
            if flag == 'FAIL':
                fails.append(f'{os.path.basename(path)}: {base} closure {close:.3e} / bound '
                             f'{bound:+.3e} exceeds tol {tol:.3e}')
            print(f'  {base:>8s} {bound:>+14.3e} {close:>14.3e} {tol:>10.2e} {nclamp:>8d}  {flag}')
        break   # one representative time; the per-step vapour gates cover the rest

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
    with h5netcdf.File(path, 'r') as f:
        names = tracer_names(f)
        qv = np.asarray(f['QVAPOR'][0]).astype('f8')
        tr = np.stack([np.asarray(f[n][0]).astype('f8') for n in names])
    sn, we = qv.shape[-2:]
    j = np.arange(sn)[:, None]
    i = np.arange(we)[None, :]
    dist = np.minimum(np.minimum(i, we - 1 - i), np.minimum(j, sn - 1 - j))

    src = tr[:N_SRC].sum(axis=0)
    bdy = tr[N_SRC:].sum(axis=0)
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
    edge = prof[0][1]
    inland = max(f for _, f in prof[1:])
    ok = len(prof) >= 2 and edge >= inland and edge > 0.5
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
