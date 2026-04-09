 module module_mp_wsm6
 use ccpp_kind_types,only: kind_phys

 use mp_wsm6,only: mp_wsm6_run,refl10cm_wsm6
 use mp_wsm6_effectrad,only: mp_wsm6_effectRad_run


 implicit none
 private
 public:: wsm6


 contains


!=================================================================================================================
 subroutine wsm6(th,q,qc,qr,qi,qs,qg,den,pii,p,delz,                 &
                 delt,g,cpd,cpv,rd,rv,t0c,ep1,ep2,qmin,              &
                 xls,xlv0,xlf0,den0,denr,cliq,cice,psat,             &
                 rain,rainncv,snow,snowncv,graupel,graupelncv,sr,    &
                 refl_10cm,diagflag,do_radar_ref,                    &
                 has_reqc,has_reqi,has_reqs,                         &
                 re_qc_bg,re_qi_bg,re_qs_bg,                         &
                 re_qc_max,re_qi_max,re_qs_max,                      &
                 re_cloud,re_ice,re_snow,                            &
                 ids,ide,jds,jde,kds,kde,                            &
                 ims,ime,jms,jme,kms,kme,                            &
                 its,ite,jts,jte,kts,kte,                            &
                 errmsg,errflg                                       &
#if(WRF_CHEM == 1)
                 ,wetscav_on,evapprod,rainprod                       &
#endif
                 ,tr_qv_curr,tr_qc_curr,tr_qr_curr                  & ! mvt
                 ,tr_qi_curr,tr_qs_curr,tr_qg_curr                  & ! mvt
                 ,tr_rainnc,tr_snownc,tr_graupelnc                   & ! mvt
                 ,f_tr_qv,f_tr_qc,f_tr_qr                           & ! mvt
                 ,f_tr_qi,f_tr_qs,f_tr_qg                           & ! mvt
                )
!=================================================================================================================

!--- input arguments:
 logical,intent(in),optional:: diagflag

 integer,intent(in):: ids,ide,jds,jde,kds,kde, &
                      ims,ime,jms,jme,kms,kme, &
                      its,ite,jts,jte,kts,kte

 integer,intent(in):: has_reqc,has_reqi,has_reqs
 integer,intent(in),optional:: do_radar_ref

 real(kind=kind_phys),intent(in):: &
    delt,g,rd,rv,t0c,den0,cpd,cpv,ep1,ep2,qmin,xls,xlv0,xlf0, &
    cliq,cice,psat,denr

 real(kind=kind_phys),intent(in):: &
    re_qc_bg,re_qi_bg,re_qs_bg,re_qc_max,re_qi_max,re_qs_max

 real(kind=kind_phys),intent(in),dimension(ims:ime,kms:kme,jms:jme ):: &
    den, &
    pii, &
    p,   &
    delz

!inout arguments:
 real(kind=kind_phys),intent(inout),dimension(ims:ime,jms:jme):: &
    rain,rainncv,sr

 real(kind=kind_phys),intent(inout),dimension(ims:ime,jms:jme),optional:: &
    snow,snowncv

 real(kind=kind_phys),intent(inout),dimension(ims:ime,jms:jme),optional:: &
    graupel,graupelncv

 real(kind=kind_phys),intent(inout),dimension(ims:ime,kms:kme,jms:jme):: &
    th, &
    q,  &
    qc, &
    qi, &
    qr, &
    qs, &
    qg

 real(kind=kind_phys),intent(inout),dimension(ims:ime,kms:kme,jms:jme):: &
    re_cloud, &
    re_ice,   &
    re_snow

 real(kind=kind_phys),intent(inout),dimension(ims:ime,kms:kme,jms:jme),optional:: &
    refl_10cm

#if(WRF_CHEM == 1)
 logical,intent(in):: wetscav_on
 real(kind=kind_phys),intent(inout),dimension(ims:ime,kms:kme,jms:jme ):: &
    rainprod,evapprod
 real(kind=kind_phys),dimension(its:ite,kts:kte):: rainprod_hv,evapprod_hv
#endif

!--- WVT tracer optional arguments:                                          ! mvt
 real(kind=kind_phys),intent(inout),dimension(ims:ime,kms:kme,jms:jme),optional:: & ! mvt
    tr_qv_curr,tr_qc_curr,tr_qr_curr,tr_qi_curr,tr_qs_curr,tr_qg_curr      ! mvt

 real(kind=kind_phys),intent(inout),dimension(ims:ime,jms:jme),optional:: &  ! mvt
    tr_rainnc,tr_snownc,tr_graupelnc                                         ! mvt

 logical,intent(in),optional:: f_tr_qv,f_tr_qc,f_tr_qr,f_tr_qi,f_tr_qs,f_tr_qg ! mvt

