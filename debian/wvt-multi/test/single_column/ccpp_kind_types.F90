! Minimal stand-in for WRF's physics_mmm/ccpp_kind_types.F90, so cu_ntiedtke.F90 can be
! compiled outside the WRF build for the single-column identity harness.
 module ccpp_kind_types
 implicit none
 private
 public:: kind_phys
#ifdef SINGLE_PREC
 integer,parameter:: kind_phys = selected_real_kind(6)
#else
 integer,parameter:: kind_phys = selected_real_kind(13)
#endif
 end module ccpp_kind_types
