!WRF:MODEL_LAYER:PHYSICS
!
! 2D column-integrated diagnostics for the WVT branch.
!
! Computed at history-write time (gated by diag_flag in module_diagnostics_driver.F).
! Formulas match cfdb-ingest's offline computation exactly so the runtime values
! are bit-comparable to the existing downstream pipeline. See
! /home/mike/git/cfdb-repos/cfdb-ingest/cfdb_ingest/wrf.py:1005-1221.
!
! Outputs (all 2D, kg/m^2 for column water, kg/m/s for fluxes, Pa for SLP):
!   PWAT       = (1/g) * sum_k QVAPOR(k) * dp(k)
!   PWAT_TR    = (1/g) * sum_k qv_tr(k) * dp(k)
!   SLP        = PSFC * exp( g_slp * HGT / (Rd * T_mean) )    [no virtual-T correction]
!   VIMF_U     = (1/g) * sum_k QVAPOR(k) * u_earth(k) * dp(k)
!   VIMF_V     = (1/g) * sum_k QVAPOR(k) * v_earth(k) * dp(k)
!   VIMF_TR_U  = (1/g) * sum_k qv_tr(k)  * u_earth(k) * dp(k)
!   VIMF_TR_V  = (1/g) * sum_k qv_tr(k)  * v_earth(k) * dp(k)
!   IVT        = sqrt(VIMF_U^2 + VIMF_V^2)
!
! Pressure thickness dp(k) is computed as centered differences on (P+PB) at
! mass levels, with half-layers at column boundaries (matches cfdb-ingest's
! _compute_column_qvapor_dp).
!
! u_earth, v_earth = wind rotated from grid-relative to Earth-relative using
! local map rotation cos/sin (grid%cosa, grid%sina). U and V are unstaggered
! by averaging the two surrounding staggered values; tile-local loop bounds
! (its:ite, jts:jte) are safe to index u(i+1,k,j) / v(i,k,j+1) because the
! staggered arrays are allocated with halo bounds (ims:ime, jms:jme).
!
! Tracer fields (qv_tr) are doubly-guarded against the WRF 4D-array dummy-slot
! segfault: tracer_opt > 0 AND P_qv_tr >= PARAM_FIRST_SCALAR must both hold.
!
! Constants pinned to cfdb-ingest's choices:
!   g for SLP   = 9.81      (cfdb-ingest _read_sea_level_pressure)
!   g for PWAT  = 9.80665   (cfdb-ingest _read_precipitable_water et al)
!   Rd          = 287.05    (cfdb-ingest)
!   gamma       = 0.0065    (cfdb-ingest)

MODULE module_diag_wvt_columns

   IMPLICIT NONE

   PRIVATE
   PUBLIC :: compute_wvt_column_diagnostics

   REAL, PARAMETER :: G_SLP     = 9.81
   REAL, PARAMETER :: G_PWAT    = 9.80665
   REAL, PARAMETER :: RD_SLP    = 287.05
   REAL, PARAMETER :: GAMMA_SLP = 0.0065

