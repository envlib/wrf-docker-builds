! Single-column identity harness for the New Tiedtke water-vapour-tracer mirrors.
!
! THE TEST: set every tag equal to the vapour. The tags are then, by construction, a partition
! of the vapour with a single member, so a correct implementation must return tr_qv == pqv at
! every level and tr_pratec == zprecc/dt, with the one-sided caps never firing.
!
! Any missing or wrong mirror shows up as a per-level residual, which is what makes this a
! DISCOVERY tool and not only a gate: the level where the residual appears names the routine.
!
! Column orientation follows the scheme (and cu_ntiedtke_pre_run): index 1 = model top,
! index km = surface.
program sc_driver
 use ccpp_kind_types,only: kind_phys
 use cu_ntiedtke,only: cu_ntiedtke_run,cu_ntiedtke_init
#ifdef WVT_CLAMP_DIAG
 use cu_ntiedtke_common,only: wvt_clamp_count,wvt_clamp_amt,wvt_flux_err,wvt_src_err,wvt_midlev_hits,wvt_plude_hits,wvt_v0
#endif
 implicit none

 integer,parameter:: km  = 50
 integer,parameter:: km1 = km+1
 integer,parameter:: nc  = 48            ! 25-36 mid-level convection; 37-48 dry-mid (strong downdraft)
 real(kind=kind_phys),parameter:: dt = 300.0
 real(kind=kind_phys),parameter:: p_sfc = 100000.0, p_top = 5000.0
 real(kind=kind_phys),parameter:: hscale = 8000.0
 real(kind=kind_phys),parameter:: grav = 9.81, cp = 1004.6, rd = 287.04, rv = 461.6
 real(kind=kind_phys),parameter:: xlv = 2.5e6, xls = 2.834e6, xlf = 0.334e6

 real(kind=kind_phys),dimension(nc,km):: pu,pv,pt,pqv,pqc,pqi,pqvf,ptf,poz,pomg,pap
 real(kind=kind_phys),dimension(nc,km):: tr_qv,tr_qc,tr_qi,cap_cre,cap_des
 real(kind=kind_phys),dimension(nc,km):: qv0,pt0,pqc0,pqi0,pu0,pv0
 real(kind=kind_phys),dimension(nc,km1):: pzz,paph
 real(kind=kind_phys),dimension(nc):: evap,hfx,zprecc,dx,tr_pratec
 integer,dimension(nc):: lndj

 real(kind=kind_phys):: tsfc,rh_bl,rh_mid,zz,tt,es,qs,rh,dpz
 real(kind=kind_phys):: dmax,dsum,cre,des,pmax,dlev
 real(kind=kind_phys):: worst_lev, worst_cre, negm, tol
 logical:: ok
 character(len=64):: argbuf, argbuf2
 logical:: v0mode
 integer:: i,k,n,nconv,errflg,kworst,nneg,ic_w,kc_w
 logical:: midlev, drymid, partmode
 integer:: ipass
 real(kind=kind_phys):: psplit, ztmp
 real(kind=kind_phys),dimension(3):: pcre, pdes, prain, psum
 real(kind=kind_phys),dimension(3,nc,km):: ptag
 character(len=256):: errmsg

 call cu_ntiedtke_init(cp,rd,rv,xlv,xls,xlf,grav,errmsg,errflg)

 do i = 1,nc
    midlev = (i > 24 .and. i <= 36)
    drymid = (i > 36)
    if (drymid) then
       ! Moist boundary layer under a very dry mid-troposphere: maximises downdraft strength
       ! (rain evaporating into dry air) so that zmfs<1 and the zmfuub correction can fire,
       ! and makes the near-cloud-top negative-humidity branch (the plude repair) reachable.
       tsfc   = 301.0 + 1.0*mod(i-1,6)
       rh_bl  = 0.92
       rh_mid = 0.10 + 0.02*mod(i-1,3)
    else if (midlev) then
       ! Dry, stable boundary layer so surface-based convection does NOT trigger, over a moist
       ! mid-troposphere - the cubasmcn path (lmfmid: RH>0.80 between 500 m and 10 km).
       tsfc   = 292.0 + 1.0*mod(i-1,6)
       rh_bl  = 0.30
       rh_mid = 0.90 + 0.02*mod(i-1,3)
    else
       tsfc   = 299.0 + 1.0*mod(i-1,8)              ! 299..306 K, tropical maritime
       rh_bl  = 0.88  + 0.02*((i-1)/8)              ! 0.88 / 0.90 / 0.92
       rh_mid = 0.60  + 0.05*((i-1)/8)
    end if
    lndj(i) = mod(i,2)                              ! alternate land / ocean
    dx(i)   = 12000.0
    evap(i) = 2.5e-4
    hfx(i)  = 120.0
    zprecc(i)   = 0.0
    tr_pratec(i)= 0.0

    ! half levels: index 1 = top, km1 = surface
    do k = 1,km1
       paph(i,k) = p_top + (p_sfc-p_top)*real(k-1,kind_phys)/real(km,kind_phys)
       pzz(i,k)  = hscale*log(p_sfc/paph(i,k))
    end do
    do k = 1,km
       pap(i,k) = 0.5*(paph(i,k)+paph(i,k+1))
       poz(i,k) = 0.5*(pzz(i,k)+pzz(i,k+1))
       zz = poz(i,k)
       if (midlev) then
          tt = tsfc - 0.0055*zz       ! stable: suppresses the surface-based plume
       else if (drymid) then
          tt = tsfc - 0.0085*zz       ! strongly unstable
       else
          tt = tsfc - 0.0078*zz       ! conditionally unstable
       end if
       if (tt < 205.0) tt = 205.0
       pt(i,k) = tt
       es = 610.78*exp(17.269*(tt-273.16)/(tt-35.86))
       qs = 0.622*es/max(pap(i,k)-0.378*es, 1.0)
       if (drymid) then
          if (zz < 1200.0) then
             rh = rh_bl
          else
             rh = rh_mid
          end if
       else if (midlev) then
          if (zz < 1000.0) then
             rh = rh_bl
          else if (zz < 7000.0) then
             rh = rh_mid
          else
             rh = 0.20
          end if
       else if (zz < 1500.0) then
          rh = rh_bl
       else if (zz < 9000.0) then
          rh = rh_bl + (rh_mid-rh_bl)*(zz-1500.0)/7500.0
       else
          rh = 0.20
       end if
       pqv(i,k) = max(1.0e-8, rh*qs)
       pqc(i,k) = 0.0
       pqi(i,k) = 0.0
       pu(i,k)  = 5.0
       pv(i,k)  = 0.0
       pqvf(i,k)= 0.0
       ptf(i,k) = 0.0
       if (zz < 2000.0) pqvf(i,k) = 1.0e-8   ! large-scale moistening
       ! gentle large-scale ascent below 500 hPa to help the trigger
       if (pap(i,k) > 50000.0) then
          pomg(i,k) = -0.30
       else
          pomg(i,k) = 0.0
       end if
    end do
 end do

 qv0 = pqv
 pt0 = pt; pqc0 = pqc; pqi0 = pqi; pu0 = pu; pv0 = pv
 v0mode = .false.
 partmode = .false.
 psplit = 92000.0
 if (command_argument_count() >= 2) then
    call get_command_argument(2, argbuf2)
    if (trim(argbuf2) == 'v0') v0mode = .true.
    if (trim(argbuf2) == 'part') partmode = .true.
 end if
 ! THE IDENTITY: every tag equals the vapour
 tr_qv = pqv
 if (v0mode) then
    ! V0 COMPOSITION MODE: tag only the lowest part of the column, so the plume entrains
    ! UNTAGGED air as it rises. The tagged fraction of the plume then has a closed form
    ! that depends on base quantities alone - see the pytest that checks it.
    do i = 1,nc
       do k = 1,km
          if (pap(i,k) < 92000.0) tr_qv(i,k) = 0.0
       end do
    end do
 end if
 tr_qc = pqc
 tr_qi = pqi
 cap_cre = 0.0
 cap_des = 0.0

 if (partmode) then
    ! PARTITION GATE. Run the scheme three times on identical soundings: a lower member, its
    ! complement, and the full tag. The member SUM is a conservation check (and is exact), so
    ! the informative quantity is the CAP ACTIVITY per member - tag mass the one-sided caps
    ! create on one member and destroy on the other. That is composition being silently
    ! redistributed between regions, and it is invisible to both V-id and V0 by construction.
    do ipass = 1,3
       pt = pt0; pqc = pqc0; pqi = pqi0; pu = pu0; pv = pv0; pqv = qv0
       zprecc = 0.0; tr_pratec = 0.0; cap_cre = 0.0; cap_des = 0.0
       do i = 1,nc
          do k = 1,km
             select case (ipass)
             case (1); tr_qv(i,k) = merge(pqv(i,k), 0.0_kind_phys, pap(i,k) >= psplit)
             case (2); tr_qv(i,k) = merge(0.0_kind_phys, pqv(i,k), pap(i,k) >= psplit)
             case (3); tr_qv(i,k) = pqv(i,k)
             end select
          end do
       end do
       tr_qc = 0.0; tr_qi = 0.0
       call cu_ntiedtke_run(pu,pv,pt,pqv,pqc,pqi,pqvf,ptf,poz,pzz,pomg,       &
                            pap,paph,evap,hfx,zprecc,lndj,nc,km,km1,dt,dx,    &
                            errmsg,errflg, tr_qv=tr_qv,tr_qc=tr_qc,tr_qi=tr_qi,&
                            tr_pratec=tr_pratec,do_tracers=.true.,             &
                            tr_cap_cre=cap_cre,tr_cap_des=cap_des)
       pcre(ipass) = 0.0; pdes(ipass) = 0.0; psum(ipass) = 0.0
       do i = 1,nc
          do k = 1,km
             dpz = (paph(i,k+1)-paph(i,k))/grav
             pcre(ipass) = pcre(ipass) + cap_cre(i,k)*dpz
             pdes(ipass) = pdes(ipass) + cap_des(i,k)*dpz
             ptag(ipass,i,k) = tr_qv(i,k)
          end do
       end do
       prain(ipass) = sum(zprecc)
    end do
    write(*,'(a,f7.1,a)') 'PARTITION GATE  (split at ', psplit*0.01, ' hPa)'
    write(*,'(a)') '  member          cap CREATED    cap DESTROYED     tagged rain (mm)'
    do ipass = 1,3
       write(*,'(a,i0,a,3es17.4)') '   pass ', ipass, '        ', &
            pcre(ipass), pdes(ipass), prain(ipass)
    end do
    ztmp = 0.0
    do i = 1,nc
       do k = 1,km
          ztmp = max(ztmp, abs(ptag(1,i,k)+ptag(2,i,k)-ptag(3,i,k)))
       end do
    end do
    write(*,'(a,es11.3,a)') '  max |lower+upper-full| = ', ztmp, ' kg/kg  (conservation)'
    write(*,'(a,es11.3,a)') '  cap activity on members = ', &
         pcre(1)+pdes(1)+pcre(2)+pdes(2), ' kg/m2  (COMPOSITION redistributed)'
    stop
 end if
 call cu_ntiedtke_run(pu,pv,pt,pqv,pqc,pqi,pqvf,ptf,poz,pzz,pomg,          &
                      pap,paph,evap,hfx,zprecc,lndj,nc,km,km1,dt,dx,       &
                      errmsg,errflg,                                        &
                      tr_qv=tr_qv,tr_qc=tr_qc,tr_qi=tr_qi,                  &
                      tr_pratec=tr_pratec,do_tracers=.true.,                &
                      tr_cap_cre=cap_cre,tr_cap_des=cap_des)

 nconv = 0
 dmax  = 0.0
 dsum  = 0.0
 cre   = 0.0
 des   = 0.0
 pmax  = 0.0
 kworst = -1
 worst_lev = 0.0
 nneg = 0
 negm = 0.0
 worst_cre = 0.0
 ic_w = 0
 kc_w = 0
 do i = 1,nc
    if (zprecc(i) > 0.0) then
       nconv = nconv + 1
       pmax = max(pmax, abs(tr_pratec(i)*dt - zprecc(i))/max(zprecc(i),1.0e-12))
    end if
    do k = 1,km
       dpz = (paph(i,k+1)-paph(i,k))/grav
       if (pqv(i,k) < 0.0) then
          ! The base scheme itself leaves a few cells with negative humidity (pre-existing WRF
          ! behaviour, not a tagging defect). The tag correctly refuses to follow it negative,
          ! so every metric would count that one event three times. Excluded by a property of
          ! the BASE field, never by the tagged quantity being tested.
          nneg = nneg + 1
          negm = negm + abs(pqv(i,k))*dpz
          cycle
       end if
       ! absolute, in kg/kg: relative measures are meaningless where the scheme
       ! leaves pqv negative or at the 1e-8 floor aloft
       dlev = abs(tr_qv(i,k)-pqv(i,k))
       if (dlev > dmax) then
          dmax = dlev
          kworst = k
          worst_lev = pap(i,k)*0.01
       end if
       dsum = dsum + abs(tr_qv(i,k)-pqv(i,k))*dpz
       cre  = cre + cap_cre(i,k)*dpz
       if (cap_cre(i,k)*dpz > worst_cre) then
          worst_cre = cap_cre(i,k)*dpz; ic_w = i; kc_w = k
       end if
       des  = des + cap_des(i,k)*dpz
    end do
 end do

 write(*,'(a,i0,a,i0,a,i0)') 'columns=', nc, '  convecting=', nconv, &
        '  levels with pqv<0 (pre-existing, EXCLUDED): ', nneg
 write(*,'(a,es12.4,a,i0,a,f7.1,a)') 'V-id  max |tr_qv-pqv|      kg/kg  : ', dmax, &
        '   at k=', kworst, ' (', worst_lev, ' hPa)'
 write(*,'(a,es12.4)')  'V-id  column-integrated |tr_qv-pqv| kg/m2: ', dsum
 write(*,'(a,es12.4)')  'cap   mass CREATED  by max(0,.)   kg/m2  : ', cre
 write(*,'(a,es12.4)')  'cap   mass DESTROYED by min(.,pqv) kg/m2 : ', des
 write(*,'(a,es12.4)')  'V-id  max rel |tr_pratec*dt - zprecc|    : ', pmax
 write(*,'(a)') ''
 write(*,'(a,es12.4)')  'TOTAL TAG INCONSISTENCY (deficit+created+destroyed) kg/m2: ', dsum+cre+des
 write(*,'(a)') '  ^ the only honest headline: the cap HIDES deficit by clipping, so a mirror'
 write(*,'(a)') '    that reduces cap_des while raising the deficit has moved mass, not fixed it.'
 write(*,'(a,es11.3,a)') ' excluded negative-base-humidity mass: ', negm, ' kg/m2'

