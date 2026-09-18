#!/usr/bin/env bash
# Verify the committed WVT multi-region code still matches what the Registry generators emit.
#
# The three generators are run BY HAND and their output pasted into Registry.EM,
# registry.moisttracers and six Fortran files (see MULTI_REGION_WIP.md). Nothing enforced
# that the paste stayed in sync, and it had already drifted: gen_wvt_cuten.py SECTION 8 was
# emitting solve_em.F's decouple block one indent level too deep. That is harmless, but the
# same silent drift in an index or a mass variable would not be.
#
# KNOWN LIMITATION: each generated line is searched across Registry.EM, registry.moisttracers
# and all of dyn_em/ phys/ share/ -- not against the specific file its SECTION header names.
# A block pasted into the wrong file would still pass. It does catch the index and expression
# drift that actually matters, which is what it was written for.
#
# This checks every generated line appears as a WHOLE LINE (grep -x) in its target file.
# Whole-line matching is deliberate: a substring match cannot see indentation drift, and
# indentation drift is precisely what had already happened in SECTION 8. It does NOT check the
# reverse (a hand-added line the generator does not know about is fine and expected -- e.g.
# the reflowed comment headers and the fatal `case default`).
#
# Usage:  ./check_generators.sh [MAX]     (default: read from module_check_a_mundo.F)
set -euo pipefail
cd "$(dirname "$0")/.."

MAX="${1:-}"
if [ -z "$MAX" ]; then
  MAX=$(grep -oE 'num_wvt_regions \.GT\. [0-9]+' share/module_check_a_mundo.F | grep -oE '[0-9]+$' | head -1)
fi
echo "checking generators at MAX=$MAX"

# Cross-file bound coupling. module_diag_wvt_columns.F sizes its per-region sum arrays with
# MAXREG but takes nreg from the namelist, so raising the check_a_mundo bound without raising
# MAXREG writes past the end of those arrays instead of failing. They must move together.
MAXREG=$(grep -oE 'MAXREG *= *[0-9]+' phys/module_diag_wvt_columns.F | grep -oE '[0-9]+$' | head -1)
if [ "$MAXREG" != "$MAX" ]; then
  echo "FAIL: MAXREG=$MAXREG in module_diag_wvt_columns.F but the num_wvt_regions bound is $MAX."
  echo "      These size the same per-region arrays; a mismatch is an out-of-bounds write, not an error."
  exit 1
fi
echo "OK: MAXREG == num_wvt_regions bound == $MAX"

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
python3 Registry/gen_wvt_tracers.py "$MAX" > "$tmp/tracers.txt"
python3 Registry/gen_wvt_cuten.py   "$MAX" > "$tmp/cuten.txt"
python3 Registry/gen_wvt_thum.py    "$MAX" > "$tmp/thum.txt"

