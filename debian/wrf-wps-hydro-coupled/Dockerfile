FROM mullenkamp/wrf-debian-base:1.0

# Compile WRF and WRF-Hydro
## WRF/linux vars
ARG WRF_VERSION=4.7.1
ARG WPS_VERSION=4.6.0
ARG HYDRO_VERSION=5.4.0

## WRF-Hydro vars
### This is a WRF environment variable. Always set to 1=On for compiling WRF-Hydro.
ENV WRF_HYDRO=1

### Spatially distributed parameters for NoahMP: 0=Off, 1=On.
ENV SPATIAL_SOIL=1

### Set to 1 if using a WRF/WRF-Hydro coupled build
ENV WRFIO_NCD_LARGE_FILE_SUPPORT=1

### RAPID routing model: 0=Off, 1=On. Option 1 is not currently supported.
ENV WRF_HYDRO_RAPID=0

### WCOSS file units: 0=Off, 1=On. Set to 1 if compile for NOAA WCOSS.
ENV NCEP_WCOSS=0

### NWM output metadata: 0=Off, 1=On. Set to 1 if using NWM-style metadata in output.
ENV NWM_META=0

### Streamflow nudging: 0=Off, 1=On.
ENV WRF_HYDRO_NUDGING=0

### Coupling with NUOPC: 0=Off, 1=On. Option 1 is not currently supported.
ENV DWRF_HYDRO_RAPID=0

### Enhanced diagnostic output for debugging: 0=Off, 1=On.
ENV HYDRO_D=0

### Set to 1 to output channel network diagnostic information
ENV OUTPUT_CHAN_CONN=0

## Get WRF source code - must get the release file instead of the archive like in WPS due to NoahMP not contained in the archive
RUN wget https://github.com/wrf-model/WRF/releases/download/v${WRF_VERSION}/v${WRF_VERSION}.tar.gz \
        && tar -zxf v${WRF_VERSION}.tar.gz \
        && mv WRFV${WRF_VERSION} /WRF \
        && rm v${WRF_VERSION}.tar.gz

### Remove existing hydro folder - DO NOT DO THIS! There seems to be some reliance on existing files.
# RUN rm -r -f /WRF/hydro

## Get WRF-Hydro source code
RUN wget https://github.com/NCAR/wrf_hydro_nwm_public/archive/v${HYDRO_VERSION}.tar.gz \
	&& tar -zxf v${HYDRO_VERSION}.tar.gz \
    && mv wrf_hydro_nwm_public-${HYDRO_VERSION}/src /WRF/hydro \
	&& rm v${HYDRO_VERSION}.tar.gz

## Compile WRF with Hydro
WORKDIR /WRF
RUN sed -i 's#$NETCDF/lib#$NETCDF/lib/x86_64-linux-gnu#g' configure && ( echo 34 ; echo 1 ) | ./configure
RUN sed -i 's#-L/usr/lib -lnetcdff -lnetcdf#-L/usr/lib/x86_64-linux-gnu -lnetcdff -lnetcdf#g' configure.wrf && gfortversion=$(gfortran -dumpversion | cut -d '.' -f 1) && ./compile -j "$(nproc)" em_real

# Compile WPS   
RUN wget https://github.com/wrf-model/WPS/archive/v${WPS_VERSION}.tar.gz \
	&& tar -zxf v${WPS_VERSION}.tar.gz \
    && mv WPS-${WPS_VERSION} /WPS \
	&& rm v${WPS_VERSION}.tar.gz

WORKDIR /WPS
COPY output_module.F /WPS/geogrid/src/

RUN sed -i '163s/.*/    NETCDFF="-lnetcdff"/' configure && echo 1 | ./configure --build-grib2-libs && ./compile

CMD ["/bin/bash"]