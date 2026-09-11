#!/usr/bin/env bash
# Assert that every place a Docker image version is written agrees with every other place.
#
# WHY THIS EXISTS. A version lives in up to four copies and NOTHING reconciles them:
#   1. the build docker-compose.yml `image:`   <- the canonical "what is newest" record
#   2. a downstream Dockerfile `FROM` pin
#   3. that downstream's own build docker-compose.yml `image:`
#   4. per-run IMAGE_VERSION / compose pins in wrf-runs
# A missed copy is silent: the build succeeds and ships the PREVIOUS WRF under a NEW tag.
# 2026-09-11: the FROM pin was bumped (the trap that was written down) and both compose files
# were not (the trap that was not). Knowing one rule is what made the other invisible.
#
# ⚠ (4) IS DELIBERATELY NOT CHECKED. Per-run pins in wrf-runs/projects/** record the image a
# given archive was actually produced with. They are PROVENANCE and must stay frozen; ~50 of them
# reference 1.0-2.0. Never pattern-replace a version across the repo.
#
# Usage: ./check_image_versions.sh [--require-built]
#   --require-built  also assert each build compose's tag exists in `docker images`
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
autoruns="${WVT_AUTORUNS:-$HOME/git/wrf-repos/wrf-auto-runs}"
require_built=0
[[ "${1:-}" == "--require-built" ]] && require_built=1

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
ylw()  { printf '\033[33m%s\033[0m\n' "$*"; }

fail=0
declare -A BUILDS   # image name -> tag declared by the compose that BUILDS it
declare -A SRC      # image name -> which compose declared it

# --- collect every build compose: one that has BOTH `image:` and `build:` -------------------
while IFS= read -r cf; do
    grep -q '^\s*build:' "$cf" || continue
    img="$(grep -oE '^\s*image:\s*\S+' "$cf" | head -1 | awk '{print $2}')"
    [[ -n "$img" ]] || continue
    name="${img%:*}"; tag="${img##*:}"
    if [[ -n "${BUILDS[$name]:-}" && "${BUILDS[$name]}" != "$tag" ]]; then
        red "  CONFLICT  $name declared :$tag in $cf but :${BUILDS[$name]} in ${SRC[$name]}"
        fail=1
    fi
    BUILDS[$name]="$tag"; SRC[$name]="${cf/#$HOME/\~}"
done < <(find "$here" "$autoruns" -name 'docker-compose*.y*ml' -not -path '*/.git/*' 2>/dev/null)

echo "--- build compose files (the canonical version record) ---"
for name in "${!BUILDS[@]}"; do
    printf '    %-48s :%s\n' "$name" "${BUILDS[$name]}"
done

# --- every FROM on one of OUR images must match that image's build compose ------------------
echo "--- FROM pins vs the compose that builds them ---"
checked=0
while IFS= read -r df; do
    while IFS= read -r from; do
        name="${from%:*}"; tag="${from##*:}"
        [[ -n "${BUILDS[$name]:-}" ]] || continue
        checked=$((checked+1))
        if [[ "$tag" != "${BUILDS[$name]}" ]]; then
            red "  MISMATCH  ${df/#$HOME/\~}"
            red "            FROM $name:$tag  but ${SRC[$name]} builds :${BUILDS[$name]}"
            fail=1
        else
            printf '    ok  %-42s FROM %s:%s\n' "$(basename "$(dirname "$df")")" "$name" "$tag"
        fi
    done < <(grep -oE '^FROM\s+\S+/\S+:\S+' "$df" | awk '{print $2}')
done < <(find "$here" "$autoruns" -name Dockerfile -not -path '*/.git/*' 2>/dev/null)
[[ $checked -eq 0 ]] && ylw "  note: no FROM pin referenced a locally-built image -- nothing cross-checked"

# --- optional: the declared tag actually exists ---------------------------------------------
if [[ $require_built -eq 1 ]]; then
    echo "--- declared tags exist locally ---"
    for name in "${!BUILDS[@]}"; do
        if docker image inspect "$name:${BUILDS[$name]}" >/dev/null 2>&1; then
            printf '    ok  %s:%s\n' "$name" "${BUILDS[$name]}"
        else
            # NOT a failure: absence only means "not built on THIS machine", which is normal
            # for the older variants. The invariant this script enforces is that the pins AGREE.
            ylw "  not built here  $name:${BUILDS[$name]} (declared in ${SRC[$name]})"
        fi
    done
fi

echo
if [[ $fail -eq 0 ]]; then
    grn "OK: every FROM pin matches the compose that builds that image"
    grn "⚠ reminder: verify the CONTENT against the binary, not the tag --"
    grn "   strings /WRF/main/wrf.exe | grep -c <symbol only the new code defines>"
    exit 0
fi
red "FAIL: image version pins disagree"
exit 1
