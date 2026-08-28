#!/usr/bin/env bash
# Assert that the WVT source overlays here and the integrated WRF fork agree.
#
# WHY THIS EXISTS: the same WVT source lives in two places -- the overlays in this repo (where
# development happens, and which the Docker images compile) and the WRF-WVT fork (the integrated
# tree kept for a possible upstream contribution). Nothing detected three months of drift between
# them. This is the check that would have.
#
# WHAT A CLEAN RUN PROVES. The image's WRF tree is the stock v4.7.1 release tarball with the
# overlay copied over it. So if every overlay file matches the fork, and the fork changes no other
# file relative to v4.7.1, then no Fortran, Registry, include or makefile source that the compile
# consumes differs between the two. That is the whole claim, and it is stronger than compiling the
# fork once.
#
# WHAT IT DOES NOT PROVE, precisely:
#   * The builds are not literally "tarball + overlay and nothing else". The gfortran images sed a
#     library path into WRF's own ./configure, and all four rm /WRF/run/namelist.input after
#     compiling. Neither touches compiled source.
#   * The builds untar the v4.7.1 RELEASE TARBALL; the fork sits on the v4.7.1 GIT TAG. These agree
#     byte-for-byte on every file both contain, but the tarball additionally ships the
#     tools/manage_externals checkouts -- phys/physics_mmm (15 files, of which the fork carries the
#     3 that WVT modifies), phys/noahmp, phys/MYNN-EDMF, .ci/hpc-workflows. The fork is therefore
#     NOT self-sufficient for a build; build from the overlay.
#
# Usage:  ./check_fork_sync.sh [--quiet]
#         WRF_WVT=/path/to/WRF-WVT ./check_fork_sync.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORK="${WRF_WVT:-$HOME/git/wrf-repos/WRF-WVT}"
QUIET=0; [[ "${1:-}" == "--quiet" ]] && QUIET=1

# The single-region overlay is frozen; this tag is the fork commit that matches it exactly.
SR_TAG="wvt-4.7.1-single-region"
BASE_TAG="v4.7.1"

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
ylw()  { printf '\033[33m%s\033[0m\n' "$*"; }
say()  { [[ $QUIET -eq 1 ]] || printf '%s\n' "$*"; }

[[ -d "$FORK/.git" ]] || { red "FAIL: no git repo at $FORK (set WRF_WVT)"; exit 2; }

hard=0; warn=0

# Map an overlay-relative path to its path inside the fork.
# The only divergence is the overlay's test/ -> the fork's test/wvt/, which keeps WRF's own
# test/ (idealised case directories) uncluttered.
fork_path() {
    case "$1" in
        test/*) printf 'test/wvt/%s' "${1#test/}" ;;
        *)      printf '%s' "$1" ;;
    esac
}

# Is this overlay file part of what the Dockerfiles COPY into the image? Mismatches inside this
# set are production-source drift and fail hard; everything else is auxiliary and warns.
# Mirrors the eight COPY lines in the WVT Dockerfiles.
is_image_source() {
    case "$1" in
        phys/*|dyn_em/*|share/*|Registry/*) return 0 ;;
        main/depend.common|main/ndown_em.F) return 0 ;;
        run/README.tracers|run/namelist.input.tracers) return 0 ;;
        *) return 1 ;;
    esac
}

compare_overlay() {   # $1 = overlay dir name
    local ov="$1" root="$HERE/$1" rel tgt
    [[ -d "$root" ]] || { red "FAIL: no overlay at $root"; hard=$((hard+1)); return; }
    say "--- $ov vs $(basename "$FORK") ---"
    local n_ok=0 n_bad=0
    while IFS= read -r rel; do
        tgt="$FORK/$(fork_path "$rel")"
        if [[ ! -f "$tgt" ]]; then
            if is_image_source "$rel"; then red "  MISSING  $ov/$rel"; hard=$((hard+1))
            else                            ylw "  missing  $ov/$rel"; warn=$((warn+1)); fi
            n_bad=$((n_bad+1))
        elif ! cmp -s "$root/$rel" "$tgt"; then
            if is_image_source "$rel"; then red "  DIFFERS  $ov/$rel"; hard=$((hard+1))
            else                            ylw "  differs  $ov/$rel"; warn=$((warn+1)); fi
            n_bad=$((n_bad+1))
        else
            n_ok=$((n_ok+1))
        fi
    done < <(cd "$root" && find . -type f | sed 's|^\./||' | sort)
    say "    $n_ok identical, $n_bad mismatched"
}

# 1. EQUALITY -- the live multi-region overlay against the fork tip.
compare_overlay wvt-multi

# 2. EQUALITY -- the frozen single-region overlay against its tag. Nearly free, and it is what the
#    two single-region production images compile.
if git -C "$FORK" rev-parse -q --verify "$SR_TAG^{commit}" >/dev/null; then
    say "--- wvt-single vs $SR_TAG ---"
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    git -C "$FORK" archive "$SR_TAG" | tar -x -C "$tmp"
    n_ok=0; n_bad=0
    while IFS= read -r rel; do
        if [[ ! -f "$tmp/$rel" ]] || ! cmp -s "$HERE/wvt-single/$rel" "$tmp/$rel"; then
            red "  DIFFERS  wvt-single/$rel"; hard=$((hard+1)); n_bad=$((n_bad+1))
        else n_ok=$((n_ok+1)); fi
    done < <(cd "$HERE/wvt-single" && find . -type f | sed 's|^\./||' | sort)
    say "    $n_ok identical, $n_bad mismatched"
else
    ylw "  tag $SR_TAG not found in $FORK -- single-region check skipped"; warn=$((warn+1))
fi

# 3. CONTAINMENT -- the fork must carry no WVT change the overlay lacks. Without this, equality
#    alone would pass a fork that had grown an extra modified file.
say "--- containment: fork changes vs $BASE_TAG ---"
allow="$(mktemp)"; trap 'rm -f "$allow"' EXIT
{
    (cd "$HERE/wvt-multi"  && find . -type f | sed 's|^\./||' | while read -r r; do fork_path "$r"; echo; done)
    (cd "$HERE/wvt-single" && find . -type f | sed 's|^\./||')
    echo CONTRIBUTING.md          # the fork's own contribution guide; deliberately not in an overlay
} | sort -u > "$allow"

extra="$(git -C "$FORK" diff --name-only "$BASE_TAG" HEAD | sort -u | comm -23 - "$allow")"
if [[ -n "$extra" ]]; then
    red "  the fork modifies files no overlay contains:"
    printf '    %s\n' $extra
    hard=$((hard+$(printf '%s\n' "$extra" | wc -l)))
else
    say "    clean -- no fork-only modifications"
fi

echo
if   [[ $hard -gt 0 ]]; then red "FAIL: $hard production-source mismatch(es), $warn auxiliary"; exit 1
elif [[ $warn -gt 0 ]]; then ylw "WARN: $warn auxiliary mismatch(es); production source is in sync"; exit 0
else                         grn "OK: overlays and fork agree"; exit 0
fi
