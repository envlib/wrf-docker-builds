FROM mullenkamp/wrf-base-debian:1.0

ARG WRF_VERSION=4.7.1
ARG WPS_VERSION=4.6.0

# Compile WRF - must get the release file instead of the archive like in WPS due to NoahMP not contained in the archive
RUN wget https://github.com/wrf-model/WRF/releases/download/v${WRF_VERSION}/v${WRF_VERSION}.tar.gz \
        && tar -zxf v${WRF_VERSION}.tar.gz \
        && mv WRFV${WRF_VERSION} /WRF \
        && rm v${WRF_VERSION}.tar.gz

# Overlay WRF-WVT modifications onto WRF source tree
COPY wvt-single/phys/ /WRF/phys/
COPY wvt-single/dyn_em/ /WRF/dyn_em/
COPY wvt-single/share/ /WRF/share/
COPY wvt-single/Registry/ /WRF/Registry/
COPY wvt-single/main/depend.common /WRF/main/depend.common
COPY wvt-single/main/ndown_em.F /WRF/main/ndown_em.F
COPY wvt-single/run/README.tracers /WRF/run/
COPY wvt-single/run/namelist.input.tracers /WRF/run/

WORKDIR /WRF
RUN sed -i 's#$NETCDF/lib#$NETCDF/lib/x86_64-linux-gnu#g' configure && ( echo 34 ; echo 1 ) | ./configure
RUN sed -i 's#-L/usr/lib -lnetcdff -lnetcdf#-L/usr/lib/x86_64-linux-gnu -lnetcdff -lnetcdf#g' configure.wrf \
    && gfortversion=$(gfortran -dumpversion | cut -d '.' -f 1) && ./compile -j "$(nproc)" em_real

# Compile WPS
RUN wget https://github.com/wrf-model/WPS/archive/v${WPS_VERSION}.tar.gz \
	&& tar -zxf v${WPS_VERSION}.tar.gz \
    && mv WPS-${WPS_VERSION} /WPS \
	&& rm v${WPS_VERSION}.tar.gz

WORKDIR /WPS

COPY patches/output_module.F /WPS/geogrid/src/

# WPS option 2 = Linux x86_64, gfortran (dmpar) — enables parallel metgrid.exe via mpirun.
# Inject -fno-stack-arrays so automatic Fortran arrays are heap-allocated instead of stack-allocated.
# Without it, metgrid.exe risks the same kind of stack-array memory bug that segfaults the Intel build on long preprocessing runs.
RUN sed -i '163s/.*/    NETCDFF="-lnetcdff"/' configure \
    && echo 2 | ./configure --build-grib2-libs \
    && sed -i 's|^FFLAGS *=.*|FFLAGS = $(FORMAT_FREE) -O -fconvert=big-endian -frecord-marker=4 -fno-stack-arrays|' configure.wps \
    && sed -i 's|^F77FLAGS *=.*|F77FLAGS = $(FORMAT_FIXED) -O -fconvert=big-endian -frecord-marker=4 -fno-stack-arrays|' configure.wps \
    && grep -E '^(FFLAGS|F77FLAGS) *=' configure.wps \
    && ./compile

RUN rm /WPS/namelist.wps && rm /WRF/run/namelist.input

WORKDIR /WPS/geogrid

COPY patches/GEOGRID.TBL.nz .

RUN ln -sf GEOGRID.TBL.nz GEOGRID.TBL

WORKDIR /WPS/metgrid

COPY patches/METGRID.TBL.nz .

RUN ln -sf METGRID.TBL.nz METGRID.TBL

WORKDIR /WPS

CMD ["/bin/bash"]