# Every generated code line must exist somewhere in the overlay. Section headers, comments
# and blank lines are skipped; the generators emit those as paste instructions, not code.
fail=0; checked=0
for f in "$tmp"/*.txt; do
  while IFS= read -r line; do
    case "$line" in ''|'===='*|'#'*|'!'*) continue ;; esac
    [ -z "${line// }" ] && continue
    checked=$((checked+1))
    if ! grep -rqxF -- "$line" Registry/Registry.EM Registry/registry.moisttracers \
         dyn_em/ phys/ share/ 2>/dev/null; then
      echo "  DRIFT: $(basename "$f"): $line"
      fail=$((fail+1))
    fi
  done < "$f"
done

echo "checked $checked generated lines; $fail not found"
drift_fail=$fail
if [ "$drift_fail" -eq 0 ]; then echo "OK: generators and committed code agree at MAX=$MAX"
else echo "DRIFT: committed code has drifted from the generators ($drift_fail line(s)) -- continuing to the package checks"; fi

# ---------------------------------------------------------------------------------------------
# Package hygiene (2026-09-18). The WVT state fields are gated by Registry `package` lines so a
# tracer-off run neither allocates nor writes them. Three ways that silently stops being true:
#
#  (a) a name in a `state:` list that matches no declaration. The registry program only prints
#      "WARNING: <x> is not a member of 4D array state" and continues -- the field is then
#      allocated and written unconditionally, build exit 0. (Names are case-INSENSITIVE: the
#      registry lower-cases every line before tokenising, tools/reg_parse.c make_lower.)
#  (b) a WVT state field declared but listed in no package -- the "new field, forgot to gate"
#      case. Every WVT state in registry.moisttracers / registry.diag_columns must be in some
#      package's `state:` list or on the explicit DEFERRED list below.
#  (c) a registry line longer than the parser reads: tools/reg_parse.c uses fgets(inln, 7000, ..)
#      so anything past 6999 chars is dropped SILENTLY (measured: a 7206-char package line lost
#      its tail with exit 0). Cap at 6000 to leave room.
# ---------------------------------------------------------------------------------------------
REG_FILES="Registry/Registry.EM Registry/Registry.EM_COMMON Registry/registry.moisttracers Registry/registry.diag_columns"
# Stage 2b (deferred 2026-09-18): region-1 RTRQ*CUTEN stay unpackaged -- their only unguarded
# writers are KF/MSKF explicit-shape sites that a bounds-checked build cannot see.
DEFERRED="rtrqvcuten rtrqccuten rtrqrcuten rtrqicuten rtrqscuten"

declared_state() {  # every lower-cased state field name across the registry files.
                    # ^[[:space:]]* because the registry parser skips leading blanks: an
                    # indented declaration is real to WRF and must be real to this check.
  grep -hE '^[[:space:]]*state[[:space:]]' $REG_FILES | awk '{print tolower($3)}' | sort -u
}
packaged_state() {  # every lower-cased name in any package's state: list
  grep -hE '^[[:space:]]*package[[:space:]]+(wvt_|tracer_moist|bucketropt)' $REG_FILES \
    | grep -oE '(^|[;[:space:]])state:[^; ]+' | sed -E 's/^[;[:space:]]?state://' | tr ',' '\n' | tr 'A-Z' 'a-z' | sort -u
}
decl=$(declared_state); pk=$(packaged_state)

fail=0
# (a) every packaged name is declared
for n in $pk; do
  echo "$decl" | grep -qx -- "$n" || { echo "  PACKAGE NAME NOT DECLARED: $n (registry would WARN and leave it un-gated)"; fail=$((fail+1)); }
done
# (b) every WVT state field is packaged or deferred
# WVT state fields: everything declared in registry.moisttracers, the *_TR diagnostics in
# registry.diag_columns, and -- so a stray WVT declaration elsewhere cannot hide -- any
# WVT-looking name in Registry.EM / Registry.EM_COMMON that is not a 4-D tracer member and not
# on the stock allowlist (tr_urb2d* are urban-canopy fields; tr_qc/tr_qi/tr_qs are stock).
STOCK_LOOKALIKES="tr_urb2d tr_urb2d_mosaic tr_qc tr_qi tr_qs"
wvt=$( { grep -hE '^[[:space:]]*state[[:space:]]' Registry/registry.moisttracers | awk '{print tolower($3)}'; \
         grep -hE '^[[:space:]]*state[[:space:]]' Registry/registry.diag_columns | awk '{print tolower($3)}' | grep -E '_tr(_|$)'; \
         grep -hE '^[[:space:]]*state[[:space:]]' Registry/Registry.EM Registry/Registry.EM_COMMON | awk '$5 != "tracer" {print tolower($3)}' \
           | grep -E '^(tr_|i_tr_|rtrq|trmask|trqfx|pwat_tr|vimf_tr)|_tr(_|$)' \
           | grep -vxF -f <(echo "$STOCK_LOOKALIKES" | tr ' ' '\n') || true; } | sort -u )
for n in $wvt; do
  echo "$pk" | grep -qx -- "$n" && continue
  echo " $DEFERRED " | grep -q " $n " && continue
  echo "  WVT STATE NOT PACKAGED: $n (allocated + written even with tracers off)"; fail=$((fail+1))
done
# (d) package CONDITIONS. The gates derive their expectation from this same registry, so a wrong
#     condition (say tracer_opt==5 on wvt_state) would be consistently wrong everywhere and pass
#     every runtime gate while the physics guards (keyed on P_QV_TR, i.e. tracer_moist) say "on"
#     -- an out-of-bounds write no gate would see. So: wvt_state must carry EXACTLY tracer_moist's
#     condition, and wvt_cuten_nrN / wvt_thum_nrN must carry num_wvt_regions==N with members
#     that are exactly regions 2..N (review round wvt-pkg-code-1, finding 1).
# `|| true` throughout: under set -o pipefail a grep with no match is exit 1, and that would
# abort the script silently instead of reporting (it did, first time round).
cond_of() { { grep -hE "^[[:space:]]*package[[:space:]]+$1[[:space:]]" $REG_FILES || true; } | awk '{print $3}' | head -1; }
tm=$(cond_of tracer_moist); ws=$(cond_of wvt_state)
if [ -z "$ws" ] || [ "$ws" != "$tm" ]; then
  echo "  PACKAGE CONDITION: wvt_state has '$ws' but tracer_moist has '$tm' -- they must be identical"; fail=$((fail+1))
fi
for pkg in $( { grep -hoE '^[[:space:]]*package[[:space:]]+wvt_(cuten|thum)_nr[0-9]+' $REG_FILES || true; } | awk '{print $2}'); do
  N=${pkg##*_nr}; c=$(cond_of "$pkg")
  [ "$c" = "num_wvt_regions==$N" ] || { echo "  PACKAGE CONDITION: $pkg has '$c', expected 'num_wvt_regions==$N'"; fail=$((fail+1)); }
  want=$(seq -f '%02g' 2 "$N" | sort -u | tr '\n' ' ')
  have=$( { grep -hE "^[[:space:]]*package[[:space:]]+$pkg[[:space:]]" $REG_FILES | grep -oE 'state:[^; ]+' | sed 's/^state://' | tr ',' '\n' | grep -oE '_[0-9]+$' || true; } | tr -d '_' | sort -u | tr '\n' ' ')
  [ "$have" = "$want" ] || { echo "  PACKAGE MEMBERS: $pkg lists regions [$have], expected [$want]"; fail=$((fail+1)); }
done
# (c) line length
while IFS= read -r ln; do
  echo "  REGISTRY LINE OVER 6000 CHARS (parser reads 6999 then truncates silently): $(echo "$ln" | cut -c1-60)..."; fail=$((fail+1))
done < <(awk 'length($0) > 6000' $REG_FILES)
if [ "$fail" -eq 0 ]; then
  echo "OK: package hygiene -- $(echo "$pk" | wc -l) packaged state names all declared; every WVT state packaged or deferred; conditions pinned; no registry line over 6000 chars"
else
  echo "FAIL: package hygiene ($fail problem(s))"
fi
[ "$fail" -eq 0 ] && [ "$drift_fail" -eq 0 ] || { echo "FAIL: check_generators (drift=$drift_fail, hygiene=$fail)"; exit 1; }
