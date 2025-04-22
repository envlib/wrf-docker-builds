FROM debian:12-slim

ARG WRF_VERSION=4.6.1
ARG WPS_VERSION=4.6.0
ARG TYPE=ARW
ARG TARGETARCH

RUN apt update && apt-get install -y build-essential csh gfortran m4 curl perl mpich libhdf5-mpich-dev libpng-dev netcdf-bin libnetcdff-dev ncl-ncarg wget cmake nano tcsh gcc g++ bash zlib1g zlib1g-dev git
# RUN apt update && apt install -y git gcc g++ glibc time tcsh wget gfortran libcurl-devel libpng-devel m4 nano cmake jasper jasper-devel zlib zlib-devel bash
# RUN apt update && apt install -y csh gfortran m4 mpich libhdf5-mpich-dev libpng-dev libnetcdff-dev netcdf-bin ncl-ncarg build-essential wget m4 cmake nano tcsh gcc g++ bash zlib1g zlib1g-dev perl

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

SHELL ["/bin/bash", "-c"]

# WORKDIR /tmp/sources

# ENV

# Get repos
# RUN git clone -b v${WRF_VERSION} --recursive https://github.com/wrf-model/WRF.git /WRF

# RUN git clone -b v${WPS_VERSION} --recursive https://github.com/wrf-model/WPS.git /WPS

# Compile Jasper
# RUN wget https://www.ece.uvic.ca/~frodo/jasper/software/jasper-1.900.29.tar.gz && \
#     tar xvf jasper-1.900.29.tar.gz && \
#     cd jasper-1.900.29 && \
#     ./configure --prefix=/WPS/grib2/ && \
#     make && \
#     make install

# Compile MPI
# RUN wget -O mpich-3.3.2.tar.gz http://www.mpich.org/static/downloads/3.3.2/mpich-3.3.2.tar.gz && \
#     tar zxf mpich-3.3.2.tar.gz && \
#     cd mpich-3.3.2 && \
#     ./configure \
#         --prefix=/usr/local \
#         FFLAGS="-w -fallow-argument-mismatch -O2" && \
#     make -j "$(nproc)" install

# # Compile HDF5
# RUN wget -O hdf5-1.12.0.tar.gz https://support.hdfgroup.org/ftp/HDF5/releases/hdf5-1.12/hdf5-1.12.0/src/hdf5-1.12.0.tar.gz && \
#     tar zxf hdf5-1.12.0.tar.gz && \
#     cd hdf5-1.12.0 && \
#     ./configure \
#         --prefix=$HDF5 \
#         --enable-fortran \
#         --enable-static=yes \
#         --enable-parallel \
#         --enable-shared \
#         CFLAGS="-O3 -fPIC -Wno-incompatible-pointer-types-discards-qualifiers -Wno-non-literal-null-conversion" \
#         FCFLAGS="-O3 -fPIC" LDFLAGS="-Wl,--build-id" \
#         --enable-fortran \
#         --enable-parallel \
#         CC=mpicc FC=mpif90 CXX=mpicxx && \
#     make -j "$(nproc)" install

# # Compile netcdf4
# RUN wget -O netcdf-c.tar.gz https://github.com/Unidata/netcdf-c/archive/refs/tags/v4.7.4.tar.gz && \
#     mkdir -p netcdf-c && tar vxf netcdf-c.tar.gz -C netcdf-c --strip-components=1 && \
#     cd netcdf-c && \
#     ./configure \
#         --prefix=$NETCDF \
#         LDFLAGS="-L$HDF5/lib" CPPFLAGS="-I$HDF5/include" CC=mpicc --disable-dap FC=mpif90 CXX=mpicxx && \
#     make -j "$(nproc)" install && \
#     ldconfig
# RUN wget -O netcdf-fortran.tar.gz https://github.com/Unidata/netcdf-fortran/archive/refs/tags/v4.5.3.tar.gz && \
#     mkdir netcdf-fortran && tar -zvxf netcdf-fortran.tar.gz -C netcdf-fortran --strip-components=1 && \
#     cd netcdf-fortran && \
#     ./configure \
#         --prefix=$NETCDF \
#         CPPFLAGS="-I$HDF5/include -I$NETCDF/include" \
#         LDFLAGS="-L$HDF5/lib -L$NETCDF/lib" \
#         --enable-static=yes \
#         --enable-shared \
#         CFLAGS="-O3 -fPIC -Wno-incompatible-pointer-types-discards-qualifiers -Wno-non-literal-conversion" \
#         FCFLAGS="-O3 -fPIC" LDFLAGS="-Wl,--build-id" \
#         CC=mpicc FC=mpif90 CXX=mpicxx && \
#     make -j "$(nproc)" install && \
#     ldconfig && \
#     rm -rf /tmp/sources

