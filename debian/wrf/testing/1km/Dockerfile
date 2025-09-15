FROM debian:12-slim

RUN apt update && apt-get install -y build-essential csh gfortran m4 curl perl mpich libhdf5-mpich-dev libpng-dev netcdf-bin libnetcdff-dev ncl-ncarg wget cmake nano tcsh gcc g++ bash zlib1g zlib1g-dev git vim && apt-get clean && rm -rf /var/lib/apt/lists/*

# RUN if [ "$TARGETARCH" = "amd64" ]; then \
#         export ARCH_NAME=x86_64; \
#     elif [ "$TARGETARCH" = "arm64" ]; then \
#         export ARCH_NAME=aarch64; \
#     fi; 

ARG ARCH

ENV CC=gcc
ENV CXX=g++
ENV FC=gfortran
ENV FCFLAGS=-m64
ENV F77=gfortran
ENV FFLAGS=-m64
ENV NETCDF=/usr
ENV HDF5=/usr/lib/$ARCH-linux-gnu/hdf5/serial
ENV LDFLAGS="-L/usr/lib/$ARCH-linux-gnu/hdf5/serial/ -L/usr/lib"
ENV CPPFLAGS="-I/usr/include/hdf5/serial/ -I/usr/include"
ENV LD_LIBRARY_PATH=/usr/lib
ENV JASPERINC=/WPS/grib2/include
ENV JASPERLIB=/WPS/grib2/lib

# SHELL ["/bin/bash", "-c"]

# ENV
ARG WRF_VERSION=4.6.1
# ARG TARGETARCH

# Compile WRF
RUN wget https://github.com/wrf-model/WRF/releases/download/v${WRF_VERSION}/v${WRF_VERSION}.tar.gz \
        && tar -zxf v${WRF_VERSION}.tar.gz \
        && mv WRFV${WRF_VERSION} /WRF \
        && rm v${WRF_VERSION}.tar.gz

WORKDIR /WRF
RUN sed -i 's#$NETCDF/lib#$NETCDF/lib/$ARCH-linux-gnu#g' configure
RUN if [ "$ARCH" = "x86_64" ]; then \
        ( echo 34 ; echo 1 ) | ./configure; \
    elif [ "$ARCH" = "aarch64" ]; then \
        ( echo 4 ; echo 1 ) | ./configure; \
    fi; 
RUN sed -i 's#-L/usr/lib -lnetcdff -lnetcdf#-L/usr/lib/$ARCH-linux-gnu -lnetcdff -lnetcdf#g' configure.wrf && gfortversion=$(gfortran -dumpversion | cut -d '.' -f 1) && ./compile -j "$(nproc)" em_real

WORKDIR /WRF/run

COPY ./wrfbdy_d01 .
COPY ./wrflowinp_d01 .
COPY ./wrflowinp_d02 .
COPY ./wrflowinp_d03 .
COPY ./wrflowinp_d04 .
COPY ./wrfinput_d01 .
COPY ./wrfinput_d02 .
COPY ./wrfinput_d03-* .
RUN cat wrfinput_d03-* > wrfinput_d03 && rm wrfinput_d03-*
COPY ./wrfinput_d04-* .
RUN cat wrfinput_d04-* > wrfinput_d04 && rm wrfinput_d04-*

COPY ./1km/namelist.input .

CMD ["/bin/bash"]