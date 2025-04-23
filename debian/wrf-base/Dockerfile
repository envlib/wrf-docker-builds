FROM debian:12-slim

RUN apt update && apt-get install -y build-essential csh gfortran m4 curl perl mpich libhdf5-mpich-dev libpng-dev netcdf-bin libnetcdff-dev ncl-ncarg wget cmake nano tcsh gcc g++ bash zlib1g zlib1g-dev git vim && apt-get clean && rm -rf /var/lib/apt/lists/*

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

SHELL ["/bin/bash", "-c"]

CMD ["/bin/bash"]