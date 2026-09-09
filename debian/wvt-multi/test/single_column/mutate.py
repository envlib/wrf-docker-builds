#!/usr/bin/env python3
"""V6 mutation set for the New Tiedtke tag mirrors.

Each mirror is reverted singly and the identity harness re-run. A mirror whose removal does
NOT break V-id is either unnecessary or untested by these soundings - both are findings, and
both are invisible if you only ever run the passing case. This is the whole point: a check
earns belief by failing against the defect it was written for.
"""
import subprocess, shutil, sys, re, os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(HERE, '..', '..', 'phys', 'physics_mmm', 'cu_ntiedtke.F90')
BAK  = '/tmp/cu_ntiedtke_v6_backup.F90'

MUTANTS = [
 ("1  cloud-base parcel tag ratio",
  "            pqu_tr(jl,ikb) = ztr_rsub*pqu(jl,ikb)                       ! wvt",
  "            pqu_tr(jl,ikb) = min(pqenh_tr(jl,ikb),pqu(jl,ikb)) ! MUTANT"),
 ("2  cloud-base parcel LIQUID tag",
  "            plu_tr(jl,ikb) = ztr_rsub*plu(jl,ikb)                       ! wvt",
  "            plu_tr(jl,ikb) = 0.0 ! MUTANT"),
 ("3  environment half-level rewrite",
  "                if (l_tracers) pqenh_tr(jl,jk) =                       & ! wvt",
  "                if (.false.) pqenh_tr(jl,jk) =                         & ! MUTANT"),
 ("4  cudlfsn LFS wet-bulb evaporation",
  "     &                          - 0.5*zcond(jl)*ztr_r                    ! wvt",
  "     &                          - 0.0*zcond(jl)*ztr_r                    ! MUTANT"),
 ("5  cuddrafn downdraft evaporation",
  "              pdmfdp_tr(jl,jk-1) = zdmfdp*ztr_r                          ! wvt",
  "              pdmfdp_tr(jl,jk-1) = 0.0 ! MUTANT"),
 ("6  cuflxn tagged-flux accumulation",
  "     &        + pdmfup_tr(jl,jk) + pdmfdp_tr(jl,jk)                   ! wvt",
  "     &        + pdmfup_tr(jl,jk)                                      ! MUTANT"),
 ("7  cuflxn sub-cloud evaporation",
  "                pdmfup_tr(jl,jk) = pdmfup_tr(jl,jk) + zdrfl*ztr_clp    ! wvt",
  "                pdmfup_tr(jl,jk) = pdmfup_tr(jl,jk)                    ! MUTANT"),
 ("8  cumastrn zmfuub correction",
  "            zmflx_tr(jl,jk+1) = zmflx_tr(jl,jk+1) + zmfuub_tr(jl)      ! wvt",
  "            zmflx_tr(jl,jk+1) = zmflx_tr(jl,jk+1)                      ! MUTANT"),
 ("9  cumastrn :1051 flux-divergence recompute",
  "            zdmfup_tr(jl,jk) = zmflx_tr(jl,jk+1) - zmflx_tr(jl,jk)      ! wvt",
  "            zdmfup_tr(jl,jk) = zdmfup_tr(jl,jk) ! MUTANT"),
 ("10 zmfdq draught-top clamp",
  "            if (l_tracers) zmfdq_tr(jl,jk) = 0.3*zmfdq_tr(jl,ik)        ! wvt",
  "            if (.false.) zmfdq_tr(jl,jk) = 0.3*zmfdq_tr(jl,ik)          ! MUTANT"),
 ("11 plude proportional repair",
  "              plude_tr(jl,jk) = plude_tr(jl,jk)*(plude(jl,jk)/zplude_old)! wvt",
  "              plude_tr(jl,jk) = min(plude_tr(jl,jk),plude(jl,jk)) ! MUTANT"),
 ("12 cubasmcn mid-level parcel",
  "              pqu_tr(jl,kk+1)=pqv_tr(jl,kk)                              ! wvt",
  "              pqu_tr(jl,kk+1)=0.0 ! MUTANT"),
 ("13 precip removed at VAPOUR not LIQUID ratio",
  "                ztr_frac = plu_tr(jl,jk) / max(plu(jl,jk)+zprecip(jl),  & ! wvt\n     &                     1.0e-10)                                      ! wvt",
  "                ztr_frac = pqu_tr(jl,jk) / max(pqu(jl,jk), 1.0e-10)      ! MUTANT"),
]

