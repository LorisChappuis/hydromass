import numpy as np
import os
from astropy.io import fits
from .deproject import MyDeprojVol
from scipy.optimize import brentq
from scipy.signal import convolve


class SpecData:

    '''
    Container class to load a spectroscopic temperature profile and its uncertainties. The data can either be passed all at once by reading a FITS table file or directly as numpy arrays.

    :param redshift: Source redshift
    :type redshift: float
    :param spec_data: Link to a FITS file containing the spectroscopic temperature profile to be read. The FITS table should contain the following fields: 'RIN', 'ROUT', 'KT', 'KT_LO', and 'KT_HI' (see the description below). If None, the values should be passed directly as numpy arrays through the rin, rout, kt, err_kt_low, and err_kt_high arguments. Defaults to None
    :type spec_data: str
    :param rin: 1-D array including the inner boundary definition of the spectroscopic bins (in arcmin). If None, the data should be passed as a FITS file using the spec_data argument. Defaults to None
    :type rin: numpy.ndarray
    :param rout: 1-D array including the outer boundary definition of the spectroscopic bins (in arcmin). If None, the data should be passed as a FITS file using the spec_data argument. Defaults to None
    :type rin: numpy.ndarray
    :param kt: 1-D array containing the fitted spectroscopic temperature (in keV). If None, the data should be passed as a FITS file using the spec_data argument. Defaults to None
    :type kt: numpy.ndarray
    :param err_kt_low: 1-D array containing the lower 1-sigma error on the fitted spectroscopic temperature (in keV). If None, the data should be passed as a FITS file using the spec_data argument. Defaults to None
    :type err_kt_low: numpy.ndarray
    :param err_kt_high: 1-D array containing the upper 1-sigma error on the fitted spectroscopic temperature (in keV). If None, the data should be passed as a FITS file using the spec_data argument. Defaults to None
    :type err_kt_high: numpy.ndarray
    :param cosmo: Astropy cosmology object including the cosmology definition
    :type cosmo: astropy.cosmology
    '''

    def __init__(self, redshift, spec_data=None, rin=None, rout=None, kt=None, err_kt_low=None, err_kt_high=None, cosmo=None, Z=None, Z_low=None, Z_high=None):

        if spec_data is None and kt is None:

            print('No data provided. Please provide either an input FITS data file or a set of numpy arrays.')

            return

        if spec_data is not None and kt is not None:

            print('Ambiguous input. Please provide either an input FITS data file or a set of numpy arrays.')

            return

        if spec_data is not None:

            if not os.path.exists(spec_data):

                print('Spectral data file not found in path, skipping')

            else:

                print('Reading spectral data from file ' + spec_data)

                ftx = fits.open(spec_data)

                dtx = ftx[1].data

                cols = ftx[1].columns

                colnames = cols.names

                if 'RIN' in colnames:

                    rin = dtx['RIN']

                    rout = dtx['ROUT']

                elif 'RADIUS' in colnames:

                    rx = dtx['RADIUS']

                    erx = dtx['WIDTH']

                    rin = rx - erx

                    rout = rx + erx

                else:

                    print('No appropriate data found in input FITS table')

                    return

                self.temp_x = dtx['KT']

                self.templ = dtx['KT_LO']

                self.temph = dtx['KT_HI']

                if 'ZFE' in dtx.names:

                    self.zfe = dtx['ZFE']

                    self.zfe_lo = dtx['ZFE_LO']

                    self.zfe_hi = dtx['ZFE_HI']

                else:

                    self.zfe, self.zfe_lo, self.zfe_hi = None, None, None

                ftx.close()

        if kt is not None:

            if rin is None or rout is None or err_kt_low is None or err_kt_high is None:

                print('Missing input, please provide rin, rout, kt, err_kt_low, and err_kt_high')

                return

            self.temp_x = kt

            self.templ = err_kt_low

            self.temph = err_kt_high

            if Z is not None:

                self.zfe = Z

            else:

                self.zfe = None

            if Z_low is not None:

                self.zfe_lo = Z_low

            else:

                self.zfe_lo = None

            if Z_high is not None:

                self.zfe_hi = Z_high

            else:

                self.zfe_hi = None

        if cosmo is None:

            from astropy.cosmology import Planck15 as cosmo

        amin2kpc = cosmo.kpc_proper_per_arcmin(redshift).value

        self.rin_x = rin * amin2kpc

        self.rout_x = rout * amin2kpc

        self.rin_x_am = rin

        self.rout_x_am = rout

        x = MyDeprojVol(rin, rout)

        self.volume = x.deproj_vol()

        self.errt_x = (self.temph + self.templ) / 2.

        self.rref_x = ((self.rin_x ** 1.5 + self.rout_x ** 1.5) / 2.) ** (2. / 3)

        self.rref_x_am = self.rref_x / amin2kpc

        self.psfmat = None



    def PSF(self, pixsize, psffunc=None, psffile=None, psfimage=None, psfpixsize=None, sourcemodel=None, psfmin=1e-7):
        '''
        Compute a point spread function (PSF) mixing matrix for the loaded spectroscopic data. Each row of the PSF mixing matrix corresponding to a given annulus is computed by defining a normalized image into the annulus and zeros elsewhere. The image is then convolved with the PSF model using FFT. See Eckert et al. 2020 for details.

        The PSF model can be provided either in the form of a one-dimensional radial function or of an image.

        :param pixsize: Pixel size in arcmin
        :type pixsize: float
        :param psffunc: 1D function transforming an array of radii into the PSF model value. If None, an image should be provided. Defaults to None.
        :type psffunc: func
        :param psffile: FITS file containing the model PSF image. If None, the PSF should be provided either as a 1D function or a 2D array. Defaults to None.
        :type psffile: str
        :param psfimage: 2-D array containing an image of the PSF. The pixel size should be passed through the "psfpixsize" argument. If None, the PSF should be provided either as a 1D function or a FITS image. Defaults to None.
        :type psfimage: numpy.ndarray
        :param psfpixsize: Image pixel size (in arcmin) in case a PSF image is provided.
        :type psfpixsize: float
        :param sourcemodel: A pyproffit model describing the radial dependence of the emissivity distribution. If provided, the PSF at each point is weighted by the radial model to take the emissivity gradient across the bins into account when computing the PSF mixing matrix. If None, a flat distribution is assumed. Defaults to None.
        :type sourcemodel: pyproffit.models.model
        :param psfmin: Minimum PSF value (relative to the maximum) below which the effect of the PSF is neglected. Increasing psfmin speeds up the computation at the cost of a lower precision.
        :type psfmin: float
        '''

        rad = (self.rin_x_am + self.rout_x_am) / 2.

        erad = (self.rout_x_am - self.rin_x_am) / 2.

        if psffile is None and psfimage is None and psffunc is None:

            print('No PSF model given')

            return

        else:
            if psffile is not None:

                fpsf = fits.open(psffile)

                psfimage = fpsf[0].data.astype(float)

                if psfpixsize is not None:

                    psfpixsize = float(psfimage[0].header['CDELT2'])

                    if psfpixsize == 0.0:

                        print('Error: no pixel size is provided for the PSF image and the CDELT2 keyword is not set')

                        return

                fpsf.close()

            if psfimage is not None:

                if psfpixsize is None or psfpixsize <= 0.0:

                    print('Error: no pixel size is provided for the PSF image')

                    return

            nbin = len(rad)

            psfout = np.zeros((nbin, nbin))

            npexp = 2 * int((rad[nbin - 1] + erad[nbin - 1]) / pixsize) + 1

            exposure = np.ones((npexp, npexp))

            y, x = np.indices(exposure.shape)

            rads = np.hypot(x - npexp / 2., y - npexp / 2.) * pixsize  # arcmin

            kernel = None

            if psffunc is not None:

                kernel = psffunc(rads)

                norm = np.sum(kernel)

                frmax = lambda x: psffunc(x) * 2. * np.pi * x / norm - psfmin

                if frmax(exposure.shape[0] / 2) < 0.:

                    rmax = brentq(frmax, 1., exposure.shape[0]) / pixsize  # pixsize

                    npix = int(rmax)

                else:
                    npix = int(exposure.shape[0] / 2)

                yp, xp = np.indices((2 * npix + 1, 2 * npix + 1))

                rpix = np.sqrt((xp - npix) ** 2 + (yp - npix) ** 2) * pixsize

                kernel = psffunc(rpix)

                norm = np.sum(kernel)

                kernel = kernel / norm

            if psfimage is not None:

                norm = np.sum(psfimage)

                kernel = psfimage / norm

            if kernel is None:

                print('No kernel provided, bye bye')

                return

            # Sort pixels into radial bins
            tol = 0.5e-5

            sort_list = []

            for n in range(nbin):

                if n == 0:

                    sort_list.append(np.where(np.logical_and(rads >= 0, rads < np.round(rad[n] + erad[n], 5) + tol)))

                else:

                    sort_list.append(np.where(np.logical_and(rads >= np.round(rad[n] - erad[n], 5) + tol,
                                                             rads < np.round(rad[n] + erad[n], 5) + tol)))

            # Calculate average of PSF image pixel-by-pixel and sort it by radial bins
            for n in range(nbin):

                # print('Working with bin',n+1)
                region = sort_list[n]

                npt = len(x[region])

                imgt = np.zeros(exposure.shape)

                if sourcemodel is None or sourcemodel.params is None:

                    imgt[region] = 1. / npt

                else:

                    imgt[region] = sourcemodel.model(rads[region], *sourcemodel.params)

                    norm = np.sum(imgt[region])

                    imgt[region] = imgt[region] / norm

                # FFT-convolve image with kernel
                blurred = convolve(imgt, kernel, mode='same')

                numnoise = np.where(blurred < 1e-15)

                blurred[numnoise] = 0.0

                for p in range(nbin):

                    sn = sort_list[p]

                    psfout[n, p] = np.sum(blurred[sn])

            self.psfmat = psfout


