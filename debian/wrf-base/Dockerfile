FROM debian:13-slim

RUN apt update && apt-get install -y build-essential csh gfortran m4 curl perl mpich libhdf5-mpich-dev libpng-dev netcdf-bin libnetcdff-dev ncl-ncarg wget cmake nano tcsh gcc g++ bash zlib1g zlib1g-dev git vim python3 python3-numpy python3-netcdf4 pipx nco libeccodes-tools unzip && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

RUN curl https://rclone.org/install.sh | bash

# ENV UV_SYSTEM_PYTHON=1 \
#     UV_LINK_MODE=copy \
#     UV_COMPILE_BYTECODE=1 \
#     UV_PYTHON_DOWNLOADS=never \
#     UV_PYTHON=python3.12
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

CMD ["/bin/bash"]