!output arguments:
 character(len=*),intent(out):: errmsg
 integer,intent(out):: errflg

!local variables and arrays:
 logical:: do_microp_re
 integer:: i,j,k

 logical:: flag_tr_qv,flag_tr_qc,flag_tr_qr                                 ! mvt
 logical:: flag_tr_qi,flag_tr_qs,flag_tr_qg                                 ! mvt
 logical:: l_do_tracers                                                      ! mvt

 real(kind=kind_phys),dimension(kts:kte):: qv1d,t1d,p1d,qr1d,qs1d,qg1d,dBZ
 real(kind=kind_phys),dimension(kts:kte):: den1d,qc1d,qi1d,re_qc,re_qi,re_qs

 real(kind=kind_phys),dimension(its:ite):: rainncv_hv,rain_hv,sr_hv
 real(kind=kind_phys),dimension(its:ite):: snowncv_hv,snow_hv
 real(kind=kind_phys),dimension(its:ite):: graupelncv_hv,graupel_hv
 real(kind=kind_phys),dimension(its:ite,kts:kte):: t_hv,den_hv,p_hv,delz_hv
 real(kind=kind_phys),dimension(its:ite,kts:kte):: qv_hv,qc_hv,qi_hv,qr_hv,qs_hv,qg_hv
 real(kind=kind_phys),dimension(its:ite,kts:kte):: re_qc_hv,re_qi_hv,re_qs_hv

 real(kind=kind_phys),dimension(its:ite,kts:kte):: tr_qv_hv,tr_qc_hv,tr_qr_hv ! mvt
 real(kind=kind_phys),dimension(its:ite,kts:kte):: tr_qi_hv,tr_qs_hv,tr_qg_hv ! mvt
 real(kind=kind_phys),dimension(its:ite):: tr_rain_hv,tr_snow_hv,tr_graupel_hv ! mvt

!-----------------------------------------------------------------------------------------------------------------

!--- set WVT tracer flags:                                                   ! mvt
 flag_tr_qv = .false.                                                        ! mvt
 flag_tr_qc = .false.                                                        ! mvt
 flag_tr_qr = .false.                                                        ! mvt
 flag_tr_qi = .false.                                                        ! mvt
 flag_tr_qs = .false.                                                        ! mvt
 flag_tr_qg = .false.                                                        ! mvt
 if(present(f_tr_qv)) flag_tr_qv = f_tr_qv                                  ! mvt
 if(present(f_tr_qc)) flag_tr_qc = f_tr_qc                                  ! mvt
 if(present(f_tr_qr)) flag_tr_qr = f_tr_qr                                  ! mvt
 if(present(f_tr_qi)) flag_tr_qi = f_tr_qi                                   ! mvt
 if(present(f_tr_qs)) flag_tr_qs = f_tr_qs                                   ! mvt
 if(present(f_tr_qg)) flag_tr_qg = f_tr_qg                                  ! mvt
                                                                             ! mvt
 l_do_tracers = flag_tr_qv .and. flag_tr_qc .and. flag_tr_qr .and.        & ! mvt
                flag_tr_qi .and. flag_tr_qs .and. flag_tr_qg                 ! mvt

 do j = jts,jte

    do i = its,ite
       !input arguments:
       do k = kts,kte
          den_hv(i,k)  = den(i,k,j)
          p_hv(i,k)    = p(i,k,j)
          delz_hv(i,k) = delz(i,k,j)
       enddo

       !inout arguments:
       rain_hv(i) = rain(i,j)

       do k = kts,kte
          t_hv(i,k)  = th(i,k,j)*pii(i,k,j)
          qv_hv(i,k) = q(i,k,j)
          qc_hv(i,k) = qc(i,k,j)
          qi_hv(i,k) = qi(i,k,j)
          qr_hv(i,k) = qr(i,k,j)
          qs_hv(i,k) = qs(i,k,j)
          qg_hv(i,k) = qg(i,k,j)
       enddo
    enddo

    if(present(snow) .and. present(snowncv)) then
       do i = its,ite
          snow_hv(i) = snow(i,j)
       enddo
    endif
    if(present(graupel) .and. present(graupelncv)) then
       do i = its,ite
          graupel_hv(i) = graupel(i,j)
       enddo
    endif

