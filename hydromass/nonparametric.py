import numpy as np
from .deproject import *
from .plots import rads_more, get_coolfunc, estimate_P0
from scipy.interpolate import interp1d

# Function to compute linear operator transforming norms of GP model into radial profile

def calc_gp_operator(npt, rads, rin, rout, bin_fact=1.0, smin=None, smax=None):
    # Set up the Gaussian Process model
    rmin = (rin[0] + rout[0]) / 2.

    rmax = np.max(rout)

    width = rout - rin

    # Gaussians logarithmically spaced between min and max radius
    rgaus = np.logspace(np.log10(rmin), np.log10(rmax), npt)

    if smin is None or smax is None:

        # Sigma logarithmically spaced between min and max bin size
        sig = np.logspace(np.log10(bin_fact * rmin), np.log10(np.max(bin_fact * width)),npt)

    else:

        # Sigma logarithmically spaced between min and max bin size
        sig = np.logspace(np.log10(smin), np.log10(smax), npt)

    nrads = len(rads)  # rads may or may not be equal to bins

    # Extend into 2D and compute values of Gaussians at each point
    sigext = np.tile(sig, nrads).reshape(nrads, npt)

    rgext = np.tile(rgaus, nrads).reshape(nrads, npt)

    radsext = np.repeat(rads, npt).reshape(nrads, npt)

    rg = 1. / (np.sqrt(2. * np.pi) * sigext) * np.exp(-(radsext - rgext) ** 2 / 2. / sigext ** 2)

    return rg , rgaus, sig


# Analytical gradient of the Gaussian process model

def calc_gp_grad_operator(npt, rads, rin, rout, bin_fact=1.0, smin=None, smax=None):
    # Set up the Gaussian Process model
    rmin = (rin[0] + rout[0]) / 2.

    rmax = np.max(rout)

    width = rout - rin

    # Gaussians logarithmically spaced between min and max radius
    rgaus = np.logspace(np.log10(rmin), np.log10(rmax), npt)

    if smin is None or smax is None:

        # Sigma logarithmically spaced between min and max bin size
        sig = np.logspace(np.log10(bin_fact * rmin), np.log10(np.max(bin_fact * width)), npt)

    else:

        # Sigma logarithmically spaced between min and max bin size
        sig = np.logspace(np.log10(smin), np.log10(smax), npt)

    nrads = len(rads)  # rads may or may not be equal to bins

    # Extend into 2D and compute values of Gaussians at each point
    sigext = np.tile(sig, nrads).reshape(nrads, npt)

    rgext = np.tile(rgaus, nrads).reshape(nrads, npt)

    radsext = np.repeat(rads, npt).reshape(nrads, npt)

    rg = 1. / (np.sqrt(2. * np.pi) * sigext ** 3) * np.exp(- (radsext - rgext) ** 2 / 2. / sigext ** 2) * (- (radsext - rgext))

    return rg