CONTAINS

   SUBROUTINE compute_wvt_column_diagnostics ( grid, config_flags,            &
                                               moist, tracer,                 &
                                               ids, ide, jds, jde, kds, kde,  &
                                               ims, ime, jms, jme, kms, kme,  &
                                               its, ite, jts, jte, kts, kte   )

      USE module_domain, ONLY : domain
      USE module_configure, ONLY : grid_config_rec_type
      USE module_state_description, ONLY : num_moist, num_tracer,             &
                                           P_QV, P_qv_tr, PARAM_FIRST_SCALAR

      IMPLICIT NONE

      TYPE(domain), INTENT(INOUT) :: grid
      TYPE(grid_config_rec_type), INTENT(IN) :: config_flags

      REAL, DIMENSION(ims:ime, kms:kme, jms:jme, num_moist),  INTENT(IN) :: moist
      REAL, DIMENSION(ims:ime, kms:kme, jms:jme, num_tracer), INTENT(IN) :: tracer

      INTEGER, INTENT(IN) :: ids, ide, jds, jde, kds, kde
      INTEGER, INTENT(IN) :: ims, ime, jms, jme, kms, kme
      INTEGER, INTENT(IN) :: its, ite, jts, jte, kts, kte

      ! Local variables
      INTEGER :: i, j, k
      INTEGER :: i_end, j_end, k_end
      REAL    :: u_unstag, v_unstag, u_earth, v_earth
      REAL    :: dp_k, t_mean
      REAL    :: pwat_sum, pwat_tr_sum
      REAL    :: vimf_u_sum, vimf_v_sum
      REAL    :: vimf_tr_u_sum, vimf_tr_v_sum
      LOGICAL :: have_tracer

      ! Tracer 4D-array dummy-slot guard. When tracer_opt == 0 the array has a
      ! dummy 4th dimension of size 1, so P_qv_tr (if undefined / set to 1)
      ! would read the dummy slot or out-of-bounds memory. The combined check
      ! is the standard WRF idiom for accessing 4D tracer arrays.
      have_tracer = ( config_flags%tracer_opt > 0 .AND. &
                      P_qv_tr >= PARAM_FIRST_SCALAR )

      ! Mass-point loop bounds. We clamp i/j against ide-1/jde-1 because mass
      ! variables (T2, PSFC, P, PB, moist, tracer) are unstaggered and live
      ! at ide-1/jde-1; we also need (i+1, j+1) on the staggered U/V grids,
      ! which is always safe within these bounds.
      i_end = MIN(ite, ide-1)
      j_end = MIN(jte, jde-1)
      k_end = MIN(kte, kde-1)

      DO j = jts, j_end
         DO i = its, i_end

            ! ---- SLP (cfdb-ingest _read_sea_level_pressure) ----
            ! Dry hypsometric reduction; no virtual-T correction to match
            ! cfdb-ingest exactly. t_mean = T2 + gamma*HGT/2.
            t_mean = grid%t2(i,j) + GAMMA_SLP * grid%ht(i,j) / 2.0
            grid%slp(i,j) = grid%psfc(i,j) * &
                            EXP( G_SLP * grid%ht(i,j) / (RD_SLP * t_mean) )

            ! ---- Column integrals ----
            pwat_sum      = 0.0
            pwat_tr_sum   = 0.0
            vimf_u_sum    = 0.0
            vimf_v_sum    = 0.0
            vimf_tr_u_sum = 0.0
            vimf_tr_v_sum = 0.0

            DO k = kts, k_end

               ! Pressure thickness on mass levels (P+PB at half levels).
               ! Centered for interior; half-layer at column boundaries.
               ! Matches cfdb-ingest _compute_column_qvapor_dp exactly.
               IF ( k == kts ) THEN
                  dp_k = ABS( (grid%p(i,k,  j) + grid%pb(i,k,  j)) - &
                              (grid%p(i,k+1,j) + grid%pb(i,k+1,j)) )
               ELSE IF ( k == k_end ) THEN
                  dp_k = ABS( (grid%p(i,k-1,j) + grid%pb(i,k-1,j)) - &
                              (grid%p(i,k,  j) + grid%pb(i,k,  j)) )
               ELSE
                  dp_k = ABS( (grid%p(i,k-1,j) + grid%pb(i,k-1,j)) - &
                              (grid%p(i,k+1,j) + grid%pb(i,k+1,j)) ) / 2.0
               END IF

               ! Unstagger U, V to mass points. Halo allocation makes the
               ! (i+1, j+1) reads safe within the its:ite / jts:jte tile.
               u_unstag = 0.5 * ( grid%u_2(i,k,j) + grid%u_2(i+1,k,j  ) )
               v_unstag = 0.5 * ( grid%v_2(i,k,j) + grid%v_2(i,  k,j+1) )

               ! Rotate to Earth-relative using local map rotation.
               u_earth =   u_unstag * grid%cosa(i,j) + v_unstag * grid%sina(i,j)
               v_earth = - u_unstag * grid%sina(i,j) + v_unstag * grid%cosa(i,j)

               ! Regular-moisture sums
               pwat_sum   = pwat_sum   + moist(i,k,j,P_QV) * dp_k
               vimf_u_sum = vimf_u_sum + moist(i,k,j,P_QV) * u_earth * dp_k
               vimf_v_sum = vimf_v_sum + moist(i,k,j,P_QV) * v_earth * dp_k

               ! Tracer sums (only if tracer is active and defined)
               IF ( have_tracer ) THEN
                  pwat_tr_sum   = pwat_tr_sum   + tracer(i,k,j,P_qv_tr) * dp_k
                  vimf_tr_u_sum = vimf_tr_u_sum + tracer(i,k,j,P_qv_tr) * u_earth * dp_k
                  vimf_tr_v_sum = vimf_tr_v_sum + tracer(i,k,j,P_qv_tr) * v_earth * dp_k
               END IF

            END DO

            ! Normalize by g and write to grid.
            grid%pwat(i,j)   = pwat_sum   / G_PWAT
            grid%vimf_u(i,j) = vimf_u_sum / G_PWAT
            grid%vimf_v(i,j) = vimf_v_sum / G_PWAT

            IF ( have_tracer ) THEN
               grid%pwat_tr(i,j)   = pwat_tr_sum   / G_PWAT
               grid%vimf_tr_u(i,j) = vimf_tr_u_sum / G_PWAT
               grid%vimf_tr_v(i,j) = vimf_tr_v_sum / G_PWAT
            ELSE
               grid%pwat_tr(i,j)   = 0.0
               grid%vimf_tr_u(i,j) = 0.0
               grid%vimf_tr_v(i,j) = 0.0
            END IF

            ! IVT = magnitude of VIMF vector (cheap convenience scalar).
            grid%ivt(i,j) = SQRT( grid%vimf_u(i,j) * grid%vimf_u(i,j) + &
                                  grid%vimf_v(i,j) * grid%vimf_v(i,j) )

         END DO
      END DO

   END SUBROUTINE compute_wvt_column_diagnostics

END MODULE module_diag_wvt_columns
