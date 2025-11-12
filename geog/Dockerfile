FROM busybox:1.37-glibc

## Get files
# Main high-res static files
RUN wget https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_high_res_mandatory.tar.gz \
        && tar -zxf geog_high_res_mandatory.tar.gz \
        && rm geog_high_res_mandatory.tar.gz

WORKDIR /WPS_GEOG

# Files for NOAH-MP
RUN wget https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_noahmp.tar.gz \
        && tar -zxf geog_noahmp.tar.gz \
        && rm geog_noahmp.tar.gz

# Higher res land cover
RUN wget https://www2.mmm.ucar.edu/wrf/src/wps_files/modis_landuse_20class_15s_with_lakes.tar.gz \
        && tar -zxf modis_landuse_20class_15s_with_lakes.tar.gz \
        && rm modis_landuse_20class_15s_with_lakes.tar.gz

RUN rm -fr modis_landuse_20class_30s_with_lakes \
        && rm ._modis_landuse_20class_30s_with_lakes

# Files for lake depth - sf_lake_physics=1
# RUN wget https://www2.mmm.ucar.edu/wrf/src/wps_files/lake_depth.tar.bz2 \
#         && tar -zxf lake_depth.tar.bz2 \
#         && rm lake_depth.tar.bz2

CMD [ "cp", "-r", "-u", "/WPS_GEOG/", "/data/" ]
