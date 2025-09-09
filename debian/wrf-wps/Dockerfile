FROM mullenkamp/wrf-base-debian:1.0

ARG WRF_VERSION=4.6.1
ARG WPS_VERSION=4.6.0

# Compile WRF - must get the release file instead of the archive like in WPS due to NoahMP not contained in the archive
RUN wget https://github.com/wrf-model/WRF/releases/download/v${WRF_VERSION}/v${WRF_VERSION}.tar.gz \
        && tar -zxf v${WRF_VERSION}.tar.gz \
        && mv WRFV${WRF_VERSION} /WRF \
        && rm v${WRF_VERSION}.tar.gz

WORKDIR /WRF
RUN sed -i 's#$NETCDF/lib#$NETCDF/lib/x86_64-linux-gnu#g' configure && ( echo 34 ; echo 1 ) | ./configure
RUN sed -i 's#-L/usr/lib -lnetcdff -lnetcdf#-L/usr/lib/x86_64-linux-gnu -lnetcdff -lnetcdf#g' configure.wrf && gfortversion=$(gfortran -dumpversion | cut -d '.' -f 1) && ./compile -j "$(nproc)" em_real

# Compile WPS   
RUN wget https://github.com/wrf-model/WPS/archive/v${WPS_VERSION}.tar.gz \
	&& tar -zxf v${WPS_VERSION}.tar.gz \
    && mv WPS-${WPS_VERSION} /WPS \
	&& rm v${WPS_VERSION}.tar.gz

WORKDIR /WPS
RUN sed -i '163s/.*/    NETCDFF="-lnetcdff"/' configure && echo 1 | ./configure --build-grib2-libs && ./compile

# Install python env for era5_to_int.py
# RUN apt-get update && apt-get install -y python3 python3-pip
COPY requirements.txt ./
# RUN pip install --no-cache-dir -r requirements.txt

RUN uv venv /opt/venv
# Use the virtual environment automatically
ENV VIRTUAL_ENV=/opt/venv \
    # UV_LINK_MODE=copy \
    # UV_COMPILE_BYTECODE=1 \
    # UV_PYTHON_DOWNLOADS=never \
    # UV_PYTHON=python3.11 \
# Place entry points in the environment at the front of the path
    PATH="/opt/venv/bin:$PATH"

RUN uv pip install -r requirements.txt
RUN git clone https://github.com/mullenkamp/era5_to_int
RUN ln -s /era5_to_int/era5_to_int.py era5_to_int.py

RUN rm /WPS/namelist.wps && rm /WRF/run/namelist.input

CMD ["/bin/bash"]