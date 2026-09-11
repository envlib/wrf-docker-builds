!=================================================================================================
! Single-column harness for the WSM6 water-vapour-tracer instrumentation.
!
! ⚠ WSM6 USES k = 1 AT THE SURFACE. The cumulus harness (../single_column/sc_driver.F90) uses
!   k = 1 at the MODEL TOP. A driver copied across will build every sounding upside down and
!   still run, so setup_soundings asserts p(1) > p(km) before anything else.
!
! Modes (argv(1)):
!   g0   BASE INVARIANCE  -- do_tracers off vs on must be bit-identical. Nothing below is
!                            trustworthy until this passes; it also exercises the whole toolchain.
!   g1   IDENTITY         -- every tag = its base species; the scheme must return them unchanged.
!                            ⚠ PARTIALLY blind to the source species of a ratio mirror. The
!                            algebra tr_P = P/X*tr_X -> P holds for ANY X ONLY WHERE that X is
!                            non-zero. Where the wrongly-named species is zero and the right one
!                            is not (qc > 0, qi == 0), the mirror yields 0 against a non-zero base
!                            rate and the identity breaks loudly -- measured at 5.30 by
!                            mutate.py's pure wrong-source mutant.
!                            ⚠ An earlier version of this comment claimed the blindness was
!                            STRUCTURAL and total. It is not; the first mutant that "confirmed"
!                            it had also changed the guard, so it broke the identity for an
!                            unrelated reason. Treat G1 as a tripwire that happens to catch some
!                            wrong-source errors, not as one that cannot.
!   d1   ATTRIBUTION BIAS -- two-region complete tagging, region 1 = {q,qc,qi}, 2 = {qr,qs,qg}.
!                            The base caps sinks at value+sources (a column-wide factor); the
!                            mirror charges sinks to the pre-existing tag and floors each region
!                            INDEPENDENTLY, so a region whose rain is consumed faster than it held
!                            floors at zero while the region supplying the cloud keeps its new
!                            rain. A MEASUREMENT, not a pass/fail -- it is non-zero on correct code.
!   d2   SEDIMENTATION    -- tag a species on a vertical subset only. nislfv_rain_plm_tr picks its
!                            limiter branch on the BASE slopes and tests positivity on the BASE
!                            only, so a sharp tracer gradient under a smooth base is unguarded.
!                            Reports a sharp interface AND a linear ramp: the effect is
!                            gradient-dependent, so one number alone would mislead.
!
! argv(2) = delt (default 60; use 360 for three substeps), argv(3) = nreg (default 1).
!=================================================================================================
program mp_wsm6_sc
 use ccpp_kind_types,only: kind_phys
 use mp_wsm6,only: mp_wsm6_init,mp_wsm6_run
 use mp_wsm6_common
 implicit none

 integer,parameter:: nc = 24, km = 50, nrmax = 12
 real(kind=kind_phys),parameter:: g=9.81, rd=287.0, rv=461.6, cpd=1004.5, cpv=1846.4
 real(kind=kind_phys),parameter:: t0c=273.15, ep1=rv/rd-1.0, ep2=rd/rv
 real(kind=kind_phys),parameter:: xls=2.85e6, xlv0=2.5e6, xlf0=3.5e5
 real(kind=kind_phys),parameter:: den0=1.28, denr=1000.0, cliq=4190.0, cice=2106.0, psat=610.78
 real(kind=kind_phys),parameter:: dens=100.0

 real(kind=kind_phys),dimension(nc,km):: t0,q0,qc0,qi0,qr0,qs0,qg0,den,p,delz,zz
 real(kind=kind_phys),dimension(nc,km):: t,q,qc,qi,qr,qs,qg
 real(kind=kind_phys),dimension(nc):: rain,rainncv,sr,snow,snowncv,graupel,graupelncv
 real(kind=kind_phys),dimension(nc,km,nrmax):: tr_q,tr_qc,tr_qi,tr_qr,tr_qs,tr_qg
 real(kind=kind_phys),dimension(nc,nrmax):: tr_rain,tr_snow,tr_graupel
 real(kind=kind_phys),dimension(nc,nrmax):: tr_mpcre,tr_mpdes,tr_mpred
 real(kind=kind_phys),dimension(nc,km,6):: ref
 real(kind=kind_phys),dimension(nc,3):: pref
 real(kind=kind_phys):: qmin = 1.0e-15, delt = 60.0
 character(len=256):: errmsg
 character(len=32):: mode, abuf
 integer:: errflg, i, k, n, s, nreg, nfail
 real(kind=kind_phys):: in_b, in_t
 character(len=2),parameter:: spn(6) = (/'q ','qc','qi','qr','qs','qg'/)

 mode = 'g1' ; nreg = 1 ; nfail = 0
 call get_command_argument(1,abuf) ; if (len_trim(abuf)>0) mode = abuf
 call get_command_argument(2,abuf) ; if (len_trim(abuf)>0) read(abuf,*) delt
 call get_command_argument(3,abuf) ; if (len_trim(abuf)>0) read(abuf,*) nreg

 call mp_wsm6_init(den0,denr,dens,cliq,cpv,0,errmsg,errflg)
 call setup_soundings
 ! d1 and d2 choose their own region count; printing argv's would misreport what was run.
 if (trim(mode)=='d1') nreg = 2
 if (trim(mode)=='d2') nreg = 1
 write(*,'(a,a,a,f6.0,a,i3,a,es8.1)') '=== mode ',trim(mode),'  delt=',delt,'  nreg=',nreg, &
      '  qmin=',qmin

 select case (trim(mode))
 case ('g0') ; call gate_g0
 case ('g1') ; call gate_g1
 case ('d1') ; call probe_d1
 case ('d2') ; call probe_d2
 case default ; write(*,*) 'unknown mode ',trim(mode) ; call exit(2)
 end select

 if (nfail > 0) then
   write(*,'(a,i0,a)') 'FAIL: ',nfail,' check(s) failed'
   call exit(1)
 endif
 write(*,'(a)') 'ok'