!--- pass/fail, so this is a TEST and not a report. Thresholds are set from the measured
!--- baseline with margin, and differ by precision: double sits at ~2e-13, single at ~1e-4.
!--- The weakest mutant in the V6 set is 9.9e-4, so single precision has only ~8x margin -
!--- that is thin, and is why the double-precision run is the primary gate.
#ifdef SINGLE_PREC
 tol = 5.0e-4
#else
 tol = 1.0e-9
#endif
 if (command_argument_count() >= 1) then
    call get_command_argument(1, argbuf)
    if (len_trim(argbuf) > 0) read(argbuf,*) tol
 end if
 ok = .true.
 if (nconv == 0) then
    write(*,'(a)') 'FAIL: no column convected - the test is vacuous'
    ok = .false.
 end if
 if (v0mode) then
    ! In V0 mode the tags deliberately do NOT span the vapour, so the identity metric is
    ! meaningless here. The composition reference is checked externally from v0_export.txt.
    write(*,'(a)') 'V0 mode: identity gate not applicable (tags do not span the vapour)'
 else if (dsum+cre+des > tol) then
    write(*,'(a,es11.3,a,es11.3)') 'FAIL: tag inconsistency ', dsum+cre+des, ' exceeds ', tol
    ok = .false.
 end if
 if (v0mode) then
    open(unit=77,file='v0_export.txt',status='replace')
    do i = 1,nc
       do k = 1,km
          if (wvt_v0(i,k,1) > 0.0) write(77,'(2i5,12es16.7)') i, k, (wvt_v0(i,k,n), n=1,12)
       end do
    end do
    close(77)
    write(*,'(a)') 'V0 export written to v0_export.txt'
 end if
 if (ok) then
    write(*,'(a,es11.3,a)') 'PASS: tag inconsistency within ', tol, ' kg/m2'
 else
    call exit(1)
 end if
 write(*,'(a)') ''
