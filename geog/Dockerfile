FROM busybox:1.37-glibc

# Get files
RUN wget https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_high_res_mandatory.tar.gz \
        && tar -zxf geog_high_res_mandatory.tar.gz \
        # && mv WRFV${WRF_VERSION} /WRF \
        && rm geog_high_res_mandatory.tar.gz

CMD [ "cp", "-r", "-u", "/WPS_GEOG/", "/data/" ]
