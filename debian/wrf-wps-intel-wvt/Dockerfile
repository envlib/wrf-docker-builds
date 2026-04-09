###############################################################################
# Stage 1: Builder — compile HDF5, NetCDF, WRF+WVT, and WPS with Intel oneAPI
###############################################################################
FROM intel/oneapi-hpckit:2025.3.1-0-devel-ubuntu24.04 AS builder

# Install system tools to match wrf-base functionality
RUN apt-get update && apt-get install -y \
    m4 curl perl libpng-dev wget cmake nano tcsh bash \
    zlib1g zlib1g-dev git vim python3 python3-numpy \
    pipx nco libeccodes-tools unzip csh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

RUN curl https://rclone.org/install.sh | bash

# Intel compiler env vars
ENV CC=icx
ENV CXX=icpx
ENV FC=ifx
ENV F77=ifx
# Tell Intel MPI wrappers (mpif90, mpicc) to use Intel compilers instead of defaulting to gfortran/gcc
ENV I_MPI_F90=ifx
ENV I_MPI_CC=icx

# Common install prefix for HDF5, NetCDF-C, and NetCDF-Fortran
# Using a shared prefix avoids library path issues in WRF's nc4_test
ENV LIBPREFIX=/usr/local

# Build HDF5 from source with Intel compilers
ARG HDF5_VERSION=1.14.6
RUN wget https://github.com/HDFGroup/hdf5/releases/download/hdf5_${HDF5_VERSION}/hdf5-${HDF5_VERSION}.tar.gz \
    && tar -xzf hdf5-${HDF5_VERSION}.tar.gz && cd hdf5-${HDF5_VERSION} \
    && CC=icx FC=ifx ./configure --prefix=$LIBPREFIX --enable-fortran --enable-shared \
    && make -j$(nproc) && make install \
    && ldconfig \
    && cd / && rm -rf hdf5-${HDF5_VERSION}*

# Build NetCDF-C from source with Intel compilers
ARG NETCDF_C_VERSION=4.9.2
RUN wget https://github.com/Unidata/netcdf-c/archive/v${NETCDF_C_VERSION}.tar.gz \
    && tar -xzf v${NETCDF_C_VERSION}.tar.gz && cd netcdf-c-${NETCDF_C_VERSION} \
    && CC=icx ./configure --prefix=$LIBPREFIX --disable-dap --disable-libxml2 --disable-byterange \
    && make -j$(nproc) && make install \
    && ldconfig \
    && cd / && rm -rf netcdf-c-${NETCDF_C_VERSION}* v${NETCDF_C_VERSION}.tar.gz

# Build NetCDF-Fortran from source with Intel compilers
ARG NETCDF_F_VERSION=4.6.1
RUN wget https://github.com/Unidata/netcdf-fortran/archive/v${NETCDF_F_VERSION}.tar.gz \
    && tar -xzf v${NETCDF_F_VERSION}.tar.gz && cd netcdf-fortran-${NETCDF_F_VERSION} \
    && FC=ifx CC=icx ./configure --prefix=$LIBPREFIX \
    && make -j$(nproc) && make install \
    && ldconfig \
    && cd / && rm -rf netcdf-fortran-${NETCDF_F_VERSION}* v${NETCDF_F_VERSION}.tar.gz

# Set library paths for WRF/WPS builds
ENV NETCDF=/usr/local
ENV HDF5=/usr/local
ENV JASPERINC=/WPS/grib2/include
ENV JASPERLIB=/WPS/grib2/lib

# Python venv and tools
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
RUN uv tool install era5_to_int==0.3.0

# Cache bust for WRF+WVT rebuild (change this value to force recompile)
ARG WVT_CACHE_BUST=12

# Download WRF source
ARG WRF_VERSION=4.7.1
RUN wget https://github.com/wrf-model/WRF/releases/download/v${WRF_VERSION}/v${WRF_VERSION}.tar.gz \
    && tar -zxf v${WRF_VERSION}.tar.gz \
    && mv WRFV${WRF_VERSION} /WRF \
    && rm v${WRF_VERSION}.tar.gz