#ifdef WVT_CLAMP_DIAG
 write(*,'(a)') 'internal clamps (count = firings above 1e-10 relative; amt = total moved):'
 do k = 1,11
    if (wvt_clamp_amt(k) > 0.0) write(*,'(a,i3,a,i8,a,es11.3)') &
        '   clamp #', k, '   n=', wvt_clamp_count(k), '   amt=', wvt_clamp_amt(k)
 end do
 if (sum(wvt_clamp_amt) == 0.0) write(*,'(a)') '   none fired'
 write(*,'(a,es11.3,a,i0)') ' max |tagged flux - base flux| in cuflxn: ', &
     wvt_flux_err(1), '  at level ', nint(wvt_flux_err(2))
 write(*,'(a,es11.3,a,es11.3)') ' on entry to cuflxn: max|pdmfup_tr-pdmfup|=', &
     wvt_src_err(1), '   max|pdmfdp_tr-pdmfdp|=', wvt_src_err(2)
 write(*,'(a,i0,a,i0)') ' cubasmcn mid-level parcel fired: ', wvt_midlev_hits, &
     '   base plude negative-humidity repair fired: ', wvt_plude_hits
 if (wvt_midlev_hits == 0) write(*,'(a)') &
    '   WARNING: mirror 9 is NOT exercised by these soundings - unverified'
 write(*,'(a)') ''
#endif
 write(*,'(a)') 'per-level profile, column 1 (only levels with a non-trivial residual):'
 write(*,'(a)') '     k    p[hPa]        pqv       tr_qv-pqv     cap_cre     cap_des'
 do k = 1,km
    if (abs(tr_qv(1,k)-pqv(1,k)) > 1.0e-12 .or. cap_cre(1,k) > 1.0e-12 &
        .or. cap_des(1,k) > 1.0e-12) then
       write(*,'(i6,f10.1,4es13.4)') k, pap(1,k)*0.01, pqv(1,k), &
             tr_qv(1,k)-pqv(1,k), cap_cre(1,k), cap_des(1,k)
    end if
 end do
 write(*,'(a)') ''
 if (ic_w > 0) write(*,'(a,i0,a,i0,a,f7.1,a,es11.3,a,es11.3)') &
    'worst cap_cre: col ', ic_w, ' k=', kc_w, ' (', pap(ic_w,kc_w)*0.01, &
    ' hPa)  pqv=', pqv(ic_w,kc_w), '  tr_qv=', tr_qv(ic_w,kc_w)
 if (nconv == 0) write(*,'(a)') 'WARNING: no column convected - the test is vacuous'

end program sc_driver
