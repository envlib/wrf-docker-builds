#!/bin/bash

geog_path=$1
dest_path=$2

cd $geog_path

## Get files
# Main high-res static files
wget -N https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_high_res_mandatory.tar.gz -O geog_high_res_mandatory.tar.gz
tar -zxf geog_high_res_mandatory.tar.gz \
rm geog_high_res_mandatory.tar.gz

cd WPS_GEOG

# Files for NOAH-MP
wget -N https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_noahmp.tar.gz -O geog_noahmp.tar.gz
tar -zxf geog_noahmp.tar.gz
rm geog_noahmp.tar.gz

# Higher res land cover ~ 500m resolution in NZ
wget -N https://www2.mmm.ucar.edu/wrf/src/wps_files/modis_landuse_20class_15s_with_lakes.tar.gz -O modis_landuse_20class_15s_with_lakes.tar.gz
tar -zxf modis_landuse_20class_15s_with_lakes.tar.gz
rm modis_landuse_20class_15s_with_lakes.tar.gz

# Files for lake depth - sf_lake_physics=1
wget -N https://www2.mmm.ucar.edu/wrf/src/wps_files/lake_depth.tar.bz2 -O lake_depth.tar.bz2
tar -jxf lake_depth.tar.bz2
rm lake_depth.tar.bz2

cd ..

tar -I "zstd -3" -cvf $dest_path ./WPS_GEOG

rm -dr ./WPS_GEOG
