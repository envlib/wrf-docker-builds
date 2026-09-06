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
[ "$fail" -eq 0 ] || { echo "FAIL: committed code has drifted from the generators"; exit 1; }
echo "OK: generators and committed code agree at MAX=$MAX"
