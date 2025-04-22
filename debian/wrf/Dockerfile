FROM mullenkamp/wrf-base-debian:1.0

ARG WRF_VERSION=4.6.1
ARG TARGETARCH

# Compile WRF
RUN wget https://github.com/wrf-model/WRF/releases/download/v${WRF_VERSION}/v${WRF_VERSION}.tar.gz \
        && tar -zxf v${WRF_VERSION}.tar.gz \
        && mv WRFV${WRF_VERSION} /WRF \
        && rm v${WRF_VERSION}.tar.gz

WORKDIR /WRF
RUN sed -i 's#$NETCDF/lib#$NETCDF/lib/x86_64-linux-gnu#g' configure
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        ( echo 34 ; echo 1 ) | ./configure; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        ( echo 4 ; echo 1 ) | ./configure; \
    fi; 
RUN sed -i 's#-L/usr/lib -lnetcdff -lnetcdf#-L/usr/lib/x86_64-linux-gnu -lnetcdff -lnetcdf#g' configure.wrf && gfortversion=$(gfortran -dumpversion | cut -d '.' -f 1) && ./compile -j "$(nproc)" em_real

CMD ["/bin/bash"]