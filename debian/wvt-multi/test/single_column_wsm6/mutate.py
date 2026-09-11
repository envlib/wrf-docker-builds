#!/usr/bin/env python3
"""Kill matrix for the WSM6 tag instrumentation.

Each mutant removes or breaks one KIND of instrumentation and asserts that a named gate notices.
A mutant nothing catches is the valuable result: it means either the instrumentation is
unnecessary, or -- far more likely -- no gate can see that class of defect. Round `wsm6-code-1`
found 10 uninstrumented floors precisely because nothing was gating their absence.

⚠ MUTATES THE SHIPPING SOURCE IN PLACE, deliberately: the harness compiles `phys/physics_mmm/
mp_wsm6.F90` directly, so testing a copy would test a file WRF does not build. Restoration is in
a `finally` with a per-run backup -- the cumulus twin used a fixed /tmp path and no finally, so an
interrupt left the checked-in scheme mutated with the only copy in a shared location.

Usage:  ./mutate.py [--keep-going]
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / '..' / '..' / 'phys' / 'physics_mmm' / 'mp_wsm6.F90'
SRC = SRC.resolve()

# (name, old, new, n_expected, gate expected to catch it, why)
MUTANTS = [
    ('process-floor counters removed',
     'if (present(tr_mpcre)) tr_mpcre(i,n) = tr_mpcre(i,n) - ztr_unc*den(i,k)*delz(i,k)',
     'if (.false.) tr_mpcre(i,n) = tr_mpcre(i,n) - ztr_unc*den(i,k)*delz(i,k)',
     10, 'ledger',
     'reproduces the pre-review state exactly: D1 creation invisible, mislabelled later as RED/DES'),

    ('entry-floor counters removed',
     'if (present(tr_mpcre)) tr_mpcre(i,n) = tr_mpcre(i,n) &',
     'if (.false.) tr_mpcre(i,n) = tr_mpcre(i,n) &',
     6, 'ledger',
     'fires only when the dynamics delivers a negative tracer; may be unexercised here'),

    ('redistributive counters removed',
     'if (present(tr_mpred)) tr_mpred(i,n) = tr_mpred(i,n) &',
     'if (.false.) tr_mpred(i,n) = tr_mpred(i,n) &',
     9, 'none expected',
     'RED is conservative in TOTAL water, so the ledger cannot see it -- only the '
     'field-vs-counter cross-check can, and only for the plumbing'),

    ('destructive accumulation ordered AFTER the overwrite',
     """             if (present(tr_mpdes)) tr_mpdes(i,n) = tr_mpdes(i,n) &                          ! wvt
                + tr_q(i,k,n)*(1.-q(i,k)/tr_sum)*den(i,k)*delz(i,k)                          ! wvt
             tr_q(i,k,n)=q(i,k)*(tr_q(i,k,n)/tr_sum)                                         ! wvt""",
     """             tr_q(i,k,n)=q(i,k)*(tr_q(i,k,n)/tr_sum)                                         ! wvt
             if (present(tr_mpdes)) tr_mpdes(i,n) = tr_mpdes(i,n) &                          ! wvt
                + tr_q(i,k,n)*(1.-q(i,k)/tr_sum)*den(i,k)*delz(i,k)                          ! wvt""",
     2, 'xcheck',
     'reads the ALREADY-OVERWRITTEN tag; the field then disagrees with the counter by a factor '
     'q/tr_sum -- small (~2%) because the cap fires just as tr_sum crosses q. ⚠ An earlier '
     'version aimed at the ENTRY rescale, which never fires in these probes, so it tested '
     'nothing and read as an uncatchable defect'),

    ('ratio mirror names the WRONG source species',
     'if (qc(i,k).gt.0.) tr_praut(i,k,n) = praut(i,k)/qc(i,k)*tr_qc(i,k,n)',
     'if (qc(i,k).gt.0.) tr_praut(i,k,n) = praut(i,k)/max(qi(i,k),1.e-30)*tr_qi(i,k,n)',
     2, 'none expected',
     'THE DOCUMENTED BLIND SPOT: tr_P = P/X*tr_X collapses to P for ANY X once tr_X = X, so '
     'the identity gate is structurally incapable of seeing it. ⚠ The GUARD must stay '
     '`qc>0`: an earlier version changed it to `qi>0` as well, which breaks the identity '
     'wherever qc>0 and qi==0 -- for a reason that has nothing to do with source species, and '
     'it made a blind spot look like a caught defect'),
]


def run(mode, *args):
    cmd = [str(HERE / 'build.sh'), 'double', mode, *[str(a) for a in args]]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=HERE)
    return p.stdout + p.stderr


def gates():
    """(ledger_residual, identity_residual, worst_xcheck_abs_diff) on the current source.

    ⚠ d1 ONLY for the ledger. d2's snow/graupel/ramp cases carry a residual at baseline -- the
    PLM straddle-cell defect, which is real and still uninstrumented (see the plan, step 3). A
    discriminator that is already non-zero before you mutate anything cannot tell you the mutant
    did it. d1 closes at baseline, so it is the one that discriminates.

    ⚠ ABSOLUTE difference for the cross-check, not relative. The harness prints `rel` computed
    against a max(|counter|,1e-30) floor, so when a counter is legitimately zero the ratio is
    ~1e29 and swamps everything. The first version of this function read those and reported a
    baseline of 2.3e+29.
    """
    # ⚠ EACH DISCRIMINATOR READS THE CASE WHERE IT IS MEANINGFUL -- they are not the same case.
    #   ledger <- d1 at delt=60 (ONE substep), which closes exactly at baseline. At delt=360 the
    #             baseline residual is 9.2e-06: the PLM straddle term stops cancelling between
    #             base and tags once composition evolves across substeps. That is a real
    #             uninstrumented defect (plan step 3), not noise -- but a discriminator with a
    #             non-zero baseline cannot attribute anything to the mutant.
    #   xcheck <- d1 at delt=360, because at delt=60 the vapour cap never fires, DES is
    #             identically zero, and a mutation of the destructive accumulation CANNOT be
    #             caught. A gate that cannot fire is not a gate.
    d1_led = run('d1')
    d1_x = run('d1', 360)
    m = re.search(r'UNCOUNTED TAG MASS\s+(\S+)', d1_led)
    ledger = abs(float(m.group(1))) if m else 0.0
    g1 = run('g1')
    m = re.search(r'per-species residual\s*:\s*(\S+)', g1)
    ident = float(m.group(1)) if m else float('nan')
    # ⚠ d2 as well: its sharp cases drive the post-sedimentation vapour rescale, which is the
    # site the destructive-ordering mutant breaks. Reading only d1 left that mutant uncaught --
    # not because the cross-check is weak, but because the case it was read from never fired DES.
    d2_x = run('d2')
    worst = 0.0
    for line in (g1 + d1_x + d2_x).splitlines():
        m = re.search(r'field\s+(\S+)\s+counter\s+(\S+)', line)
        if m:
            worst = max(worst, abs(float(m.group(1)) - float(m.group(2))))
    return ledger, ident, worst


def main():
    keep = '--keep-going' in sys.argv
    backup = Path(tempfile.mkstemp(prefix='mp_wsm6_', suffix='.F90')[1])
    shutil.copy(SRC, backup)
    print(f'source  : {SRC}')
    print(f'backup  : {backup}\n')
    try:
        b_led, b_id, b_rel = gates()
        print(f'baseline: ledger={b_led:.3e}  identity={b_id:.3e}  worst_xcheck_diff={b_rel:.1e}')
        if b_led > 1e-9:
            print('⚠ BASELINE ALREADY FAILS THE LEDGER — fix that before trusting any row below.\n')
        print(f'\n{"mutant":<52}{"ledger":>10}{"identity":>12}{"xcheck":>10}  {"caught by":<14}')
        print('-' * 100)
        rows = []
        for name, old, new, n_exp, expect, _why in MUTANTS:
            text = backup.read_text()
            n = text.count(old)
            if n != n_exp:
                print(f'{name:<52}{"":>30}  ANCHOR {n} != {n_exp} — fix mutate.py')
                rows.append((name, 'ANCHOR'))
                continue
            SRC.write_text(text.replace(old, new))
            led, ident, rel = gates()
            caught = []
            if led > max(b_led * 1e3, 1e-9):
                caught.append('ledger')
            if ident > max(b_id * 1e3, 1e-9):
                caught.append('identity')
            if rel > max(b_rel * 1e3, 1e-6):
                caught.append('xcheck')
            tag = '+'.join(caught) if caught else '*** NEITHER ***'
            print(f'{name:<52}{led:>10.2e}{ident:>12.2e}{rel:>10.1e}  {tag:<14}')
            rows.append((name, tag))
            shutil.copy(backup, SRC)
            if not caught and not keep and expect != 'none expected':
                print('   ^ expected a gate to catch this; stopping (use --keep-going to continue)')
                break
        print('-' * 100)
        for (name, tag), (_, _, _, _, expect, why) in zip(rows, MUTANTS):
            if tag == 'ANCHOR':
                continue
            ok = (tag == '*** NEITHER ***') == (expect == 'none expected')
            print(f'{"ok " if ok else "!! "}{name}\n     expected {expect!r}, got {tag!r}\n     {why}')
    finally:
        shutil.copy(backup, SRC)
        print(f'\nsource restored from {backup}')


if __name__ == '__main__':
    main()
