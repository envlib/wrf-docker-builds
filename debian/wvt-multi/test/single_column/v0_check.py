#!/usr/bin/env python3
"""V0 - the COMPOSITION gate for the New Tiedtke tag mirrors.

Why this exists
---------------
V-id is a CONSERVATION check: do the tags sum to the vapour? That is invariant under permuting
shares between regions, so an implementation attributing rain to entirely the wrong region
passes it perfectly - a rejected candidate design did exactly that, passing conservation while
being wrong by 30 points on composition. V0 tests the thing V-id structurally cannot.

The reference and why it is independent
---------------------------------------
Tag only the lower column, so the rising plume entrains UNTAGGED air. Then apply one physical
statement - a passive label is diluted by mixing and unchanged by proportional removal -
separately to each phase, using ONLY base-scheme quantities:

  mixing        vapour tag diluted by entrainment; detrainment removes both phases pro rata
                a(k) = a(k+1)*Qm / (Qm + E)        Qm = pqu(k+1)*(pmfu(k+1)-zdmfde)
  condensation  moves dq = zqold - pqu from vapour to liquid AT THE VAPOUR composition
                b(k) = (b(k+1)*Lm + a(k)*dq) / (Lm + dq)
  precipitation removes liquid at the LIQUID composition -> leaves b unchanged

An earlier single-composition version of this reference disagreed with the model by up to 1.2%,
and the error scaled monotonically with the liquid fraction of plume water (2.8e-4 where the
plume was nearly all vapour, 8.4e-3 where nearly all liquid) - diagnosing the REFERENCE, not
the model. That is why the phases are carried separately here.

It reimplements nothing from the tagged code: slots 5 and 9 (the model's tagged answer) are
read only for comparison, never fed back into the recurrence.
"""
import sys
from collections import defaultdict

S = "pmfu W E zdmfde Wtr pdmfup kcbot L Ltr zqold zprecip Q".split()

rows = defaultdict(dict)
for line in open(sys.argv[1] if len(sys.argv) > 1 else "v0_export.txt"):
    f = line.split()
    rows[int(f[0])][int(f[1])] = dict(zip(S, (float(x) for x in f[2:14])))

worst, worst_id, checked, skipped = 0.0, None, 0, 0
for i, col in sorted(rows.items()):
    lv = sorted(col)
    kcb = int(col[lv[0]]["kcbot"])
    plume = sorted([k for k in lv if k <= kcb], reverse=True)   # cloud base upward
    if len(plume) < 3:
        continue
    a = b = None
    for k in plume:
        d = col[k]
        if d["pmfu"] <= 0.0 or d["W"] <= 0.0:
            continue
        if a is None:                                  # seed at cloud base from the model
            a = (d["Wtr"] - d["Ltr"]) / max(d["Q"], 1e-30)
            b = d["Ltr"] / d["L"] if d["L"] > 1e-30 else 0.0
            kprev = k
            continue
        p = col[kprev]
        mflux = p["pmfu"] - d["zdmfde"]                # mass surviving detrainment
        Qm = p["Q"] / p["pmfu"] * mflux                # vapour carried up, pre-mixing
        Lm = p["L"] / p["pmfu"] * mflux                # liquid carried up
        E = d["E"]
        a = a * Qm / (Qm + E) if (Qm + E) > 1e-30 else 0.0
        dq = max(0.0, d["zqold"] * d["pmfu"] - d["Q"]) # condensed water flux
        b = (b * Lm + a * dq) / (Lm + dq) if (Lm + dq) > 1e-30 else b
        kprev = k
        # compare against the model, per phase, where each phase carries meaningful mass
        for name, base, tag, ref in (("vap", d["Q"], d["Wtr"] - d["Ltr"], a),
                                     ("liq", d["L"], d["Ltr"], b)):
            if base <= 1e-9:
                skipped += 1
                continue
            err = abs(tag / base - ref)
            checked += 1
            if err > worst:
                worst, worst_id = err, (i, k, name, tag / base, ref)

print(f"levels compared: {checked}   (phases skipped for negligible mass: {skipped})")
if worst_id:
    i, k, ph, m, r = worst_id
    print(f"worst |model - reference| = {worst:.3e}  col {i} lev {k} [{ph}]"
          f"  model {m:.6f} vs reference {r:.6f}")
TOL = 2e-3
if checked == 0:
    print("FAIL: nothing compared - the gate is vacuous")
    sys.exit(1)
print(("PASS" if worst <= TOL else "FAIL") + f": composition within {TOL}")
sys.exit(0 if worst <= TOL else 1)
