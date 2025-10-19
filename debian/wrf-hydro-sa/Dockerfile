FROM mullenkamp/wrf-debian-base:1.0

# install nccmp manually instead of with conda to save space
ENV NCCMP=1.9.1.0
WORKDIR /tmp
RUN wget -q https://gitlab.com/remikz/nccmp/-/archive/${NCCMP}/nccmp-${NCCMP}.tar.gz \
    && tar -zxf nccmp-${NCCMP}.tar.gz \
    && mv nccmp-${NCCMP} /nccmp \
    && cmake -B /nccmp/build -S /nccmp \
    && make -C /nccmp/build -j install

# cleanup
RUN rm -rf /tmp/*

## WRF-Hydro vars
### linux vars
ARG HYDRO_VERSION=5.4.0

ENV NETCDF=/usr/local
ENV NCDIR=/usr/local
ENV NETCDF_LIB=/usr/local/lib
ENV NETCDF_INC=/usr/local/include

### This is a WRF environment variable. Always set to 1=On for compiling WRF-Hydro.
ENV WRF_HYDRO=1

### Spatially distributed parameters for NoahMP: 0=Off, 1=On.
ENV SPATIAL_SOIL=1

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

RUN wget https://github.com/NCAR/wrf_hydro_nwm_public/archive/refs/tags/v${HYDRO_VERSION}.tar.gz \
    && tar -zxf v${HYDRO_VERSION}.tar.gz \
    && mv wrf_hydro_nwm_public-${HYDRO_VERSION} /wrf_hydro \
    && rm v${HYDRO_VERSION}.tar.gz
    
WORKDIR /wrf_hydro    

## Compile hydro
RUN cmake -B build \
    && make -C build -j

## Setup test data
WORKDIR /wrf_hydro/build
RUN make croton

WORKDIR /wrf_hydro/build/Run

CMD ["/bin/bash"]