contains

 subroutine setup_soundings
  real(kind=kind_phys):: ph(km+1), zh(km+1), tsfc, gam, tt, z, es, qsat, rh, tv
  integer:: ityp
  do i = 1,nc
    ityp = (i-1)/8 + 1
    select case (ityp)
    case (1) ; tsfc = 300.0 + mod(i-1,8) ; gam = 6.5e-3     ! tropical warm rain
    case (2) ; tsfc = 284.0 + mod(i-1,8) ; gam = 6.5e-3     ! mid-latitude, melting layer
    case (3) ; tsfc = 262.0 + mod(i-1,8) ; gam = 6.0e-3     ! fully glaciated
    end select
    do k = 1,km+1
      ph(k) = 1000.0e2 - 900.0e2*real(k-1,kind_phys)/real(km,kind_phys)
    enddo
    zh(1) = 0.0
    do k = 1,km
      p(i,k) = 0.5*(ph(k)+ph(k+1))
      z = zh(k) + 0.5*rd*max(tsfc-gam*zh(k),210.0_kind_phys)/g*log(ph(k)/ph(k+1))
      tt = max(tsfc - gam*z, 210.0_kind_phys)
      t0(i,k) = tt
      es = 610.78*exp(17.269*(tt-273.16)/(tt-35.86))
      qsat = ep2*es/max(p(i,k)-es,1.0_kind_phys)
      if (z < 3000.0) then ; rh = 0.95
      else if (z < 8000.0) then ; rh = 0.80
      else ; rh = 0.40 ; endif
      if (mod(i,2)==0 .and. z>1000.0 .and. z<2500.0) rh = 1.04   ! liquid supersaturation -> pcond>0
      if (mod(i,4)==0 .and. tt<255.0 .and. z<9000.0) rh = 1.10   ! ice supersaturation -> pigen/pidep
      if (mod(i,3)==0 .and. z>2500.0 .and. z<5000.0) rh = 0.50   ! dry layer -> evaporation branches
      q0(i,k) = rh*qsat
      tv = tt*(1.0+ep1*q0(i,k))
      den(i,k) = p(i,k)/(rd*tv)
      zh(k+1) = zh(k) + rd*tv/g*log(ph(k)/ph(k+1))
      delz(i,k) = zh(k+1)-zh(k)
      zz(i,k) = z
      qc0(i,k)=0. ; qi0(i,k)=0. ; qr0(i,k)=0. ; qs0(i,k)=0. ; qg0(i,k)=0.
      ! ⚠ Ice is capped below ~11 km ON PURPOSE. Ice placed in the isothermal top layers is
      ! dropped by the semi-Lagrangian remap (mass arriving above the last regular cell), which
      ! makes the BASE scheme lose ~0.5 kg/m2 per call. That is a property of these soundings, not
      ! of the tagging, but it swamps the mass ledger and puts every "created relative to base"
      ! number on a non-conserving base. Found by review round wsm6-code-1.
      select case (ityp)
      case (1)
        if (z>800.0 .and. z<3500.0) qc0(i,k) = 1.5e-3
        if (z<3500.0) qr0(i,k) = 6.0e-4
        if (tt<253.0 .and. z<11000.0) qi0(i,k) = 1.0e-4   ! z bound: see the note above
        if (z>5000.0 .and. z<10000.0) qs0(i,k) = 6.0e-4
        if (z>4000.0 .and. z<8000.0) qg0(i,k) = 4.0e-4
      case (2)
        if (z>500.0 .and. z<2500.0) qc0(i,k) = 1.0e-3
        if (z<2500.0) qr0(i,k) = 4.0e-4
        if (tt<258.0 .and. z<11000.0) qi0(i,k) = 8.0e-5   ! z bound: see the note above
        if (z>1000.0 .and. z<8000.0) qs0(i,k) = 6.0e-4
        if (z>1000.0 .and. z<6000.0) qg0(i,k) = 3.0e-4
      case (3)
        if (z>500.0 .and. z<2000.0) qc0(i,k) = 3.0e-4
        if (z>1000.0 .and. z<8000.0) qi0(i,k) = 8.0e-5
        if (z<8000.0) qs0(i,k) = 5.0e-4
        if (z<5000.0) qg0(i,k) = 2.0e-4
      end select
    enddo
  enddo
  ! ⚠ orientation self-check: WSM6 is k=1 at the SURFACE.
  if (p(1,1) <= p(1,km)) then
    write(*,'(a)') 'FAIL: soundings are upside down (p(1) <= p(km)); WSM6 wants k=1 at the surface'
    call exit(2)
  endif
 end subroutine setup_soundings

 subroutine reset_state
  t=t0 ; q=q0 ; qc=qc0 ; qi=qi0 ; qr=qr0 ; qs=qs0 ; qg=qg0
  rain=0. ; rainncv=0. ; sr=0. ; snow=0. ; snowncv=0. ; graupel=0. ; graupelncv=0.
  tr_q=0. ; tr_qc=0. ; tr_qi=0. ; tr_qr=0. ; tr_qs=0. ; tr_qg=0.
  tr_rain=0. ; tr_snow=0. ; tr_graupel=0.
  tr_mpcre=0. ; tr_mpdes=0. ; tr_mpred=0.
  call wvt_diag_reset
 end subroutine reset_state

 subroutine run_base
  call mp_wsm6_run(t,q,qc,qi,qr,qs,qg,den,p,delz,delt,g,cpd,cpv,rd,rv,t0c,ep1,ep2,qmin,xls, &
                   xlv0,xlf0,den0,denr,cliq,cice,psat,rain,rainncv,sr,snow,snowncv,graupel, &
                   graupelncv,its=1,ite=nc,kts=1,kte=km,errmsg=errmsg,errflg=errflg,        &
                   num_wvt_regions=1)
 end subroutine run_base

 subroutine run_tr(nr)
  integer,intent(in):: nr
  call mp_wsm6_run(t,q,qc,qi,qr,qs,qg,den,p,delz,delt,g,cpd,cpv,rd,rv,t0c,ep1,ep2,qmin,xls, &
                   xlv0,xlf0,den0,denr,cliq,cice,psat,rain,rainncv,sr,snow,snowncv,graupel, &
                   graupelncv,its=1,ite=nc,kts=1,kte=km,errmsg=errmsg,errflg=errflg,        &
                   tr_q=tr_q(:,:,1:nr),tr_qc=tr_qc(:,:,1:nr),tr_qi=tr_qi(:,:,1:nr),         &
                   tr_qr=tr_qr(:,:,1:nr),tr_qs=tr_qs(:,:,1:nr),tr_qg=tr_qg(:,:,1:nr),       &
                   tr_rain=tr_rain(:,1:nr),tr_snow=tr_snow(:,1:nr),                         &
                   tr_graupel=tr_graupel(:,1:nr),do_tracers=.true.,num_wvt_regions=nr,       &
                   tr_mpcre=tr_mpcre(:,1:nr),tr_mpdes=tr_mpdes(:,1:nr),tr_mpred=tr_mpred(:,1:nr))
 end subroutine run_tr

 function colmass(f) result(m)
  real(kind=kind_phys),intent(in):: f(nc,km)
  real(kind=kind_phys):: m
  m = sum(f*den*delz)
 end function colmass

 function basef(s) result(a)
  integer,intent(in):: s
  real(kind=kind_phys):: a(nc,km)
  select case (s)
  case (1) ; a=q
  case (2) ; a=qc
  case (3) ; a=qi
  case (4) ; a=qr
  case (5) ; a=qs
  case (6) ; a=qg
  end select
 end function basef

 function tagsum(s,nr) result(a)
  integer,intent(in):: s,nr
  real(kind=kind_phys):: a(nc,km)
  a = 0.
  do n=1,nr
    select case (s)
    case (1) ; a=a+tr_q(:,:,n)
    case (2) ; a=a+tr_qc(:,:,n)
    case (3) ; a=a+tr_qi(:,:,n)
    case (4) ; a=a+tr_qr(:,:,n)
    case (5) ; a=a+tr_qs(:,:,n)
    case (6) ; a=a+tr_qg(:,:,n)
    end select
  enddo
 end function tagsum

 subroutine seed_identity
  tr_q(:,:,1)=q ; tr_qc(:,:,1)=qc ; tr_qi(:,:,1)=qi
  tr_qr(:,:,1)=qr ; tr_qs(:,:,1)=qs ; tr_qg(:,:,1)=qg
 end subroutine seed_identity

 subroutine gate_g0
  real(kind=kind_phys):: d
  logical:: bad
  call reset_state ; call run_base
  ref(:,:,1)=q ; ref(:,:,2)=qc ; ref(:,:,3)=qi ; ref(:,:,4)=qr ; ref(:,:,5)=qs ; ref(:,:,6)=qg
  pref(:,1)=rain ; pref(:,2)=snow ; pref(:,3)=graupel
  call reset_state ; call seed_identity ; call run_tr(1)
  bad = .false.
  write(*,'(a)') 'G0 base invariance: tracers OFF vs ON (nreg=1). Must be BIT-IDENTICAL.'
  do s=1,6
    d = maxval(abs(basef(s)-ref(:,:,s)))
    write(*,'(4x,a,a,es11.3)') spn(s),' max|diff| ',d
    if (d /= 0.0) bad = .true.
  enddo
  d = max(maxval(abs(rain-pref(:,1))),maxval(abs(snow-pref(:,2))),maxval(abs(graupel-pref(:,3))))
  write(*,'(4x,a,es11.3)') 'rain/snow/graupel max|diff| ',d
  if (d /= 0.0) bad = .true.
  if (bad) then
    write(*,'(a)') '  -> FAIL: turning tracers on changed the forecast'
    nfail = nfail + 1
  else
    write(*,'(a)') '  -> PASS: bit-identical'
  endif
 end subroutine gate_g0

 subroutine gate_g1
  real(kind=kind_phys):: per, tot, tw(nc,km)
  call reset_state ; call seed_identity
  in_b = total_base() ; in_t = total_tags(1)
  call run_tr(1)
  call ledger(1, in_b, in_t)
  write(*,'(a)') 'G1 identity. Per-species and total-water residuals; their DIFFERENCE is the'
  write(*,'(a)') '   species-misattribution measure (mass moved between species, total conserved).'
  per = 0. ; tw = 0.
  do s=1,6
    per = per + colmass(abs(tagsum(s,1)-basef(s)))
    tw = tw + (tagsum(s,1)-basef(s))
  enddo
  tot = colmass(abs(tw))
  write(*,'(4x,a,es12.3,a)') 'per-species residual : ',per,' kg/m2'
  write(*,'(4x,a,es12.3,a)') 'total-water residual : ',tot,' kg/m2'
  call report_counters
  write(*,'(a)') '  ⚠ G1 is PARTIALLY blind to a mirror naming the wrong source species: the'
  write(*,'(a)') '    collapse tr_P = P/X*tr_X -> P holds only WHERE that X is non-zero. It does'
  write(*,'(a)') '    catch the case where the named species is zero and the right one is not.'
  write(*,'(a)') '    Treat a pass as a tripwire, not as proof the mirrors name the right source.'
 end subroutine gate_g1

 subroutine probe_d1
  real(kind=kind_phys):: ex(nc,km), created
  call reset_state
  ! region 1 = the vapour/cloud/ice reservoir, region 2 = the precipitating species.
  tr_q(:,:,1)=q ; tr_qc(:,:,1)=qc ; tr_qi(:,:,1)=qi
  tr_qr(:,:,2)=qr ; tr_qs(:,:,2)=qs ; tr_qg(:,:,2)=qg
  in_b = total_base() ; in_t = total_tags(2)
  call run_tr(2)
  call ledger(2, in_b, in_t)
  write(*,'(a)') 'D1 attribution bias: two-region COMPLETE tagging {q,qc,qi} | {qr,qs,qg}.'
  write(*,'(a)') '   sum_n tr_X exceeding X means the per-region floor kept mass the base removed.'
  do s=1,6
    ex = max(tagsum(s,2)-basef(s),0.0_kind_phys)
    created = colmass(ex)
    write(*,'(4x,a,a,es12.3,a,es10.2)') spn(s),' created : ',created,' kg/m2   base ',colmass(basef(s))
  enddo
  call report_counters
  write(*,'(a)') '  This is a MEASUREMENT, not a pass/fail: it is non-zero on correct code.'
 end subroutine probe_d1

 subroutine probe_d2
  call d2_case('sharp: rain tagged below 1.5 km only',  4, 1500.0_kind_phys, .false.)
  call d2_case('sharp: snow tagged below 6 km only',    5, 6000.0_kind_phys, .false.)
  call d2_case('sharp: graupel tagged below 5 km only', 6, 5000.0_kind_phys, .false.)
  call d2_case('RAMP : rain tagged, linear 0->1 over the column', 4, 0.0_kind_phys, .true.)
  write(*,'(a)') '  Sharp vs ramp is the point: the effect is gradient-dependent, so a single'
  write(*,'(a)') '  number would mislead. Production magnitude needs production tag gradients.'
 end subroutine probe_d2

 subroutine d2_case(label,s,zsplit,ramp)
  character(len=*),intent(in):: label
  integer,intent(in):: s
  real(kind=kind_phys),intent(in):: zsplit
  logical,intent(in):: ramp
  real(kind=kind_phys):: m(nc,km), tagged
  call reset_state
  if (ramp) then
    m = min(max(zz/10000.0_kind_phys,0.0_kind_phys),1.0_kind_phys)
  else
    m = merge(1.0_kind_phys,0.0_kind_phys,zz < zsplit)
  endif
  select case (s)
  case (4) ; tr_qr(:,:,1)=qr*m
  case (5) ; tr_qs(:,:,1)=qs*m
  case (6) ; tr_qg(:,:,1)=qg*m
  end select
  tagged = colmass(tagsum(s,1))
  in_b = total_base() ; in_t = total_tags(1)
  write(*,'(a,a)') '  -- ',label          ! label BEFORE the run: the ledger prints inside it,
  call run_tr(1)                          ! and a block printed above its own label is misread
  call ledger(1, in_b, in_t)
  write(*,'(6x,a,es11.3,a)') 'tagged mass at entry           : ',tagged,' kg/m2'
  write(*,'(6x,a,4es11.3)')  'neg floors created qr,qs,qg,qi : ',wvt_neg_amt
  write(*,'(6x,a,4i8)')      '   firings                     : ',wvt_neg_n
  write(*,'(6x,a,3es11.3)')  'post-sed caps ->vapour qr,qs,qg: ',wvt_cap_amt(7),wvt_cap_amt(8),wvt_cap_amt(9)
  write(*,'(6x,a,2es11.3)')  'vapour rescale DISCARDED       : ',wvt_cap_amt(10),wvt_cap_amt(12)
  write(*,'(6x,a,3es11.3)')  'OUTPUT fields red/des/cre      : ',sum(tr_mpred),sum(tr_mpdes),sum(tr_mpcre)
 end subroutine d2_case

 function total_base() result(m)
  real(kind=kind_phys):: m
  m = 0.
  do s=1,6 ; m = m + colmass(basef(s)) ; enddo
 end function total_base

 function total_tags(nr) result(m)
  integer,intent(in):: nr
  real(kind=kind_phys):: m
  m = 0.
  do s=1,6 ; m = m + colmass(tagsum(s,nr)) ; enddo
 end function total_tags

 subroutine ledger(nr, in_b, in_t)
  !--- THE COMPLETENESS GATE.  out - in + precipitated - created + destroyed == 0
  !
  !  Every counter in this harness is one I chose to write, so no counter can check my
  !  enumeration. The ledger can: if mass appears or vanishes at a site I never instrumented, the
  !  residual is non-zero and names the amount. It was written BEFORE the missing counters on
  !  purpose -- built first it FAILS and says what is missing; built afterwards it would merely
  !  agree with whatever I happened to instrument.
  !
  !  ⚠ `rain` is the TOTAL surface precipitation (snow and graupel are subsets of it), so it is
  !  the only precipitation term -- adding snow/graupel would double-count. 1 mm water == 1 kg/m2.
  integer,intent(in):: nr
  real(kind=kind_phys),intent(in):: in_b, in_t
  real(kind=kind_phys):: out_b, out_t, res_b, res_t, cre, des
  out_b = total_base() ; out_t = total_tags(nr)
  cre = sum(tr_mpcre(:,1:nr)) ; des = sum(tr_mpdes(:,1:nr))
  res_b = out_b - in_b + sum(rain)
  res_t = out_t - in_t + sum(tr_rain(:,1:nr)) - cre + des
  write(*,'(a)') '  MASS LEDGER (kg/m2, all columns): out - in + precip [- created + destroyed]'
  write(*,'(6x,a,es13.5,a,es13.5,a,es12.4)') 'base  out ',out_b,'  in ',in_b,'  residual ',res_b
  write(*,'(6x,a,es13.5,a,es13.5,a,es12.4)') 'tags  out ',out_t,'  in ',in_t,'  residual ',res_t
  write(*,'(6x,a,es12.4,a,es12.4)') 'counted created ',cre,'   counted destroyed ',des
  if (abs(res_b) > 1.0e-8) then
    write(*,'(6x,a,es12.4,a)') 'NOTE: base does not conserve (',res_b,') -- a sounding artefact,'
    write(*,'(6x,a)')          '  not a tagging defect, but it makes the tag residual unreadable.'
  endif
  if (abs(res_t - res_b) > 1.0e-8) then
    write(*,'(6x,a,es12.4,a)') 'FAIL: UNCOUNTED TAG MASS ',res_t-res_b,' kg/m2 appeared or vanished'
    write(*,'(6x,a)')          '  at a site with no counter. The counter set is INCOMPLETE.'
    nfail = nfail + 1
  else
    write(*,'(6x,a)')          'ledger closes: every creation and destruction is counted'
  endif
 end subroutine ledger

 subroutine report_counters
  character(len=16),parameter:: capn(12) = (/ &
    'entry qc        ','entry qi        ','entry qr        ','entry qs        ', &
    'entry qg        ','entry q DISCARD ','postsed qr      ','postsed qs      ', &
    'postsed qg      ','postsed q DISCRD','postice qi      ','postice q DISCRD' /)
  logical:: any
  any = .false.
  write(*,'(a)') '  counters (kg/m2 over all columns; kind 0=redistributive, -1=DESTRUCTIVE):'
  do s=1,12
    if (wvt_cap_n(s) > 0 .or. wvt_cap_amt(s) /= 0.0) then
      write(*,'(6x,a,a,i3,a,es12.3,i9)') capn(s),' kind',wvt_cap_kind(s),'  amt ',wvt_cap_amt(s),wvt_cap_n(s)
      any = .true.
    endif
  enddo
  do s=1,4
    if (wvt_neg_n(s) > 0) then
      write(*,'(6x,a,i1,a,es12.3,i9)') 'neg floor sp',s,' (qr,qs,qg,qi) amt ',wvt_neg_amt(s),wvt_neg_n(s)
      any = .true.
    endif
  enddo
  do s=1,2
    if (wvt_orphan_n(s) > 0) then
      write(*,'(6x,a,i1,a,es12.3,i9)') 'M1 orphan sp',s,' (qc,qi)       amt ',wvt_orphan_amt(s),wvt_orphan_n(s)
      any = .true.
    endif
  enddo
  if (.not. any) write(*,'(6x,a)') 'none fired'
  write(*,'(6x,a,6es10.2)') 'end-of-substep max (sum tr-X)/X q,qc,qi,qr,qs,qg: ',wvt_excess_max
  call compare_output_fields
 end subroutine report_counters

 subroutine compare_output_fields
  !--- The OUTPUT fields (production path, always on) and the WVT_CLAMP_DIAG counters accumulate
  !    the same quantities by different code. Agreement checks the plumbing of the new fields
  !    against an instrument already validated against Fable's independent harness. It does NOT
  !    check the physics -- both read the same cap sites, so a wrong site is invisible to this.
  real(kind=kind_phys):: fred, fdes, fcre, cred, cdes, ccre
  fred = sum(tr_mpred) ; fdes = sum(tr_mpdes) ; fcre = sum(tr_mpcre)
  cred = wvt_cap_amt(1)+wvt_cap_amt(2)+wvt_cap_amt(3)+wvt_cap_amt(4)+wvt_cap_amt(5) &
       + wvt_cap_amt(7)+wvt_cap_amt(8)+wvt_cap_amt(9)+wvt_cap_amt(11)
  cdes = wvt_cap_amt(6)+wvt_cap_amt(10)+wvt_cap_amt(12)
  ! ⚠ tr_mpcre is fed by BOTH the sedimentation floors (wvt_neg_amt) and the process/entry
  ! floors (wvt_floor_amt). Omitting the second made the baseline cross-check disagree by
  ! exactly the mass step 2 instrumented -- found by mutate.py reporting a nonsense baseline.
  ccre = sum(wvt_neg_amt) + sum(wvt_floor_amt)
  write(*,'(a)') '  output fields vs diagnostic counters (independent accumulations, kg/m2):'
  write(*,'(6x,a,es12.4,a,es12.4,a,es9.1)') 'REDISTRIBUTIVE field ',fred,'  counter ',cred, &
       '  rel ',abs(fred-cred)/max(abs(cred),1.e-30)
  write(*,'(6x,a,es12.4,a,es12.4,a,es9.1)') 'DESTRUCTIVE    field ',fdes,'  counter ',cdes, &
       '  rel ',abs(fdes-cdes)/max(abs(cdes),1.e-30)
  write(*,'(6x,a,es12.4,a,es12.4,a,es9.1)') 'CREATIVE       field ',fcre,'  counter ',ccre, &
       '  rel ',abs(fcre-ccre)/max(abs(ccre),1.e-30)
 end subroutine compare_output_fields

end program mp_wsm6_sc
