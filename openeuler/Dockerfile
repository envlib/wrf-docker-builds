ARG BASE=openeuler/openeuler:24.03-lts
FROM ${BASE}

ARG WRF_VERSION=4.6.1
ARG WPS_VERSION=4.6.0
ARG TARGETARCH
RUN yum install -y git gcc g++ glibc time tcsh wget gfortran libcurl-devel libpng-devel m4 nano cmake jasper jasper-devel zlib zlib-devel bash

# RUN yum -y update
# RUN yum -y install scl file gcc gcc-gfortran gcc-c++ glibc.i686 libgcc.i686 libpng-devel jasper \
#   jasper-devel hostname m4 make perl tar bash tcsh time wget which zlib zlib-devel \
#   openssh-clients openssh-server net-tools fontconfig libgfortran libXext libXrender \
#   ImageMagick sudo epel-release git

# # Newer version of GNU compiler, required for WRF 2003 and 2008 Fortran constructs

# RUN yum -y install centos-release-scl \
#  && yum -y install devtoolset-8 \
#  && yum -y install devtoolset-8-gcc devtoolset-8-gcc-gfortran devtoolset-8-gcc-c++ \
#  && scl enable devtoolset-8 bash \
#  && scl enable devtoolset-8 tcsh 

# RUN groupadd wrf -g 9999
# RUN useradd -u 9999 -g wrf -G wheel -M -d /wrf wrfuser
# RUN mkdir /wrf \
#  &&  chown -R wrfuser:wrf /wrf \
#  &&  chmod 6755 /wrf

WORKDIR /tmp/sources

# ENV
ENV HDF5=/usr/local
ENV NETCDF=/usr/local
ENV JASPERINC=/usr/include/jasper
ENV JASPERLIB=/usr/lib64/

# Get repos
# RUN git clone -b v${WRF_VERSION} --recursive https://github.com/wrf-model/WRF.git /WRF

# RUN git clone -b v${WPS_VERSION} --recursive https://github.com/wrf-model/WPS.git /WPS

# Compile MPI
RUN wget -O mpich-3.3.2.tar.gz http://www.mpich.org/static/downloads/3.3.2/mpich-3.3.2.tar.gz && \
    tar zxf mpich-3.3.2.tar.gz && \
    cd mpich-3.3.2 && \
    ./configure \
        --prefix=/usr/local \
        FFLAGS="-w -fallow-argument-mismatch -O2" && \
    make -j "$(nproc)" install

# Compile HDF5
RUN wget -O hdf5-1.12.0.tar.gz https://support.hdfgroup.org/ftp/HDF5/releases/hdf5-1.12/hdf5-1.12.0/src/hdf5-1.12.0.tar.gz && \
    tar zxf hdf5-1.12.0.tar.gz && \
    cd hdf5-1.12.0 && \
    ./configure \
        --prefix=$HDF5 \
        --enable-fortran \
        --enable-static=yes \
        --enable-parallel \
        --enable-shared \
        CFLAGS="-O3 -fPIC -Wno-incompatible-pointer-types-discards-qualifiers -Wno-non-literal-null-conversion" \
        FCFLAGS="-O3 -fPIC" LDFLAGS="-Wl,--build-id" \
        --enable-fortran \
        --enable-parallel \
        CC=mpicc FC=mpif90 CXX=mpicxx && \
    make -j "$(nproc)" install

# Compile netcdf4
RUN wget -O netcdf-c.tar.gz https://github.com/Unidata/netcdf-c/archive/refs/tags/v4.7.4.tar.gz && \
    mkdir -p netcdf-c && tar vxf netcdf-c.tar.gz -C netcdf-c --strip-components=1 && \
    cd netcdf-c && \
    ./configure \
        --prefix=$NETCDF \
        LDFLAGS="-L$HDF5/lib" CPPFLAGS="-I$HDF5/include" CC=mpicc --disable-dap FC=mpif90 CXX=mpicxx && \
    make -j "$(nproc)" install && \
    ldconfig
RUN wget -O netcdf-fortran.tar.gz https://github.com/Unidata/netcdf-fortran/archive/refs/tags/v4.5.3.tar.gz && \
    mkdir netcdf-fortran && tar -zvxf netcdf-fortran.tar.gz -C netcdf-fortran --strip-components=1 && \
    cd netcdf-fortran && \
    ./configure \
        --prefix=$NETCDF \
        CPPFLAGS="-I$HDF5/include -I$NETCDF/include" \
        LDFLAGS="-L$HDF5/lib -L$NETCDF/lib" \
        --enable-static=yes \
        --enable-shared \
        CFLAGS="-O3 -fPIC -Wno-incompatible-pointer-types-discards-qualifiers -Wno-non-literal-conversion" \
        FCFLAGS="-O3 -fPIC" LDFLAGS="-Wl,--build-id" \
        CC=mpicc FC=mpif90 CXX=mpicxx && \
    make -j "$(nproc)" install && \
    ldconfig && \
    rm -rf /tmp/sources

# Compile WRF and WPS
WORKDIR /WRF
RUN git clone -b v${WRF_VERSION} --recursive https://github.com/wrf-model/WRF.git /WRF && ./configure <<< $'34\r1\r' && ./compile -j "$(nproc)" em_real
# RUN git clone -b v${WRF_VERSION} --recursive https://github.com/wrf-model/WRF.git /WRF && \
#     if [ "$TARGETARCH" = "amd64" ]; then \
#         ./configure <<< $'34\r1\r' ; \
#     elif [ "$TARGETARCH" = "arm64" ]; then \
#         ./configure <<< $'4\r1\r'; \
#     fi; \
#     ./compile -j "$(nproc)" em_real

# # Compile WPS   
WORKDIR /WPS
RUN git clone --recursive https://github.com/mullenkamp/WPS.git /WPS  && ./configure <<< $'1\r' && ./compile
# RUN git clone -b v${WPS_VERSION} --recursive https://github.com/mullenkamp/WPS.git /WPS && \
#     if [ "$TARGETARCH" = "amd64" ]; then \
#         ./configure <<< $'3\r1\r' ; \
#     elif [ "$TARGETARCH" = "arm64" ]; then \
#         ./configure <<< $'4\r1\r'; \
#     fi; \
#     ./compile -j "$(nproc)" em_real

# git clone -b release-v4.7.0 --recursive https://github.com/wrf-model/WRF.git /WRF