# wrf-wps-intel-wvt-avx512

The `wrf-wps-intel-wvt` image built with `WRF_MARCH=skylake-avx512` — same Dockerfile, same
`debian/wvt-multi/` source, same WPS; only WRF's Fortran/C flags gain `-march=skylake-avx512`.
Everything in `../wrf-wps-intel-wvt/readme.md` applies.

**Why a separate name.** The binary uses AVX-512 and will not start on a host without it. Every
Slurm cluster in use (Hetzner AX162 / EPYC 9454P, NeSI genoa / EPYC 9654, UC RCH) is Zen 4 and
has it; other servers may not. The un-suffixed image stays on the AVX2 baseline for them (`core-avx2` from the bump after 2.4; 2.4 itself is plain x86-64).

**What it buys.** Measured 2026-09-18 on the 99×111 harness (Ryzen 7900, 4 ranks): −2% step time
with tracers off, −7.4% at 12 tagged regions. Record:
`wrf-model-eval/docs/wvt_tracer_cost_assessment.md` §3.7.

**Bit-identity — MEASURED, not assumed.** On the 99×111 / 3 h harness the last wrfout of this
image is **byte-identical (same md5) to `wrf-wps-intel-wvt-ubuntu:2.4`'s**, at 0 regions and at
12 regions, and the two throwaway builds behind the assessment (`core-avx2`, `skylake-avx512`)
match each other and this image field-for-field. That is `-fp-model precise` doing its job: it
forbids the reassociation that wider vectors would otherwise introduce, so the ISA change alters
speed only. ⚠ Established on a 3 h run of one configuration; a longer integration has not been
compared. If it holds there too, gate 0 and the N=1 vs N=4 identity carry over from the generic
image without re-baselining.

**Measured on this image (idle machine, 4 ranks pinned to one CCD, 2026-09-18):** step time
0.317 → 0.303 s at 0 regions (−4.4%), 1.055 → 0.996 s at 12 regions (−5.6%) against `:2.4`.

**Verify the binary, not the tag:** `objdump -d /WRF/main/wrf.exe | grep -c ymm` is ~130 000 here
against ~230 in the generic image.

Build: `docker compose build` in this directory. Downstream: `wrf-auto-runs/intel_wvt_avx512/`.