def total():
    """V-id: conservation. Does the tagged vapour still equal the base vapour?"""
    r = subprocess.run([os.path.join(HERE,'build.sh')], capture_output=True, text=True)
    m = re.search(r'TOTAL TAG INCONSISTENCY.*?:\s*(\S+)', r.stdout)
    if not m:
        return None, (r.stdout+r.stderr)[-400:]
    return float(m.group(1).replace('E','e')), None

def partition():
    """Partition gate: run a lower member, its complement, and the full tag on identical
    soundings. The member SUM is conservation (exact); the informative number is CAP ACTIVITY
    on the members - composition silently redistributed between regions. This is the gate that
    caught the mirror-1 off-by-one, which V-id and V0 both passed."""
    r = subprocess.run([os.path.join(HERE,'build.sh'),'double','','part'],
                       capture_output=True, text=True)
    m = re.search(r'cap activity on members =\s*(\S+)', r.stdout)
    return float(m.group(1)) if m else None

def composition():
    """V0: attribution. Does the tagged FRACTION match an independent reference?"""
    subprocess.run([os.path.join(HERE,'build.sh'),'double','','v0'],
                   capture_output=True, text=True)
    r = subprocess.run(['python3', os.path.join(HERE,'v0_check.py'),
                        os.path.join(HERE,'v0_export.txt')], capture_output=True, text=True)
    m = re.search(r'worst \|model - reference\| = (\S+)', r.stdout)
    return float(m.group(1)) if m else None

shutil.copy(SRC, BAK)
base, err = total()
if base is None:
    print("baseline build FAILED:\n", err); sys.exit(1)
base_v0 = composition()
base_pt = partition()
print(f"baseline: V-id {base:.4e}   V0 {base_v0:.3e}   partition {base_pt:.4g} kg/m2\n")
print(f"{'mirror reverted':<40} {'V-id':>10} {'V0':>9} {'partition':>10}   caught by")
print("-"*84)
fails = 0
for name, old, new in MUTANTS:
    s = open(BAK).read()
    if s.count(old) != 1:
        print(f"{name:<45} {'--':>12}   ANCHOR NOT UNIQUE ({s.count(old)}) - fix mutate.py")
        continue
    open(SRC,'w').write(s.replace(old, new))
    t, err = total()
    c = composition()
    q = partition()
    shutil.copy(BAK, SRC)
    if t is None:
        print(f"{name:<40} {'--':>10} {'--':>9} {'--':>10}   BUILD FAILED"); continue
    hit_id = t > max(base*1e3, 1e-8)
    hit_v0 = c is not None and c > 2e-3
    hit_pt = q is not None and base_pt and abs(q - base_pt) > 0.05*base_pt
    who = " + ".join([g for g, h in (("V-id", hit_id), ("V0", hit_v0),
                                     ("part", hit_pt)) if h]) or "*** NEITHER ***"
    cs = f"{c:>9.3e}" if c is not None else f"{'--':>9}"
    qs = f"{q:>10.4g}" if q is not None else f"{'--':>10}"
    print(f"{name:<40} {t:>10.4e} {cs} {qs}   {who}")
    if hit_id or hit_v0 or hit_pt:
        fails += 1
print("-"*80)
print(f"{fails}/{len(MUTANTS)} mutants detected by at least one gate")
print()
print("READ THE COLUMNS SEPARATELY - the two gates test different properties:")
print("  V-id  conservation. Blind to attribution: mutant 13 permutes composition while")
print("        conserving mass, and V-id cannot see it.")
print("  part  composition redistributed between two complementary members by the caps.")
print("        Caught the mirror-1 off-by-one that V-id and V0 both passed. Its baseline is")
print("        NOT zero - it measures a real structural effect, so it gates on CHANGE (5%).")
print("  V0    composition, and ONLY of the UPDRAFT PLUME. It is blind to mirrors in the")
print("        downdraft, precipitation-flux and tendency paths, which is why most rows")
print("        show it sitting at its baseline. Surface-rain attribution is NOT yet gated.")
print("A mutant caught by NEITHER means the mirror is unnecessary, or these soundings do")
print("not exercise it. Either way it is unverified - do not treat it as covered.")