# Compile WRF
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

# Compile WRF - must get the release file instead of the archive like in WPS due to NoahMP not contained in the archive
RUN wget https://github.com/wrf-model/WRF/releases/download/v${WRF_VERSION}/v${WRF_VERSION}.tar.gz \
        && tar -zxf v${WRF_VERSION}.tar.gz \
        && mv WRFV${WRF_VERSION} /WRF \
        && rm v${WRF_VERSION}.tar.gz

WORKDIR /WRF
RUN sed -i 's#$NETCDF/lib#$NETCDF/lib/x86_64-linux-gnu#g' configure && ( echo 34 ; echo 1 ) | ./configure
RUN sed -i 's#-L/usr/lib -lnetcdff -lnetcdf#-L/usr/lib/x86_64-linux-gnu -lnetcdff -lnetcdf#g' configure.wrf && gfortversion=$(gfortran -dumpversion | cut -d '.' -f 1) && ./compile -j "$(nproc)" em_real

# RUN git clone -b v${WRF_VERSION} --recursive https://github.com/wrf-model/WRF.git /WRF && ./clean
# RUN sed -i 's#$NETCDF/lib#$NETCDF/lib/x86_64-linux-gnu#g' configure && ( echo 34 ; echo 1 ) | ./configure
# RUN sed -i 's#-L/usr/lib -lnetcdff -lnetcdf#-L/usr/lib/x86_64-linux-gnu -lnetcdff -lnetcdf#g' configure.wrf && gfortversion=$(gfortran -dumpversion | cut -d '.' -f 1) && ./compile -j "$(nproc)" em_real
# RUN git clone -b v${WRF_VERSION} --recursive https://github.com/wrf-model/WRF.git /WRF && \
    # if [ "$TARGETARCH" = "amd64" ]; then \
    #     ./configure <<< $'34\r1\r' ; \
    # elif [ "$TARGETARCH" = "arm64" ]; then \
    #     ./configure <<< $'4\r1\r'; \
    # fi; \
#     ./compile -j "$(nproc)" em_real

# Compile WPS   
RUN wget https://github.com/wrf-model/WPS/archive/v${WPS_VERSION}.tar.gz \
	&& tar -zxf v${WPS_VERSION}.tar.gz \
    && mv WPS-${WPS_VERSION} /WPS \
	&& rm v${WPS_VERSION}.tar.gz

WORKDIR /WPS
RUN sed -i '163s/.*/    NETCDFF="-lnetcdff"/' configure && echo 1 | ./configure --build-grib2-libs && ./compile

# RUN git clone -b v${WPS_VERSION} --recursive https://github.com/wrf-model/WPS.git /WPS && ./clean
# RUN sed -i '163s/.*/    NETCDFF="-lnetcdff"/' configure && echo 1 | ./configure --build-grib2-libs && ./compile
# RUN git clone --recursive https://github.com/mullenkamp/WPS.git /WPS  && ./configure <<< $'1\r' && ./compile
# RUN git clone -b v${WPS_VERSION} --recursive https://github.com/mullenkamp/WPS.git /WPS && \
#     if [ "$TARGETARCH" = "amd64" ]; then \
#         ./configure <<< $'3\r1\r' ; \
#     elif [ "$TARGETARCH" = "arm64" ]; then \
#         ./configure <<< $'4\r1\r'; \
#     fi; \
#     ./compile -j "$(nproc)" em_real

CMD ["/bin/bash"]