class SZData:
    '''
    Container class to load a SZ pressure profile and its covariance matrix. The data can either be passed all at once by reading a FITS table file or directly as numpy arrays.

    :param redshift: Source redshift
    :type redshift: float
    :param sz_data: Link to a FITS file containing the SZ pressure profile to be read. If None, the values should be passed directly as numpy arrays through the rin, rout, kt, err_kt_low, and err_kt_high arguments. Defaults to None
    :type sz_data: str
    :param rin: 1-D array including the inner boundary definition of the SZ bins (in kpc). If None, the data should be passed as a FITS file using the sz_data argument. Defaults to None
    :type rin: numpy.ndarray
    :param rout: 1-D array including the outer boundary definition of the SZ bins (in kpc). If None, the data should be passed as a FITS file using the sz_data argument. Defaults to None
    :type rin: numpy.ndarray
    :param psz: 1-D array containing the SZ pressure profile (in keV cm^-3). If None, the data should be passed as a FITS file using the sz_data argument. Defaults to None
    :type psz: numpy.ndarray
    :param covmat_sz: 2-D array containing the covariance matrix on the SZ pressure profile. If None, the data should be passed as a FITS file using the sz_data argument. Defaults to None
    :type covmat_sz: numpy.ndarray
    :param cosmo: Astropy cosmology object including the cosmology definition
    :type cosmo: astropy.cosmology
    '''
    def __init__(self, redshift, sz_data=None, rin=None, rout=None, psz=None, covmat_sz=None, cosmo=None):

        if sz_data is None and psz is None:

            print('No data provided. Please provide either an input FITS data file or a set of numpy arrays.')

            return

        if sz_data is not None and psz is not None:

            print('Ambiguous input. Please provide either an input FITS data file or a set of numpy arrays.')

            return

        if sz_data is not None:

            if not os.path.exists(sz_data):

                print('SZ data file not found in path, skipping')

            else:

                print('Reading SZ data file ' + sz_data)

                hdulist = fits.open(sz_data)

                self.pres_sz = hdulist[4].data['FLUX'].reshape(-1)

                self.errp_sz = hdulist[4].data['ERRFLUX'].reshape(-1)

                self.rref_sz = hdulist[4].data['RW'].reshape(-1)

                rin = hdulist[4].data['RIN'].reshape(-1)

                rout = hdulist[4].data['ROUT'].reshape(-1)

                self.covmat_sz = hdulist[4].data['COVMAT'].reshape(len(self.rref_sz), len(self.rref_sz)).astype(
                    np.float32)

        if psz is not None:

            if rin is None or rout is None or covmat_sz is None:

                print('Missing input, please provide rin, rout, psz, and covmat_sz')

                return

            self.pres_sz = psz

            self.covmat_sz = covmat_sz.astype(np.float32)

            self.errp_sz = np.sqrt(np.diag(covmat_sz))

        if cosmo is None:

            from astropy.cosmology import Planck15 as cosmo

        amin2kpc = cosmo.kpc_proper_per_arcmin(redshift).value

        self.rin_sz = rin

        self.rout_sz = rout

        self.rin_sz_am = rin / amin2kpc

        self.rout_sz_am = rout / amin2kpc

        self.rref_sz = (self.rin_sz + self.rout_sz) / 2.




    def PSF(self, pixsize, psffunc=None, psffile=None, psfimage=None, psfpixsize=None, sourcemodel=None, psfmin=1e-7):
        '''
        Compute a point spread function (PSF) mixing matrix for the loaded SZ data. Each row of the PSF mixing matrix corresponding to a given annulus is computed by defining a normalized image into the annulus and zeros elsewhere. The image is then convolved with the PSF model using FFT. See Eckert et al. 2020 for details.

        The PSF model can be provided either in the form of a one-dimensional radial function or of an image.

        :param pixsize: Pixel size in arcmin
        :type pixsize: float
        :param psffunc: 1D function transforming an array of radii into the PSF model value. If None, an image should be provided. Defaults to None.
        :type psffunc: func
        :param psffile: FITS file containing the model PSF image. If None, the PSF should be provided either as a 1D function or a 2D array. Defaults to None.
        :type psffile: str
        :param psfimage: 2-D array containing an image of the PSF. The pixel size should be passed through the "psfpixsize" argument. If None, the PSF should be provided either as a 1D function or a FITS image. Defaults to None.
        :type psfimage: numpy.ndarray
        :param psfpixsize: Image pixel size (in arcmin) in case a PSF image is provided.
        :type psfpixsize: float
        :param sourcemodel: A pyproffit model describing the radial dependence of the emissivity distribution. If provided, the PSF at each point is weighted by the radial model to take the emissivity gradient across the bins into account when computing the PSF mixing matrix. If None, a flat distribution is assumed. Defaults to None.
        :type sourcemodel: pyproffit.models.model
        :param psfmin: Minimum PSF value (relative to the maximum) below which the effect of the PSF is neglected. Increasing psfmin speeds up the computation at the cost of a lower precision.
        :type psfmin: float
        '''

        rad = (self.rin_sz_am + self.rout_sz_am) / 2.

        erad = (self.rout_sz_am - self.rin_sz_am) / 2.

        if psffile is None and psfimage is None and psffunc is None:

            print('No PSF model given')

            return

        else:
            if psffile is not None:

                fpsf = fits.open(psffile)

                psfimage = fpsf[0].data.astype(float)

                if psfpixsize is not None:

                    psfpixsize = float(psfimage[0].header['CDELT2'])

                    if psfpixsize == 0.0:

                        print('Error: no pixel size is provided for the PSF image and the CDELT2 keyword is not set')

                        return

                fpsf.close()

            if psfimage is not None:

                if psfpixsize is None or psfpixsize <= 0.0:

                    print('Error: no pixel size is provided for the PSF image')

                    return

            nbin = len(rad)

            psfout = np.zeros((nbin, nbin))

            npexp = 2 * int((rad[nbin - 1] + erad[nbin - 1]) / pixsize) + 1

            exposure = np.ones((npexp, npexp))

            y, x = np.indices(exposure.shape)

            rads = np.hypot(x - npexp / 2., y - npexp / 2.) * pixsize  # arcmin

            kernel = None

            if psffunc is not None:

                kernel = psffunc(rads)

                norm = np.sum(kernel)

                frmax = lambda x: psffunc(x) * 2. * np.pi * x / norm - psfmin

                if frmax(exposure.shape[0] / 2) < 0.:

                    rmax = brentq(frmax, 1., exposure.shape[0]) / pixsize  # pixsize

                    npix = int(rmax)

                else:
                    npix = int(exposure.shape[0] / 2)

                yp, xp = np.indices((2 * npix + 1, 2 * npix + 1))

                rpix = np.sqrt((xp - npix) ** 2 + (yp - npix) ** 2) * pixsize

                kernel = psffunc(rpix)

                norm = np.sum(kernel)

                kernel = kernel / norm

            if psfimage is not None:

                norm = np.sum(psfimage)

                kernel = psfimage / norm

            if kernel is None:

                print('No kernel provided, bye bye')

                return

            # Sort pixels into radial bins
            tol = 0.5e-5

            sort_list = []

            for n in range(nbin):

                if n == 0:

                    sort_list.append(np.where(np.logical_and(rads >= 0, rads < np.round(rad[n] + erad[n], 5) + tol)))

                else:

                    sort_list.append(np.where(np.logical_and(rads >= np.round(rad[n] - erad[n], 5) + tol,
                                                             rads < np.round(rad[n] + erad[n], 5) + tol)))

            # Calculate average of PSF image pixel-by-pixel and sort it by radial bins
            for n in range(nbin):

                # print('Working with bin',n+1)
                region = sort_list[n]

                npt = len(x[region])

                imgt = np.zeros(exposure.shape)

                if sourcemodel is None or sourcemodel.params is None:

                    imgt[region] = 1. / npt

                else:

                    imgt[region] = sourcemodel.model(rads[region], *sourcemodel.params)

                    norm = np.sum(imgt[region])

                    imgt[region] = imgt[region] / norm

                # FFT-convolve image with kernel
                blurred = convolve(imgt, kernel, mode='same')

                numnoise = np.where(blurred < 1e-15)

                blurred[numnoise] = 0.0

                for p in range(nbin):

                    sn = sort_list[p]

                    psfout[n, p] = np.sum(blurred[sn])

            self.psfmat = psfout