!--- copy WVT tracer arrays to 2D slices:                                   ! mvt
    if(l_do_tracers) then                                                    ! mvt
       do i = its,ite                                                        ! mvt
          tr_rain_hv(i)    = tr_rainnc(i,j)                                 ! mvt
          tr_snow_hv(i)    = tr_snownc(i,j)                                 ! mvt
          tr_graupel_hv(i) = tr_graupelnc(i,j)                              ! mvt
          do k = kts,kte                                                     ! mvt
             tr_qv_hv(i,k) = tr_qv_curr(i,k,j)                             ! mvt
             tr_qc_hv(i,k) = tr_qc_curr(i,k,j)                             ! mvt
             tr_qr_hv(i,k) = tr_qr_curr(i,k,j)                             ! mvt
             tr_qi_hv(i,k) = tr_qi_curr(i,k,j)                             ! mvt
             tr_qs_hv(i,k) = tr_qs_curr(i,k,j)                             ! mvt
             tr_qg_hv(i,k) = tr_qg_curr(i,k,j)                             ! mvt
          enddo                                                              ! mvt
       enddo                                                                 ! mvt
    endif                                                                    ! mvt

!--- call to cloud microphysics scheme:
    if(l_do_tracers) then                                                    ! mvt
    call mp_wsm6_run(t=t_hv,q=qv_hv,qc=qc_hv,qi=qi_hv,qr=qr_hv,qs=qs_hv,qg=qg_hv, &
                 den=den_hv,p=p_hv,delz=delz_hv,delt=delt,g=g,cpd=cpd,cpv=cpv,    &
                 rd=rd,rv=rv,t0c=t0c,ep1=ep1,ep2=ep2,qmin=qmin,xls=xls,xlv0=xlv0, &
                 xlf0=xlf0,den0=den0,denr=denr,cliq=cliq,cice=cice,psat=psat,     &
                 rain=rain_hv,rainncv=rainncv_hv,sr=sr_hv,snow=snow_hv,           &
                 snowncv=snowncv_hv,graupel=graupel_hv,graupelncv=graupelncv_hv,  &
                 its=its,ite=ite,kts=kts,kte=kte,errmsg=errmsg,errflg=errflg      &
#if(WRF_CHEM == 1)
                 ,rainprod2d=rainprod_hv,evapprod2d=evapprod_hv                   &
#endif
                 ,tr_q=tr_qv_hv,tr_qc=tr_qc_hv,tr_qi=tr_qi_hv                   & ! mvt
                 ,tr_qr=tr_qr_hv,tr_qs=tr_qs_hv,tr_qg=tr_qg_hv                  & ! mvt
                 ,tr_rain=tr_rain_hv,tr_snow=tr_snow_hv,tr_graupel=tr_graupel_hv  & ! mvt
                 ,do_tracers=l_do_tracers                                          & ! mvt
                    )
    else                                                                     ! mvt
    call mp_wsm6_run(t=t_hv,q=qv_hv,qc=qc_hv,qi=qi_hv,qr=qr_hv,qs=qs_hv,qg=qg_hv, &
                 den=den_hv,p=p_hv,delz=delz_hv,delt=delt,g=g,cpd=cpd,cpv=cpv,    &
                 rd=rd,rv=rv,t0c=t0c,ep1=ep1,ep2=ep2,qmin=qmin,xls=xls,xlv0=xlv0, &
                 xlf0=xlf0,den0=den0,denr=denr,cliq=cliq,cice=cice,psat=psat,     &
                 rain=rain_hv,rainncv=rainncv_hv,sr=sr_hv,snow=snow_hv,           &
                 snowncv=snowncv_hv,graupel=graupel_hv,graupelncv=graupelncv_hv,  &
                 its=its,ite=ite,kts=kts,kte=kte,errmsg=errmsg,errflg=errflg      &
#if(WRF_CHEM == 1)
                 ,rainprod2d=rainprod_hv,evapprod2d=evapprod_hv                   &
#endif
                    )
    endif                                                                    ! mvt

    do i = its,ite
       !inout arguments:
       rain(i,j)    = rain_hv(i)
       rainncv(i,j) = rainncv_hv(i)
       sr(i,j)      = sr_hv(i)

       do k = kts,kte
          th(i,k,j) = t_hv(i,k)/pii(i,k,j)
          q(i,k,j)  = qv_hv(i,k)
          qc(i,k,j) = qc_hv(i,k)
          qi(i,k,j) = qi_hv(i,k)
          qr(i,k,j) = qr_hv(i,k)
          qs(i,k,j) = qs_hv(i,k)
          qg(i,k,j) = qg_hv(i,k)
       enddo
    enddo

    if(present(snow) .and. present(snowncv)) then
       do i = its,ite
          snow(i,j)    = snow_hv(i)
          snowncv(i,j) = snowncv_hv(i)
       enddo
    endif
    if(present(graupel) .and. present(graupelncv)) then
       do i = its,ite
          graupel(i,j)    = graupel_hv(i)
          graupelncv(i,j) = graupelncv_hv(i)
       enddo
    endif

