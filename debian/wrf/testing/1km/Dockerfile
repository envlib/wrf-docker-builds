FROM mullenkamp/wrf-debian:1.0

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