# Overlay WRF-WVT modifications onto WRF source tree
COPY wvt/phys/ /WRF/phys/
COPY wvt/dyn_em/ /WRF/dyn_em/
COPY wvt/share/ /WRF/share/
COPY wvt/Registry/ /WRF/Registry/
COPY wvt/main/depend.common /WRF/main/depend.common
COPY wvt/run/README.tracers /WRF/run/
COPY wvt/run/namelist.input.tracers /WRF/run/

# Compile WRF - option 78 = INTEL (ifx/icx) oneAPI LLVM, dmpar
WORKDIR /WRF
RUN ( echo 78 ; echo 1 ) | ./configure \
    && ./compile -j "$(nproc)" em_real

# Compile WPS
ARG WPS_VERSION=4.6.0
RUN wget https://github.com/wrf-model/WPS/archive/v${WPS_VERSION}.tar.gz \
    && tar -zxf v${WPS_VERSION}.tar.gz \
    && mv WPS-${WPS_VERSION} /WPS \
    && rm v${WPS_VERSION}.tar.gz

WORKDIR /WPS

COPY patches/output_module.F /WPS/geogrid/src/

# Pre-build jasper with gcc — bundled jasper 1.900.29 has old-style C prototypes
# that icx treats as errors (-Wstrict-prototypes)
RUN cd /WPS/external/jasper-1.900.29 \
    && CC=gcc ./configure --prefix=/WPS/grib2 --disable-shared \
    && make -j$(nproc) && make install

# WPS option 9 = Intel oneAPI compilers, serial (--build-grib2-libs removes NO_GRIB2 entries, shifting numbering)
RUN echo 9 | ./configure --build-grib2-libs \
    && ./compile

RUN rm /WPS/namelist.wps && rm /WRF/run/namelist.input

WORKDIR /WPS/geogrid

COPY patches/GEOGRID.TBL.nz .

RUN ln -sf GEOGRID.TBL.nz GEOGRID.TBL

WORKDIR /WPS/metgrid

COPY patches/METGRID.TBL.nz .

RUN ln -sf METGRID.TBL.nz METGRID.TBL


###############################################################################
# Stage 2: Runtime — slim image with only executables and shared libraries
###############################################################################
FROM intel/oneapi-runtime:2025.3.1-0-devel-ubuntu24.04

# Intel Fortran and MPI runtime libraries (not included in base runtime image)
# plus runtime-only system packages (no compilers, no -dev headers)
RUN apt-get update && apt-get install -y \
    intel-oneapi-runtime-fortran \
    intel-oneapi-runtime-mpi \
    python3 python3-numpy nco libeccodes-tools \
    bash csh nano curl wget unzip zlib1g libpng16-16t64 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

# HDF5 + NetCDF shared libraries
COPY --from=builder /usr/local/ /usr/local/

# WRF executables (actual binaries live in main/, run/ has symlinks to ../main/)
COPY --from=builder /WRF/main/*.exe /WRF/main/
# WRF run directory (physics tables, data files, and symlinks to executables)
COPY --from=builder /WRF/run/ /WRF/run/
# Noah-MP parameter table (run/MPTABLE.TBL symlinks to ../phys/ which isn't copied)
COPY --from=builder /WRF/phys/noahmp/parameters/MPTABLE.TBL /WRF/phys/noahmp/parameters/MPTABLE.TBL

# WPS (whole directory — small, has internal symlinks)
COPY --from=builder /WPS/ /WPS/

# Python virtual environment
COPY --from=builder /opt/venv/ /opt/venv/

# era5_to_int installed via uv tool
COPY --from=builder /root/.local/ /root/.local/

# rclone binary
COPY --from=builder /usr/bin/rclone /usr/bin/rclone

# Register shared libraries
RUN ldconfig

# Environment variables
ENV NETCDF=/usr/local
ENV HDF5=/usr/local
ENV JASPERINC=/WPS/grib2/include
ENV JASPERLIB=/WPS/grib2/lib
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/root/.local/bin:/opt/venv/bin:/opt/intel/oneapi/redist/bin:$PATH"
# Intel MPI fabric for container environments (shm for single-node, avoids OFI hardware errors)
ENV I_MPI_FABRICS=shm

WORKDIR /WPS

CMD ["/bin/bash"]