!--- copy WVT tracer 2D slices back to 3D arrays:                           ! mvt
    if(l_do_tracers) then                                                    ! mvt
       do i = its,ite                                                        ! mvt
          tr_rainnc(i,j)    = tr_rain_hv(i)                                 ! mvt
          tr_snownc(i,j)    = tr_snow_hv(i)                                 ! mvt
          tr_graupelnc(i,j) = tr_graupel_hv(i)                              ! mvt
          do k = kts,kte                                                     ! mvt
             tr_qv_curr(i,k,j) = tr_qv_hv(i,k)                             ! mvt
             tr_qc_curr(i,k,j) = tr_qc_hv(i,k)                             ! mvt
             tr_qr_curr(i,k,j) = tr_qr_hv(i,k)                             ! mvt
             tr_qi_curr(i,k,j) = tr_qi_hv(i,k)                             ! mvt
             tr_qs_curr(i,k,j) = tr_qs_hv(i,k)                             ! mvt
             tr_qg_curr(i,k,j) = tr_qg_hv(i,k)                             ! mvt
          enddo                                                              ! mvt
       enddo                                                                 ! mvt
    endif                                                                    ! mvt

#if(WRF_CHEM == 1)
    if(wetscav_on) then
       do k = kts,kte
          do i = its, ite
             rainprod(i,k,j) = rainprod_hv(i,k)
             evapprod(i,k,j) = evapprod_hv(i,k)
          enddo
        enddo
     else
       do k = kts,kte
          do i = its, ite
             rainprod(i,k,j) = 0.
             evapprod(i,k,j) = 0.
          enddo
        enddo
     endif
#endif

!--- call to computation of effective radii for cloud water, cloud ice, and snow:
     do_microp_re = .false.
     if(has_reqc == 1 .and. has_reqi == 1 .and. has_reqs == 1) do_microp_re = .true.

     do k = kts,kte
        do i = its,ite
           t_hv(i,k) = th(i,k,j)*pii(i,k,j)
           re_qc_hv(i,k) = re_cloud(i,k,j)
           re_qi_hv(i,k) = re_ice(i,k,j)
           re_qs_hv(i,k) = re_snow(i,k,j)
        enddo
     enddo

     call  mp_wsm6_effectRad_run(do_microp_re,t_hv,qc_hv,qi_hv,qs_hv,den_hv,qmin,t0c, &
                   re_qc_bg,re_qi_bg,re_qs_bg,re_qc_max,re_qi_max,re_qs_max,re_qc_hv, &
                   re_qi_hv,re_qs_hv,its,ite,kts,kte,errmsg,errflg)

     do k = kts,kte
        do i = its,ite
           re_cloud(i,k,j) = re_qc_hv(i,k)
           re_ice(i,k,j)   = re_qi_hv(i,k)
           re_snow(i,k,j)  = re_qs_hv(i,k)
        enddo
     enddo

     if (diagflag .and. do_radar_ref == 1) then
        do i=its,ite
           do k=kts,kte
              t1d(k)=th(i,k,j)*pii(i,k,j)
              p1d(k)=p(i,k,j)
              qv1d(k)=q(i,k,j)
              qr1d(k)=qr(i,k,j)
              qs1d(k)=qs(i,k,j)
              qg1d(k)=qg(i,k,j)
           enddo
           call refl10cm_wsm6 (qv1d,qr1d,qs1d,qg1d,t1d,p1d,dBZ,kts,kte)
           do k = kts, kte
              refl_10cm(i,k,j) = MAX(-35., dBZ(k))
           enddo
        enddo
     endif

 enddo

 end subroutine wsm6

!=================================================================================================================
 end module module_mp_wsm6
!=================================================================================================================
