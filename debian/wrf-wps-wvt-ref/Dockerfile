# WRF 4.3.3 + Original WVT — FROZEN PROVENANCE REFERENCE. See FREEZE.md (provenance, checksums,
# pinned inputs, archive procedure). The original WVT modules (debian/wvt-ref/modules_tracers_4.3.3.tar)
# are the method authors' unmodified code — this is the citable origin reference, not a production build.
# Uses Debian 11 (GCC 10) because WRF 4.3.3 doesn't compile cleanly with GCC 13+; base pinned by digest
# (debian:11-slim, linux/amd64, observed 2026-06-26 — re-derive via `docker manifest inspect debian:11-slim`).
FROM debian:11-slim@sha256:7d5a9679452f9a25d9c8ef2fcb3b9ba0cd1653799a998591292aec1679fad7a2

RUN apt-get update && apt-get install -y \
    build-essential csh gfortran m4 curl perl mpich \
    libhdf5-mpich-dev libpng-dev netcdf-bin libnetcdff-dev \
    wget cmake nano tcsh gcc g++ bash zlib1g zlib1g-dev \
    git vim python3 python3-numpy nco unzip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

RUN curl https://rclone.org/install.sh | bash

ENV CC=gcc
ENV CXX=g++
ENV FC=gfortran
ENV FCFLAGS=-m64
ENV F77=gfortran
ENV FFLAGS=-m64
ENV NETCDF=/usr
ENV HDF5=/usr/lib/x86_64-linux-gnu/hdf5/serial
ENV LDFLAGS="-L/usr/lib/x86_64-linux-gnu/hdf5/serial/ -L/usr/lib"
ENV CPPFLAGS="-I/usr/include/hdf5/serial/ -I/usr/include"
ENV LD_LIBRARY_PATH=/usr/lib
ENV JASPERINC=/WPS/grib2/include
ENV JASPERLIB=/WPS/grib2/lib

RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN uv tool install era5_to_int==0.3.0

# Compile WRF 4.3.3
ARG WRF_VERSION=4.3.3
RUN wget https://github.com/wrf-model/WRF/archive/refs/tags/v${WRF_VERSION}.tar.gz \
        && tar -zxf v${WRF_VERSION}.tar.gz \
        && mv WRF-${WRF_VERSION} /WRF \
        && rm v${WRF_VERSION}.tar.gz

# Overlay original WRF-WVT modifications (unmodified 4.3.3 tar from the authors)
COPY wvt-ref/modules_tracers_4.3.3.tar /WRF/
RUN cd /WRF && tar -xf modules_tracers_4.3.3.tar && rm modules_tracers_4.3.3.tar

WORKDIR /WRF
RUN sed -i 's#$NETCDF/lib#$NETCDF/lib/x86_64-linux-gnu#g' configure && ( echo 34 ; echo 1 ) | ./configure
RUN sed -i 's#-L/usr/lib -lnetcdff -lnetcdf#-L/usr/lib/x86_64-linux-gnu -lnetcdff -lnetcdf#g' configure.wrf \
    && ./compile -j "$(nproc)" em_real

# Compile WPS
ARG WPS_VERSION=4.6.0
RUN wget https://github.com/wrf-model/WPS/archive/v${WPS_VERSION}.tar.gz \
    && tar -zxf v${WPS_VERSION}.tar.gz \
    && mv WPS-${WPS_VERSION} /WPS \
    && rm v${WPS_VERSION}.tar.gz

WORKDIR /WPS

COPY patches/output_module.F /WPS/geogrid/src/

RUN sed -i '163s/.*/    NETCDFF="-lnetcdff"/' configure && echo 1 | ./configure --build-grib2-libs && ./compile

RUN rm /WPS/namelist.wps && rm /WRF/run/namelist.input

WORKDIR /WPS/geogrid

COPY patches/GEOGRID.TBL.nz .

RUN ln -sf GEOGRID.TBL.nz GEOGRID.TBL

WORKDIR /WPS/metgrid

COPY patches/METGRID.TBL.nz .

RUN ln -sf METGRID.TBL.nz METGRID.TBL

WORKDIR /WPS

CMD ["/bin/bash"]
