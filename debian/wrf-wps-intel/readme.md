# Intel WRF/WPS Docker Image

WRF 4.7.1 + WPS 4.6.0 compiled with Intel oneAPI (ifx/icx) compilers in a two-stage Docker build. The runtime image is ~1.5-2GB compared to ~4.2GB for a single-stage build using the full `intel/oneapi-hpckit` image.

## Build

```bash
cd debian/wrf-wps-intel
docker compose build
```

## Test

```bash
chmod +x test.sh
./test.sh
# Or with custom paths:
./test.sh --image mullenkamp/wrf-wps-intel-ubuntu:1.0 \
          --geog-path ~/WPS_GEOG \
          --test-data ~/data/wrf/test_data
```

The test script validates file existence, shared library dependencies, tool availability, and runs the full pipeline (geogrid, metgrid, real, wrf) against test data.

## Two-Stage Build

### Stage 1: Builder

Uses `intel/oneapi-hpckit:2025.3.1-0-devel-ubuntu24.04` (~5GB). Compiles HDF5, NetCDF-C, NetCDF-Fortran, WRF, and WPS from source with Intel compilers. Everything here is discarded except the artifacts copied to Stage 2.

### Stage 2: Runtime

Uses `intel/oneapi-runtime:2025.3.1-0-devel-ubuntu24.04` (~1.3GB). Contains only:

- `/WRF/main/*.exe` — WRF executables (wrf.exe, real.exe, ndown.exe, tc.exe)
- `/WRF/run/` — physics tables, data files, and symlinks to executables
- `/WRF/phys/noahmp/parameters/MPTABLE.TBL` — Noah-MP parameter table
- `/WPS/` — WPS executables, grib2 libs, NZ-customized geogrid/metgrid tables
- `/usr/local/` — HDF5 + NetCDF shared libraries
- `/opt/venv/` — Python virtual environment
- `/root/.local/` — era5_to_int CLI tool
- `/usr/bin/rclone` — rclone binary

## Intel-Specific Gotchas

These are lessons learned from building and debugging this image. Many of these issues fail silently and are only caught at runtime.

### Intel MPI wrappers default to gfortran

Intel MPI's `mpif90` and `mpicc` wrapper scripts default to `gfortran` and `gcc` (hardcoded in the scripts). When compiling WPS with `dmpar` (which uses `mpif90`), the compile silently fails because `gfortran` isn't installed.

**Fix:** Set `I_MPI_F90=ifx` and `I_MPI_CC=icx` environment variables before any MPI-wrapped compilation.

### WPS configure option numbering changes with --build-grib2-libs

The `--build-grib2-libs` flag removes all `NO_GRIB2` entries from the configure menu, roughly halving the option numbers. Without this flag, Intel oneAPI dmpar is option 19. With it, option 19 becomes Cray compiler, and Intel oneAPI dmpar is option **10** and **9** with serial.

**Fix:** Always verify the option number by running `echo "" | ./configure --build-grib2-libs` and reading the menu output.

### Jasper 1.900.29 fails to compile with icx

The bundled JasPer library (1.900.29) in WPS has old-style C function declarations without `void` prototypes. Intel's `icx` compiler treats `-Wstrict-prototypes` as an error, causing the JasPer build to fail silently. Without `libjasper.a`, `ungrib.exe` cannot link.

**Fix:** Pre-build JasPer with `CC=gcc` before running `./configure --build-grib2-libs`:

```dockerfile
RUN cd /WPS/external/jasper-1.900.29 \
    && CC=gcc ./configure --prefix=/WPS/grib2 --disable-shared \
    && make -j$(nproc) && make install
```

### WRF executables live in main/, not run/

WRF's `./compile` puts the actual binaries in `/WRF/main/` and creates symlinks in `/WRF/run/` pointing to `../main/`. In a multi-stage build, you must copy both directories or the symlinks will be broken.

### MPTABLE.TBL symlinks outside of run/

`/WRF/run/MPTABLE.TBL` is a symlink to `../phys/noahmp/parameters/MPTABLE.TBL`. This is the only file in `/WRF/run/` that points outside the `run/` directory. If Noah-MP land surface physics is enabled (sf_surface_physics = 4), WRF will crash with `FATAL: STOP in Noah-MP read_mp_veg_parameters`.

**Fix:** Copy the target file explicitly in the runtime stage:

```dockerfile
COPY --from=builder /WRF/phys/noahmp/parameters/MPTABLE.TBL /WRF/phys/noahmp/parameters/MPTABLE.TBL
```

### Intel oneAPI runtime image tag includes "devel"

Intel uses `devel` in ALL their Docker tag names, including runtime images. The tag `intel/oneapi-runtime:2025.3.1-0-devel-ubuntu24.04` is the correct runtime image despite the confusing name. A tag without `devel` does not exist.

### Runtime image needs explicit Fortran and MPI packages

The `intel/oneapi-runtime` base image only includes core oneAPI runtime libs. It does **not** include Fortran or MPI runtimes. You must install them:

```dockerfile
RUN apt-get install -y intel-oneapi-runtime-fortran intel-oneapi-runtime-mpi
```

### mpirun is not on PATH in the runtime image

Intel MPI's `mpirun` is installed at `/opt/intel/oneapi/redist/bin/mpirun` but this directory is not on `PATH` by default. Add it explicitly:

```dockerfile
ENV PATH="/opt/intel/oneapi/redist/bin:$PATH"
```

## Intel MPI in Containers

### I_MPI_FABRICS=shm

Intel MPI defaults to OFI (OpenFabrics Interfaces) which tries to auto-detect InfiniBand, PSM2, or other high-performance network hardware. Inside containers, this hardware doesn't exist, causing `MPI_Init` to fail with:

```
Fatal error in internal_Init: Other MPI error
MPIDI_OFI_mpi_init_hook: Other MPI error
```

**Fix:** Set `I_MPI_FABRICS=shm` for single-node containers. This uses shared memory for inter-process communication, which is faster than TCP and doesn't require network hardware.

For multi-node MPI across containers (e.g., Kubernetes), use `I_MPI_FABRICS=ofi` with `FI_PROVIDER=tcp` to force the TCP socket provider.

Note: `FI_PROVIDER` alone is not sufficient — Intel MPI uses `I_MPI_FABRICS` to select the transport layer, and only consults `FI_PROVIDER` when `I_MPI_FABRICS=ofi`.

### ulimit -s unlimited

WRF compiled with Intel compilers uses large stack-allocated Fortran arrays. With the default Linux stack size limit (~8MB), multi-core MPI runs segfault during time integration:

```
forrtl: severe (174): SIGSEGV, segmentation fault occurred
```

Single-core runs may work because the per-process array sizes are smaller. The crash typically occurs right after initialization when the model begins time-stepping.

**Fix:** Set `ulimit -s unlimited` before running `mpirun`, or use `resource.setrlimit` in Python:

```python
import resource
resource.setrlimit(resource.RLIMIT_STACK, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
```

This has no downside and is standard practice for HPC workloads.

### WPS executables don't need mpirun

`geogrid.exe` and `metgrid.exe` are compiled with dmpar but can be run directly without `mpirun` (they call `MPI_Init` internally). However, `real.exe`, `ndown.exe`, and `wrf.exe` should always be run via `mpirun`.
