# wrf-builds

This repo contains various WRF builds in docker containers. They were built in docker to allow WRF to be run more easily on any machine. The goal is to have several builds of WRF with different components and built in AMD64 and ARM64. Initially, the containers are only built in AMD64.

## References
There are many sources that I drew from to create these builds. It shouldn't be surprising that other people have wanted to have automated WRF builds.

### NCAR docs/repos
- https://github.com/wrf-model/WRF
- https://github.com/wrf-model/WPS
- https://github.com/NCAR/WRF_DOCKER
- https://github.com/NCAR/wrf_hydro_nwm_public
- https://github.com/NCAR/wrf_hydro_docker
- https://www2.mmm.ucar.edu/wrf/OnLineTutorial/compilation_tutorial.php
- https://ral.ucar.edu/sites/default/files/docs/water/howtobuildrunwrfhydrov511instandalonemode.pdf
- https://ral.ucar.edu/sites/default/files/docs/water/howtobuildandrunwrfhydrov511coupledtowrf.pdf

### Linux build scripts
- https://github.com/bakamotokatas/WRF-Install-Script
- https://github.com/jokervTv/auto-install-WRFV4
- https://pratiman-91.github.io/2020/07/28/Installing-WRF-4.2.1-on-Ubuntu-LTS-20.04.html

### Docker scripts
- https://gitee.com/openeuler/openeuler-docker-images/tree/master/HPC/wrf

## Debian builds
The purpose for these builds was to use an up-to-date debian OS to build WRF, WPS, and WRF-Hydro into Docker. 

### wrf-base
The base debian installation for nearly all of the WRF docker containers. This is contained in the folder /debian/base.

### wrf-debian
A build with only WRF installed (no WPS). It has been built for amd64 and arm64. WPS cannot be built for arm64. This is contained in the folder /debian/wrf.
To build containers in arm64 (using an amd64), you'll need to do two things.

1) Install qemu on your OS: sudo apt install qemu-user-static
2) Allow docker to build multi-arch images: https://docs.docker.com/build/building/multi-platform/

### wrf-wps-debian
A build with a WRF and WPS. This is contained in the folder /debian/wrf-wps.

### wrf-wps-hydro-coupled-debian
A build with WRF Hydro coupled with WRF and WPS. This is contained in the folder /debian/wrf-wps-hydro-coupled.

### wrf-hydro-sa-debian
A build with a stand alone WRF-Hydro installation. This is contained in the folder /debian/wrf-hydro-sa.