def kt_GP_from_samples(Mhyd, nmore=5):
    """

    Compute model temperature profile from Forward Mhyd reconstruction evaluated at reference X-ray temperature radii

    :param Mhyd: mhyd.Mhyd object including the reconstruction
    :param model: mhyd.Model object defining the mass model
    :return: Median temperature, Lower 1-sigma percentile, Upper 1-sigma percentile
    """

    if Mhyd.spec_data is None:
        print('No spectral data provided')

        return

    nsamp = len(Mhyd.samples)

    rin_m, rout_m, index_x, index_sz, sum_mat, ntm = rads_more(Mhyd, nmore=nmore)

    vx = MyDeprojVol(rin_m / Mhyd.amin2kpc, rout_m / Mhyd.amin2kpc)

    vol_x = vx.deproj_vol().T

    if Mhyd.spec_data.psfmat is not None:

        mat1 = np.dot(Mhyd.spec_data.psfmat.T, sum_mat)

        proj_mat = np.dot(mat1, vol_x)

    else:

        proj_mat = np.dot(sum_mat, vol_x)

    nvalm = len(rin_m)

    if Mhyd.cf_prof is not None:

        cf_prof = np.repeat(Mhyd.cf_prof, nsamp).reshape(nvalm, nsamp)

    else:

        cf_prof = Mhyd.ccf

    dens_m = np.sqrt(np.dot(Mhyd.Kdens_m, np.exp(Mhyd.samples.T)) / cf_prof * Mhyd.transf)

    t3d = np.dot(Mhyd.GPop, Mhyd.samppar.T)

    if np.max(rout_m) > rout_m[ntm - 1]:
        # Power law outside of the fitted range
        ne0 = dens_m[nvalm - 1, :]

        T0 = Mhyd.sampp0 / ne0

        Tspo = t3d[ntm - 1, :]

        rspo = rout_m[ntm - 1]

        r0 = rout_m[nvalm - 1]

        alpha = - np.log(Tspo / T0) / np.log(rspo / r0)

        nout = nvalm - ntm

        outspec = np.where(rout_m > rspo)

        Tspo_mul = np.tile(Tspo, nout).reshape(nout, nsamp)

        rout_mul = np.repeat(rout_m[outspec], nsamp).reshape(nout, nsamp)

        alpha_mul = np.tile(alpha, nout).reshape(nout, nsamp)

        t3d[outspec] = Tspo_mul * (rout_mul / rspo) ** (-alpha_mul)

    # Mazzotta weights
    ei = dens_m ** 2 * t3d ** (-0.75)

    # Temperature projection
    flux = np.dot(proj_mat, ei)

    tproj = np.dot(proj_mat, t3d * ei) / flux

    tmed, tlo, thi = np.percentile(tproj, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    t3dot, t3dlt, t3dht = np.percentile(t3d, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    t3do, t3dl, t3dh = t3dot[index_x], t3dlt[index_x], t3dht[index_x]

    dict = {
        "R_IN": Mhyd.spec_data.rin_x,
        "R_OUT": Mhyd.spec_data.rout_x,
        "R_REF": Mhyd.spec_data.rref_x,
        "T3D": t3do,
        "T3D_LO": t3dl,
        "T3D_HI": t3dh,
        "TSPEC": tmed,
        "TSPEC_LO": tlo,
        "TSPEC_HI": thi
    }

    return dict


def P_GP_from_samples(Mhyd, nmore=5):
    """

    Compute model pressure profile from Forward Mhyd reconstruction evaluated at the reference SZ radii

    :param Mhyd: mhyd.Mhyd object including the reconstruction
    :return: Median pressure, Lower 1-sigma percentile, Upper 1-sigma percentile
    """

    if Mhyd.sz_data is None:

        print('No SZ data provided')

        return

    rin_m, rout_m, index_x, index_sz, sum_mat, ntm = rads_more(Mhyd, nmore=nmore)

    nsamp = len(Mhyd.samples)

    nvalm = len(rin_m)

    if Mhyd.cf_prof is not None:

        cf_prof = np.repeat(Mhyd.cf_prof, nsamp).reshape(nvalm, nsamp)

    else:

        cf_prof = Mhyd.ccf

    dens_m = np.sqrt(np.dot(Mhyd.Kdens_m, np.exp(Mhyd.samples.T)) / cf_prof * Mhyd.transf)

    t3d = np.dot(Mhyd.GPop, Mhyd.samppar.T)

    if np.max(rout_m) > rout_m[ntm - 1]:
        # Power law outside of the fitted range
        ne0 = dens_m[nvalm - 1, :]

        T0 = Mhyd.sampp0 / ne0

        Tspo = t3d[ntm - 1, :]

        rspo = rout_m[ntm - 1]

        r0 = rout_m[nvalm - 1]

        alpha = - np.log(Tspo / T0) / np.log(rspo / r0)

        nout = nvalm - ntm

        outspec = np.where(rout_m > rspo)

        Tspo_mul = np.tile(Tspo, nout).reshape(nout, nsamp)

        rout_mul = np.repeat(rout_m[outspec], nsamp).reshape(nout, nsamp)

        alpha_mul = np.tile(alpha, nout).reshape(nout, nsamp)

        t3d[outspec] = Tspo_mul * (rout_mul / rspo) ** (-alpha_mul)

    p3d = t3d * dens_m

    pmt, plot, phit = np.percentile(p3d, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    pmed, plo, phi = pmt[index_sz], plot[index_sz], phit[index_sz]

    return pmed, plo, phi


def mass_GP_from_samples(Mhyd, rin=None, rout=None, npt=200, plot=False):

    nsamp = len(Mhyd.samples)

    rin_m, rout_m, index_x, index_sz, sum_mat, ntm = rads_more(Mhyd, nmore=Mhyd.nmore)

    if rin is None:
        rin = np.min(rin_m)

        if rin == 0:
            rin = 1.

    if rout is None:
        rout = np.max(rout_m)

    bins = np.logspace(np.log10(rin), np.log10(rout), npt + 1)

    rin_m = bins[:npt]

    rout_m = bins[1:]

    rref_m = (rin_m + rout_m) / 2.

    nvalm = len(rin_m)

    if Mhyd.cf_prof is not None:

        cf_prof = np.repeat(Mhyd.cf_prof, nsamp).reshape(nvalm, nsamp)

    else:

        cf_prof = Mhyd.ccf

    if Mhyd.fit_bkg:

        Kdens_m = calc_density_operator(rout_m / Mhyd.amin2kpc, Mhyd.pardens, Mhyd.amin2kpc)

        Kdens_grad = calc_grad_operator(rout_m / Mhyd.amin2kpc, Mhyd.pardens, Mhyd.amin2kpc)

    else:

        Kdens_m = calc_density_operator(rout_m / Mhyd.amin2kpc, Mhyd.pardens, Mhyd.amin2kpc, withbkg=False)

        Kdens_grad = calc_grad_operator(rout_m / Mhyd.amin2kpc, Mhyd.pardens, Mhyd.amin2kpc, withbkg=False)

    dens_m = np.sqrt(np.dot(Kdens_m, np.exp(Mhyd.samples.T)) / cf_prof * Mhyd.transf)

    grad_dens = np.dot(Kdens_grad, np.exp(Mhyd.samples.T)) / 2. / dens_m ** 2 / cf_prof * Mhyd.transf

    if Mhyd.spec_data is not None and Mhyd.sz_data is None:

        rout_joint = Mhyd.spec_data.rout_x

    elif Mhyd.spec_data is None and Mhyd.sz_data is not None:

        rout_joint = Mhyd.sz_data.rout_sz

    elif Mhyd.spec_data is not None and Mhyd.sz_data is not None:

        rout_joint = np.sort(np.append(Mhyd.spec_data.rout_x, Mhyd.sz_data.rout_sz))

    rin_joint = np.roll(rout_joint, 1)

    rin_joint[0] = 0.

    GPop, rgauss, sig = calc_gp_operator(Mhyd.ngauss, rout_m, rin_joint, rout_joint, bin_fact=Mhyd.bin_fact, smin=Mhyd.smin, smax=Mhyd.smax)

    GPgrad = calc_gp_grad_operator(Mhyd.ngauss, rout_m, rin_joint, rout_joint, bin_fact=Mhyd.bin_fact, smin=Mhyd.smin, smax=Mhyd.smax)

    t3d = np.dot(GPop, Mhyd.samppar.T)

    rout_mul = np.repeat(rout_m, nsamp).reshape(nvalm, nsamp) * cgskpc

    grad_t3d = rout_mul / cgskpc / t3d * np.dot(GPgrad, Mhyd.samppar.T)

    if np.max(rout_m) > rout_m[ntm - 1]:
        # Power law outside of the fitted range
        ne0 = dens_m[nvalm - 1, :]

        T0 = Mhyd.sampp0 / ne0

        Tspo = t3d[ntm - 1, :]

        rspo = rout_m[ntm - 1]

        r0 = rout_m[nvalm - 1]

        alpha = - np.log(Tspo / T0) / np.log(rspo / r0)

        nout = nvalm - ntm

        outspec = np.where(rout_m > rspo)

        Tspo_mul = np.tile(Tspo, nout).reshape(nout, nsamp)

        rout_mm = np.repeat(rout_m[outspec], nsamp).reshape(nout, nsamp)

        alpha_mul = np.tile(alpha, nout).reshape(nout, nsamp)

        t3d[outspec] = Tspo_mul * (rout_mm / rspo) ** (-alpha_mul)

        grad_t3d[outspec] = - alpha_mul

    mass = - rout_mul * t3d / (cgsG * cgsamu * Mhyd.mup) * (grad_t3d + grad_dens) * kev2erg / Msun

    mmed, mlo, mhi = np.percentile(mass, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    # Matrix containing integration volumes
    volmat = np.repeat(4. / 3. * np.pi * (rout_m ** 3 - rin_m ** 3), nsamp).reshape(nvalm, nsamp)

    # Compute Mgas profile as cumulative sum over the volume

    nhconv = cgsamu * Mhyd.mu_e * cgskpc ** 3 / Msun  # Msun/kpc^3

    ones_mat = np.ones((nvalm, nvalm))

    cs_mat = np.tril(ones_mat)

    mgas = np.dot(cs_mat, dens_m * nhconv * volmat)

    mg, mgl, mgh = np.percentile(mgas, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    fgas = mgas / mass

    fg, fgl, fgh = np.percentile(fgas, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    dict = {
        "R_IN": rin_m,
        "R_OUT": rout_m,
        "MASS": mmed,
        "MASS_LO": mlo,
        "MASS_HI": mhi,
        "MGAS": mg,
        "MGAS_LO": mgl,
        "MGAS_HI": mgh,
        "FGAS": fg,
        "FGAS_LO": fgl,
        "FGAS_HI": fgh
    }

    if plot:

        fig = plt.figure(figsize=(13, 10))

        ax_size = [0.14, 0.12,
                   0.85, 0.85]

        ax = fig.add_axes(ax_size)

        ax.minorticks_on()

        ax.tick_params(length=20, width=1, which='major', direction='in', right=True, top=True)

        ax.tick_params(length=10, width=1, which='minor', direction='in', right=True, top=True)

        for item in (ax.get_xticklabels() + ax.get_yticklabels()):

            item.set_fontsize(22)

        plt.xscale('log')

        plt.yscale('log')

        plt.plot(rout_m, mg, color='blue', label='$M_{\rm gas}$')

        plt.fill_between(rout_m, mgl, mgh, color='blue', alpha=0.4)

        plt.plot(rout_m, mmed, color='red', label='$M_{\rm Hyd}$')

        plt.fill_between(rout_m, mlo, mhi, color='red', alpha=0.4)

        plt.xlabel('Radius [kpc]', fontsize=40)

        plt.ylabel('$M(<R) [M_\odot]$', fontsize=40)

        return dict, fig

    else:

        return dict


def prof_GP_hires(Mhyd, rin=None, npt=200, Z=0.3):
    """
    Compute best-fitting profiles and error envelopes from fitted data

    :param Mhyd: (hydromass.Mhyd) Object containing results of mass reconstruction
    :param model:
    :param nmore:
    :return:
    """

    rin_m, rout_m, index_x, index_sz, sum_mat, ntm = rads_more(Mhyd, nmore=Mhyd.nmore)

    if rin is None:
        rin = np.min(rin_m)

        if rin == 0:
            rin = 1.

    rout = np.max(rout_m)

    bins = np.logspace(np.log10(rin), np.log10(rout), npt + 1)

    rin_m = bins[:npt]

    rout_m = bins[1:]

    rref_m = (rin_m + rout_m) / 2.

    vx = MyDeprojVol(rin_m / Mhyd.amin2kpc, rout_m / Mhyd.amin2kpc)

    vol_x = vx.deproj_vol().T

    nsamp = len(Mhyd.samples)

    nvalm = len(rin_m)

    if Mhyd.cf_prof is not None:

        cf_prof = np.repeat(Mhyd.cf_prof, nsamp).reshape(nvalm, nsamp)

    else:

        cf_prof = Mhyd.ccf

    if Mhyd.fit_bkg:

        Kdens_m = calc_density_operator(rout_m / Mhyd.amin2kpc, Mhyd.pardens, Mhyd.amin2kpc)

    else:

        Kdens_m = calc_density_operator(rout_m / Mhyd.amin2kpc, Mhyd.pardens, Mhyd.amin2kpc, withbkg=False)

    dens_m = np.sqrt(np.dot(Kdens_m, np.exp(Mhyd.samples.T)) / cf_prof * Mhyd.transf)

    if Mhyd.spec_data is not None and Mhyd.sz_data is None:

        rout_joint = Mhyd.spec_data.rout_x

    elif Mhyd.spec_data is None and Mhyd.sz_data is not None:

        rout_joint = Mhyd.sz_data.rout_sz

    elif Mhyd.spec_data is not None and Mhyd.sz_data is not None:

        rout_joint = np.sort(np.append(Mhyd.spec_data.rout_x, Mhyd.sz_data.rout_sz))

    rin_joint = np.roll(rout_joint, 1)

    rin_joint[0] = 0.

    GPop, rgauss, sig = calc_gp_operator(Mhyd.ngauss, rout_m, rin_joint, rout_joint, bin_fact=Mhyd.bin_fact, smin=Mhyd.smin, smax=Mhyd.smax)

    t3d = np.dot(GPop, Mhyd.samppar.T)

    rspo = np.max(rout_joint)

    if rout > rspo:
        # Power law outside of the fitted range
        ne0 = dens_m[nvalm - 1, :]

        T0 = Mhyd.sampp0 / ne0

        finter = interp1d(rout_m, t3d, axis=0)

        Tspo = finter(rspo)

        r0 = rout_m[nvalm - 1]

        alpha = - np.log(Tspo / T0) / np.log(rspo / r0)

        outspec = np.where(rout_m > rspo)

        nout = len(outspec[0])

        Tspo_mul = np.tile(Tspo, nout).reshape(nout, nsamp)

        rout_mul = np.repeat(rout_m[outspec], nsamp).reshape(nout, nsamp)

        alpha_mul = np.tile(alpha, nout).reshape(nout, nsamp)

        t3d[outspec] = Tspo_mul * (rout_mul / rspo) ** (-alpha_mul)

    p3d = t3d * dens_m

    # Mazzotta weights
    ei = dens_m ** 2 * t3d ** (-0.75)

    # Temperature projection
    flux = np.dot(vol_x, ei)

    tproj = np.dot(vol_x, t3d * ei) / flux

    K3d = t3d * dens_m ** (- 2. / 3.)

    mptot, mptotl, mptoth = np.percentile(p3d, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    mt3d, mt3dl, mt3dh = np.percentile(t3d, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    mtp, mtpl, mtph = np.percentile(tproj, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    mne, mnel, mneh = np.percentile(dens_m, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    mK, mKl, mKh = np.percentile(K3d, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    coolfunc, ktgrid = get_coolfunc(Z)

    lambda3d = np.interp(t3d, ktgrid, coolfunc)

    tcool = 3./2. * dens_m * (1. + 1./Mhyd.nhc) * t3d * kev2erg / (lambda3d * dens_m **2 / Mhyd.nhc) / year

    mtc, mtcl, mtch = np.percentile(tcool, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    mcf, mcfl, mcfh = np.percentile(lambda3d, [50., 50. - 68.3 / 2., 50. + 68.3 / 2.], axis=1)

    dict={
        "R_IN": rin_m,
        "R_OUT": rout_m,
        "R_REF": rref_m,
        "P_TOT": mptot,
        "P_TOT_LO": mptotl,
        "P_TOT_HI": mptoth,
        "T3D": mt3d,
        "T3D_LO": mt3dl,
        "T3D_HI": mt3dh,
        "TSPEC": mtp,
        "TSPEC_LO": mtpl,
        "TSPEC_HI": mtph,
        "NE": mne,
        "NE_LO": mnel,
        "NE_HI": mneh,
        "K": mK,
        "K_LO": mKl,
        "K_HI": mKh,
        "T_COOL": mtc,
        "T_COOL_LO": mtcl,
        "T_COOL_HI": mtch,
        "LAMBDA": mcf,
        "LAMBDA_LO": mcfl,
        "LAMBDA_HI": mcfh
    }

    return dict



def Run_NonParametric_PyMC3(Mhyd, bkglim=None, nmcmc=1000, fit_bkg=False, back=None,
                   samplefile=None, nrc=None, nbetas=6, min_beta=0.6, nmore=5,
                   tune=500, bin_fact=1.0, smin=None, smax=None, ngauss=100, find_map=True):
    """

    :param Mhyd:
    :param bkglim:
    :param nmcmc:
    :param fit_bkg:
    :param back:
    :param samplefile:
    :param nrc:
    :param nbetas:
    :param min_beta:
    :param tune:
    :return:
    """

    prof = Mhyd.sbprof
    sb = prof.profile
    esb = prof.eprof
    rad = prof.bins
    erad = prof.ebins
    counts = prof.counts
    area = prof.area
    exposure = prof.effexp
    bkgcounts = prof.bkgcounts

    # Define maximum radius for source deprojection, assuming we have only background for r>bkglim
    if bkglim is None:
        bkglim=np.max(rad+erad)
        Mhyd.bkglim = bkglim
        if back is None:
            back = sb[len(sb) - 1]
    else:
        Mhyd.bkglim = bkglim
        backreg = np.where(rad>bkglim)
        if back is None:
            back = np.mean(sb[backreg])

    # Set source region
    sourcereg = np.where(rad < bkglim)

    # Set vector with list of parameters
    pars = list_params(rad, sourcereg, nrc, nbetas, min_beta)

    npt = len(pars)

    if prof.psfmat is not None:
        psfmat = prof.psfmat
    else:
        psfmat = np.eye(prof.nbin)

    # Compute linear combination kernel
    if fit_bkg:

        K = calc_linear_operator(rad, sourcereg, pars, area, exposure, np.transpose(psfmat)) # transformation to counts

    else:

        Ksb = calc_sb_operator(rad, sourcereg, pars, withbkg=False)

        K = np.dot(psfmat, Ksb)

    # Set up initial values
    if np.isnan(sb[0]) or sb[0] <= 0:
        testval = -10.
    else:
        testval = np.log(sb[0] / npt)
    if np.isnan(back) or back == 0:
        testbkg = -10.
    else:
        testbkg = np.log(back)

    z = Mhyd.redshift

    transf = 4. * (1. + z) ** 2 * (180. * 60.) ** 2 / np.pi / 1e-14 * Mhyd.nhc / cgsMpc * 1e3

    pardens = list_params_density(rad, sourcereg, Mhyd.amin2kpc, nrc, nbetas, min_beta)

    if fit_bkg:

        Kdens = calc_density_operator(rad, pardens, Mhyd.amin2kpc)

    else:

        Kdens = calc_density_operator(rad, pardens, Mhyd.amin2kpc, withbkg=False)

    # Define the fine grid onto which the mass model will be computed
    rin_m, rout_m, index_x, index_sz, sum_mat, ntm = rads_more(Mhyd, nmore=nmore)

    rref_m = (rin_m + rout_m) / 2.

    nptmore = len(rout_m)

    vx = MyDeprojVol(rin_m / Mhyd.amin2kpc, rout_m / Mhyd.amin2kpc)

    vol = vx.deproj_vol().T

    Mhyd.cf_prof = None

    try:
        nn = len(Mhyd.ccf)

    except TypeError:

        print('Single conversion factor provided, we will assume it is constant throughout the radial range')

        cf = Mhyd.ccf

    else:

        if len(Mhyd.ccf) != len(rad):

            print('The provided conversion factor has a different length as the input radial binning. Adopting the mean value.')

            cf = np.mean(Mhyd.ccf)

        else:

            print('Interpolating conversion factor profile onto the radial grid')

            cf = np.interp(rref_m, rad * Mhyd.amin2kpc, Mhyd.ccf)

            Mhyd.cf_prof = cf

    if Mhyd.spec_data is not None:

        if Mhyd.spec_data.psfmat is not None:

            mat1 = np.dot(Mhyd.spec_data.psfmat.T, sum_mat)

            proj_mat = np.dot(mat1, vol)

        else:

            proj_mat = np.dot(sum_mat, vol)

    if fit_bkg:

        Kdens_m = calc_density_operator(rout_m / Mhyd.amin2kpc, pardens, Mhyd.amin2kpc)

        Kdens_grad = calc_grad_operator(rout_m / Mhyd.amin2kpc, pardens, Mhyd.amin2kpc)

    else:

        Kdens_m = calc_density_operator(rout_m / Mhyd.amin2kpc, pardens, Mhyd.amin2kpc, withbkg=False)

        Kdens_grad = calc_grad_operator(rout_m / Mhyd.amin2kpc, pardens, Mhyd.amin2kpc, withbkg=False)

    if Mhyd.spec_data is not None and Mhyd.sz_data is None:

        rout_joint = Mhyd.spec_data.rout_x

    elif Mhyd.spec_data is None and Mhyd.sz_data is not None:

        rout_joint = Mhyd.sz_data.rout_sz

    elif Mhyd.spec_data is not None and Mhyd.sz_data is not None:

        rout_joint = np.sort(np.append(Mhyd.spec_data.rout_x, Mhyd.sz_data.rout_sz))

    rin_joint = np.roll(rout_joint, 1)

    rin_joint[0] = 0.

    GPop, rgauss, sig = calc_gp_operator(ngauss, rout_m, rin_joint, rout_joint, bin_fact=bin_fact, smin=smin, smax=smax)

    GPgrad = calc_gp_grad_operator(ngauss, rout_m, rin_joint, rout_joint, bin_fact=bin_fact, smin=smin, smax=smax)

    P0_est = estimate_P0(Mhyd)

    err_P0_est = P0_est  # 1-dex

    hydro_model = pm.Model()

    with hydro_model:
        # Priors for unknown model parameters
        coefs = pm.Normal('coefs', mu=testval, sd=20, shape=npt)

        if fit_bkg:

            bkgd = pm.Normal('bkg', mu=testbkg, sd=0.05, shape=1) # in case fit_bkg = False this is not fitted

            ctot = pm.math.concatenate((coefs, bkgd), axis=0)

            al = pm.math.exp(ctot)

            pred = pm.math.dot(K, al) + bkgcounts  # Predicted number of counts per annulus

        else:

            al = pm.math.exp(coefs)

            pred = pm.math.dot(K, al)

        # GP parameters
        coefs_GP = pm.Normal('GP', mu=np.log(sig), sd=20, shape=ngauss)

        # Expected value of outcome
        gpp = pm.math.exp(coefs_GP)

        for RV in hydro_model.basic_RVs:
            print(RV.name, RV.logp(hydro_model.test_point))

        t3d = pm.math.dot(GPop, gpp)

        dens_m = pm.math.sqrt(pm.math.dot(Kdens_m, al) / cf * transf)  # electron density in cm-3

        logp0 = pm.TruncatedNormal('logp0', mu=np.log(P0_est), sd=err_P0_est / P0_est,
                                   lower=np.log(P0_est) - err_P0_est / P0_est,
                                   upper=np.log(P0_est) + err_P0_est / P0_est)

        if np.max(rout_m) > rout_m[ntm - 1]:
            # Power law outside of the fitted range
            ne0 = dens_m[nptmore - 1]

            T0 = np.exp(logp0) / ne0

            Tspo = t3d[ntm - 1]

            rspo = rout_m[ntm - 1]

            r0 = rout_m[nptmore - 1]

            alpha = - pm.math.log(Tspo/T0) / np.log(rspo/r0)

            outspec = np.where(rout_m > rspo)

            inspec = np.where(rout_m <= rspo)

            t3d_in = t3d[inspec]

            t3d_out = Tspo * (rout_m[outspec] / rspo) ** (-alpha)

            t3d = pm.math.concatenate([t3d_in, t3d_out])

        # Density Likelihood
        if fit_bkg:

            count_obs = pm.Poisson('counts', mu=pred, observed=counts)  # counts likelihood

        else:

            sb_obs = pm.Normal('sb', mu=pred, observed=sb, sd=esb)  # Sx likelihood

        # Temperature model and likelihood
        if Mhyd.spec_data is not None:

            # Mazzotta weights
            ei = dens_m ** 2 * t3d ** (-0.75)

            # Temperature projection
            flux = pm.math.dot(proj_mat, ei)

            tproj = pm.math.dot(proj_mat, t3d * ei) / flux

            T_obs = pm.Normal('kt', mu=tproj, observed=Mhyd.spec_data.temp_x, sd=Mhyd.spec_data.errt_x)  # temperature likelihood

        # SZ pressure model and likelihood
        if Mhyd.sz_data is not None:

            p3d = t3d * dens_m

            pfit = p3d[index_sz]

            P_obs = pm.MvNormal('P', mu=pfit, observed=Mhyd.sz_data.pres_sz, cov=Mhyd.sz_data.covmat_sz)  # SZ pressure likelihood

    tinit = time.time()

    print('Running MCMC...')

    with hydro_model:

        if find_map:

            start = pm.find_MAP()

            trace = pm.sample(nmcmc, start=start, tune=tune)

        else:

            trace = pm.sample(nmcmc, tune=tune)

    print('Done.')

    tend = time.time()

    print(' Total computing time is: ', (tend - tinit) / 60., ' minutes')

    Mhyd.trace = trace

    # Get chains and save them to file
    sampc = trace.get_values('coefs')

    if fit_bkg:

        sampb = trace.get_values('bkg')

        samples = np.append(sampc, sampb, axis=1)

    else:
        samples = sampc

    Mhyd.samples = samples

    if samplefile is not None:
        np.savetxt(samplefile, samples)
        np.savetxt(samplefile + '.par', np.array([pars.shape[0] / nbetas, nbetas, min_beta, nmcmc]), header='pymc3')

    # Compute output deconvolved brightness profile

    if fit_bkg:
        Ksb = calc_sb_operator(rad, sourcereg, pars)

        allsb = np.dot(Ksb, np.exp(samples.T))

        bfit = np.median(np.exp(samples[:, npt]))

        Mhyd.bkg = bfit

        allsb_conv = np.dot(prof.psfmat, allsb[:, :npt])

    else:
        Ksb = calc_sb_operator(rad, sourcereg, pars, withbkg=False)

        allsb = np.dot(Ksb, np.exp(samples.T))

        allsb_conv = np.dot(K, np.exp(samples.T))

    pmc = np.median(allsb, axis=1)
    pmcl = np.percentile(allsb, 50. - 68.3 / 2., axis=1)
    pmch = np.percentile(allsb, 50. + 68.3 / 2., axis=1)
    Mhyd.sb_dec = pmc
    Mhyd.sb_dec_lo = pmcl
    Mhyd.sb_dec_hi = pmch

    pmc = np.median(allsb_conv, axis=1)
    pmcl = np.percentile(allsb_conv, 50. - 68.3 / 2., axis=1)
    pmch = np.percentile(allsb_conv, 50. + 68.3 / 2., axis=1)
    Mhyd.sb = pmc
    Mhyd.sb_lo = pmcl
    Mhyd.sb_hi = pmch

    Mhyd.nrc = nrc
    Mhyd.nbetas = nbetas
    Mhyd.min_beta = min_beta
    Mhyd.nmore = nmore
    Mhyd.pardens = pardens
    Mhyd.fit_bkg = fit_bkg

    alldens = np.sqrt(np.dot(Kdens, np.exp(samples.T)) * transf)
    pmc = np.median(alldens, axis=1) / np.sqrt(Mhyd.ccf)
    pmcl = np.percentile(alldens, 50. - 68.3 / 2., axis=1) / np.sqrt(Mhyd.ccf)
    pmch = np.percentile(alldens, 50. + 68.3 / 2., axis=1) / np.sqrt(Mhyd.ccf)
    Mhyd.dens = pmc
    Mhyd.dens_lo = pmcl
    Mhyd.dens_hi = pmch

    samppar = np.exp(trace.get_values('GP'))

    Mhyd.samppar = samppar

    Mhyd.GPop = GPop
    Mhyd.GPgrad = GPgrad
    Mhyd.smin = smin
    Mhyd.smax = smax
    Mhyd.bin_fact = bin_fact
    Mhyd.ngauss = ngauss

    Mhyd.K = K
    Mhyd.Kdens = Kdens
    Mhyd.Ksb = Ksb
    Mhyd.transf = transf
    Mhyd.Kdens_m = Kdens_m
    Mhyd.Kdens_grad = Kdens_grad

    sampp0 = np.exp(trace.get_values('logp0'))
    Mhyd.sampp0 = sampp0

    if Mhyd.spec_data is not None:
        kt_mod = kt_GP_from_samples(Mhyd, nmore=nmore)
        Mhyd.ktmod = kt_mod['TSPEC']
        Mhyd.ktmod_lo = kt_mod['TSPEC_LO']
        Mhyd.ktmod_hi = kt_mod['TSPEC_HI']
        Mhyd.kt3d = kt_mod['T3D']
        Mhyd.kt3d_lo = kt_mod['T3D_LO']
        Mhyd.kt3d_hi = kt_mod['T3D_HI']

    if Mhyd.sz_data is not None:
        pmed, plo, phi = P_GP_from_samples(Mhyd, nmore=nmore)
        Mhyd.pmod = pmed
        Mhyd.pmod_lo = plo
        Mhyd.pmod_hi = phi
