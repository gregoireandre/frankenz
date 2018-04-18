#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Functions for manipulating PDFs.

"""

from __future__ import (print_function, division)
import six
from six.moves import range

import sys
import os
import warnings
import math
import numpy as np
import warnings
from scipy.special import erf, xlogy, gammaln

__all__ = ["_loglike", "_loglike_s", "loglike",
           "gaussian", "gaussian_bin", "gauss_kde", "gauss_kde_dict",
           "magnitude", "inv_magnitude", "luptitude", "inv_luptitude",
           "PDFDict"]


def _loglike(data, data_err, data_mask, models, models_err, models_mask,
             ignore_model_err=False, dim_prior=True, *args, **kwargs):
    """
    Internal function for computing the log-likelihood between noisy
    data and noisy models.

    Parameters
    ----------
    data : `~numpy.ndarray` of shape (Nfilt)
        Observed data values.

    data_err : `~numpy.ndarray` of shape (Nfilt)
        Associated (Normal) errors on the observed values.

    data_mask : `~numpy.ndarray` of shape (Nfilt)
        Binary mask (0/1) indicating whether the data was observed.

    models : `~numpy.ndarray` of shape (Nmodel, Nfilt)
        Model values.

    models_err : `~numpy.ndarray` of shape (Nmodel, Nfilt)
        Associated errors on the model values.

    models_mask : `~numpy.ndarray` of shape (Nmodel, Nfilt)
        Binary mask (0/1) indicating whether the model value was observed.

    ignore_model_err : bool, optional
        Whether to ignore model errors during calculation.
        Default is `False`.

    dim_prior : bool, optional
        Whether to apply a dimensional-based correction (prior) to the
        log-likelihood. Transforms the likelihood to a chi2 distribution
        with `Nfilt` degrees of freedom. Default is `True`.

    Returns
    -------
    lnlike : `~numpy.ndarray` of shape (Nmodel)
        Log-likelihood values.

    Ndim : `~numpy.ndarray` of shape (Nmodel)
        Number of observations used in the fit (dimensionality).

    chi2 : `~numpy.ndarray` of shape (Nmodel)
        Chi-square values used to compute the log-likelihood.

    """

    # Initialize errors.
    if ignore_model_err:
        tot_var = np.square(data_err) + np.zeros_like(models_err)
    else:
        tot_var = np.square(data_err) + np.square(models_err)

    # Initialize mask.
    tot_mask = data_mask * models_mask  # combined binary mask
    Ndim = np.sum(tot_mask, axis=1)  # number of dimensions

    # Compute chi2.
    resid = data - models  # residuals
    chi2 = np.sum(tot_mask * np.square(resid) / tot_var, axis=1)  # chi2

    # Apply dimensionality prior.
    if dim_prior:
        # Compute logpdf of chi2 distribution.
        a = 0.5 * Ndim  # dof
        lnl = xlogy(a - 1., chi2) - (chi2 / 2.) - gammaln(a) - (np.log(2.) * a)
    else:
        # Compute logpdf of multivariate normal.
        lnl = -0.5 * chi2
        lnl += -0.5 * (Ndim * np.log(2. * np.pi) +
                       np.sum(np.log(tot_var), axis=1))

    return lnl, Ndim, chi2


def _loglike_s(data, data_err, data_mask, models, models_err, models_mask,
               ignore_model_err=False, dim_prior=True, ltol=1e-4,
               return_scale=False, *args, **kwargs):
    """
    Internal function for computing the log-likelihood between noisy
    data and noisy models while allowing the model to be rescaled.

    Parameters
    ----------
    data : `~numpy.ndarray` of shape (Nfilt)
        Observed data values.

    data_err : `~numpy.ndarray` of shape (Nfilt)
        Associated (Normal) errors on the observed values.

    data_mask : `~numpy.ndarray` of shape (Nfilt)
        Binary mask (0/1) indicating whether the data was observed.

    models : `~numpy.ndarray` of shape (Nmodel, Nfilt)
        Model values.

    models_err : `~numpy.ndarray` of shape (Nmodel, Nfilt)
        Associated errors on the model values.

    models_mask : `~numpy.ndarray` of shape (Nmodel, Nfilt)
        Binary mask (0/1) indicating whether the model value was observed.

    ignore_model_err : bool, optional
        Whether to ignore the model errors during calculation.
        Default is `False`.

    dim_prior : bool, optional
        Whether to apply a dimensional-based correction (prior) to the
        log-likelihood. Transforms the likelihood to a chi2 distribution
        with `Nfilt - 1` degrees of freedom. Default is `True`.

    ltol : float, optional
        The fractional tolerance in the log-likelihood function used to
        determine convergence when including errors when the scale factor is
        left free (i.e. `free_scale = True` and `ignore_model_err = False`).
        Default is `1e-4`.

    return_scale : bool, optional
        Whether to return the scale factor.
        Default is `False`.

    Returns
    -------
    lnlike : `~numpy.ndarray` of shape (Nmodel)
        Log-likelihood values.

    Ndim : `~numpy.ndarray` of shape (Nmodel)
        Number of observations used in the fit (dimensionality).

    chi2 : `~numpy.ndarray` of shape (Nmodel)
        Chi-square values used to compute the log-likelihood.

    scale : `~numpy.ndarray` of shape (Nmodel), optional
        The factor used to scale the model observations to the observed data.
        Returned if `return_scale = True`.

    """

    # Initialize errors.
    if ignore_model_err:
        tot_var = np.square(data_err) + np.zeros_like(models_err)
    else:
        tot_var = np.square(data_err) + np.square(models_err)

    # Initialize mask.
    tot_mask = data_mask * models_mask  # combined binary mask
    Ndim = np.sum(tot_mask, axis=1)  # number of dimensions

    # Derive scalefactors between data and models.
    inter_num = tot_mask * models * data[None, :]
    inter_vals = np.sum(inter_num / tot_var, axis=1)  # "interaction"
    shape_num = tot_mask * np.square(models)
    shape_vals = np.sum(shape_num / tot_var, axis=1)  # "shape" term
    scale = inter_vals / shape_vals  # scalefactor

    # Compute chi2.
    resid = data - scale[:, None] * models  # scaled residuals
    chi2 = np.sum(tot_mask * np.square(resid) / tot_var, axis=1)  # chi2

    # Compute multivariate normal logpdf.
    lnl = -0.5 * chi2
    lnl += -0.5 * (Ndim * np.log(2. * np.pi) +
                   np.sum(np.log(tot_var), axis=1))

    # Iterate until convergence if we don't ignore model errors.
    if ignore_model_err is not True:
        lerr = np.inf  # initialize ln(like) error
        while lerr > ltol:
            # Compute new variance using our previous scale.
            tot_var = np.square(data_err) + np.square(scale[:, None] *
                                                      models_err)

            # Compute new scale.
            inter_vals = np.sum(inter_num / tot_var, axis=1)
            shape_vals = np.sum(shape_num / tot_var, axis=1)
            scale_new = inter_vals / shape_vals

            # Compute new chi2.
            resid = data - scale_new[:, None] * models
            chi2 = np.sum(tot_mask * np.square(resid) / tot_var, axis=1)

            # Compute new logpdf.
            lnl_new = -0.5 * chi2
            lnl_new += -0.5 * (Ndim * np.log(2. * np.pi) +
                               np.sum(np.log(tot_var), axis=1))

            # Check tolerance.
            loglike_err = ((lnl_new - lnl) / lnl)
            lerr = max(abs(loglike_err))

            # Assign new values.
            lnl, scale = lnl_new, scale_new

    # Apply dimensionality prior.
    if dim_prior:
        # Compute logpdf of chi2 distribution.
        a = 0.5 * (Ndim - 1)  # dof
        lnl = xlogy(a - 1., chi2) - (chi2 / 2.) - gammaln(a) - (np.log(2.) * a)

    if return_scale:
        return lnl, Ndim, chi2, scale
    else:
        return lnl, Ndim, chi2


def loglike(data, data_err, data_mask, models, models_err, models_mask,
            free_scale=False, ignore_model_err=False, dim_prior=True,
            ltol=1e-4, return_scale=False, *args, **kwargs):
    """
    Compute the ln(likelihood) between an input set of data vectors and an
    input set of (scale-free and/or error-free) model vectors.

    Parameters
    ----------
    data : `~numpy.ndarray` of shape (Nfilt)
        Observed data values.

    data_err : `~numpy.ndarray` of shape (Nfilt)
        Associated (Normal) errors on the observed values.

    data_mask : `~numpy.ndarray` of shape (Nfilt)
        Binary mask (0/1) indicating whether the data was observed.

    models : `~numpy.ndarray` of shape (Nmodel, Nfilt)
        Model values.

    models_err : `~numpy.ndarray` of shape (Nmodel, Nfilt)
        Associated errors on the model values.

    models_mask : `~numpy.ndarray` of shape (Nmodel, Nfilt)
        Binary mask (0/1) indicating whether the model value was observed.

    free_scale : bool, optional
        Whether to include a free scale factor (scaling the model to the data)
        in the fit. Default is `False`.

    ignore_model_err : bool, optional
        Whether to ignore the model errors during calculation.
        Default is `False`.

    dim_prior : bool, optional
        Whether to apply a dimensional-based correction (prior) to the
        log-likelihood. Transforms the likelihood to a Gamma distribution
        with shape parameter `a = dof /2.`. Default is `True`.

    ltol : float, optional
        The fractional tolerance in the log-likelihood function used to
        determine convergence when including errors when the scale factor is
        left free (i.e. `free_scale = True` and `ignore_model_err = False`).
        Default is `1e-4`.

    return_scale : bool, optional
        Whether to return the scale factor derived when `free_scale = True`.
        Default is `False`.

    Returns
    -------
    lnlike : `~numpy.ndarray` of shape (Nmodel)
        Log-likelihood values.

    Ndim : `~numpy.ndarray` of shape (Nmodel)
        Number of observations used in the fit (dimensionality).

    chi2 : `~numpy.ndarray` of shape (Nmodel)
        Chi-square values used to compute the log-likelihood.

    scale : `~numpy.ndarray` of shape (Nmodel), optional
        The factor used to scale the model observations to the observed data.
        Returned if `return_scale = True`.

    """

    if free_scale:
        results = _loglike_s(data, data_err, data_mask, models, models_err,
                             models_mask, ignore_model_err=ignore_model_err,
                             dim_prior=dim_prior, ltol=ltol,
                             return_scale=return_scale)
    else:
        results = _loglike(data, data_err, data_mask, models, models_err,
                           models_mask, ignore_model_err=ignore_model_err,
                           dim_prior=dim_prior)

    return results


def gaussian(mu, std, x):
    """
    Gaussian kernal with mean `mu` and standard deviation `std` evaluated
    over grid `x`. Returns the PDF `N(x | mu, std)`.

    """

    dif = x - mu  # difference
    norm = np.sqrt(2. * np.pi) * std  # normalization
    pdf = np.exp(-0.5 * np.square(dif / std)) / norm

    return pdf


def gaussian_bin(mu, std, bins):
    """
    Gaussian kernal with mean `mu` and standard deviation `std` evaluated
    over a set of bins with edges specified by `bins`.
    Returns the PDF integrated over the bins (i.e. an `N - 1`-length vector).

    """

    dif = bins - mu  # difference
    y = dif / (np.sqrt(2) * std)  # divide by relative width
    cdf = 0.5 * (1. + erf(y))  # CDF evaluated at bin edges
    pdf = cdf[1:] - cdf[:-1]  # amplitude integrated over the bins

    return pdf


def gauss_kde(y, y_std, x, dx=None, y_wt=None, sig_thresh=5., wt_thresh=1e-3,
              cdf_thresh=2e-4, *args, **kwargs):
    """
    Compute smoothed PDF using kernel density estimation.

    Parameters
    ----------
    y : `~numpy.ndarray` with shape (Ny,)
        Array of observed values.

    y_std : `~numpy.ndarray` with shape (Ny,)
        Array of (Gaussian) errors associated with the observed values.

    x : `~numpy.ndarray` with shape (Nx,)
        Grid over which the PDF will be evaluated. Note that this grid should
        be evenly spaced to ensure appropriate sigma clipping behavior.

    dx : float, optional
        The spacing of the input `x` grid. If not provided, `dx` will be
        computed from `x[1] - x[0]`.

    y_wt : `~numpy.ndarray` with shape (Ny,), optional
        An associated set of weights for each of the elements in `y`. If not
        provided, objects will be weighted uniformly.

    sig_thresh : float, optional
        The number of standard deviations from the mean to evaluate
        from before clipping the Gaussian. Default is `5.`.

    wt_thresh : float, optional
        The threshold `wt_thresh * max(y_wt)` used to ignore objects
        with (relatively) negligible weights. Default is `1e-3`.

    cdf_thresh : float, optional
        The `1. - cdf_thresh` threshold of the (sorted) CDF used to ignore
        objects with (relatively) negligible weights. This option is only
        used when `wt_thresh=None`. Default is `2e-4`.

    Returns
    -------
    pdf : `~numpy.ndarray` with shape (Nx,)
        Probability distribution function (PDF) evaluated over `x`.

    """

    # Initialize values.
    Nx, Ny = len(x), len(y)
    if dx is None:
        dx = x[1] - x[0]
    if y_wt is None:
        y_wt = np.ones(Ny)
    if wt_thresh is None and cdf_thresh is None:
        wt_thresh = -np.inf  # default to no clipping/thresholding

    # Clipping kernels.
    centers = np.array((y - x[0]) / dx, dtype='int')  # discretized centers
    offsets = np.array(sig_thresh * y_std / dx, dtype='int')  # offsets
    uppers, lowers = centers + offsets, centers - offsets  # upper/lower bounds
    uppers[uppers > Nx], lowers[lowers < 0] = Nx, 0  # limiting to grid edges

    # Initialize PDF.
    pdf = np.zeros(Nx)

    # Apply thresholding.
    if wt_thresh is not None:
        # Use relative amplitude to threshold.
        sel_arr = np.arange(Ny)[y_wt > (wt_thresh * np.max(y_wt))]
    else:
        # Use CDF to threshold.
        idx_sort = np.argsort(y_wt)  # sort
        y_cdf = np.cumsum(y_wt[idx_sort])  # compute CDF
        y_cdf /= y_cdf[-1]  # normalize
        sel_arr = idx_sort[y_cdf <= (1. - cdf_thresh)]

    # Compute PDF.
    for i in sel_arr:
        # Stack weighted Gaussian kernel over array slice.
        gkde = gaussian(y[i], y_std[i], x[lowers[i]:uppers[i]])
        norm = sum(gkde)
        if norm != 0.:
            pdf[lowers[i]:uppers[i]] += y_wt[i] / norm * gkde

    return pdf


def gauss_kde_dict(pdfdict, y=None, y_std=None, y_idx=None, y_std_idx=None,
                   y_wt=None, wt_thresh=1e-3, cdf_thresh=2e-4,
                   *args, **kwargs):
    """
    Compute smoothed PDF using kernel density estimation based on a
    pre-computed dictionary and pre-defined grid.

    Parameters
    ----------
    pdfdict : :class:`PDFDict` instance
        `PDFDict` instance containing the grid and kernels.

    y, y_std : `~numpy.ndarray` with shape (Ny,), optional
        Array of observed values and associated (Gaussian) errors. Mutually
        exclusive with `y_idx` and `y_std_idx`.

    y_idx, y_std_idx : `~numpy.ndarray` with shape (Ny,), optional
        Array of dictionary indices corresponding to the observed values and
        associated errors. Mutually exclusive with `y` and `y_std`. Preference
        will be given to `y_idx` and `y_std_idx` if provided.

    y_wt : `~numpy.ndarray` with shape (Ny,), optional
        An associated set of weights for each of the elements in `y`. If not
        provided, objects will be weighted uniformly.

    wt_thresh : float, optional
        The threshold `wt_thresh * max(y_wt)` used to ignore objects
        with (relatively) negligible weights. Default is `1e-3`.

    cdf_thresh : float, optional
        The `1. - cdf_thresh` threshold of the (sorted) CDF used to ignore
        objects with (relatively) negligible weights. This option is only
        used when `wt_thresh=None`. Default is `2e-4`.

    Returns
    -------
    pdf : `~numpy.ndarray` with shape (Nx,)
        Probability distribution function (PDF) evaluated over `pdfdict.grid`.

    """

    # Check for valid inputs.
    if y_idx is not None and y_std_idx is not None:
        pass
    elif y is not None and y_std is not None:
        y_idx, y_std_idx = pdfdict.fit(y, y_std)
    else:
        raise ValueError("At least one pair of (`y`, `y_std`) or "
                         "(`y_idx`, `y_idx_std`) must be specified.")
    if wt_thresh is None and cdf_thresh is None:
        wt_thresh = -np.inf  # default to no clipping/thresholding

    # Initialize PDF.
    Nx = pdfdict.Ngrid
    pdf = np.zeros(Nx)

    # Apply weight thresholding.
    Ny = len(y_idx)
    if y_wt is None:
        y_wt = np.ones(Ny)
    if wt_thresh is not None:
        # Use relative amplitude to threshold.
        sel_arr = np.arange(Ny)[y_wt > (wt_thresh * np.max(y_wt))]
    else:
        # Use CDF to threshold.
        idx_sort = np.argsort(y_wt)  # sort
        y_cdf = np.cumsum(y_wt[idx_sort])  # compute CDF
        y_cdf /= y_cdf[-1]  # normalize
        sel_arr = idx_sort[y_cdf <= (1. - cdf_thresh)]

    # Compute PDF.
    sigma_dict = pdfdict.sigma_dict  # Gaussian kernel dictionary
    sigma_width = pdfdict.sigma_width  # number of elements in each kernel
    sigma_dict_cdf = pdfdict.sigma_dict_cdf  # CDF of Gaussian kernel
    for i in sel_arr:
        # Select position and kernel.
        idx = y_std_idx[i]  # dictionary element
        pos = y_idx[i]  # kernel center
        kernel = sigma_dict[idx]  # Gaussian kernel
        width = sigma_width[idx]  # kernel width
        kcdf = sigma_dict_cdf[idx]  # kernel CDF

        # Deal with edge effects.
        low, high = max(pos - width, 0), min(pos + width + 1, Nx)
        lpad, hpad = low - (pos - width), high - (pos + width + 1)
        if lpad == 0:
            norm = kcdf[hpad-1]
        else:
            norm = kcdf[hpad-1] - kcdf[lpad-1]

        # Stack weighted Gaussian kernel over array slice.
        pdf[low:high] += (y_wt[i] / norm) * kernel[lpad:2*width+1+hpad]

    return pdf


def magnitude(phot, err, zeropoints=1., *args, **kwargs):
    """
    Convert photometry to AB magnitudes.

    Parameters
    ----------
    phot : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Observed photometric flux densities.

    err : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Observed photometric flux density errors.

    zeropoints : float or `~numpy.ndarray` with shape (Nfilt,)
        Flux density zero-points. Used as a "location parameter".
        Default is `1.`.

    Returns
    -------
    mag : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Magnitudes corresponding to input `phot`.

    mag_err : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Magnitudes errors corresponding to input `err`.

    """

    # Compute magnitudes.
    mag = -2.5 * np.log10(phot / zeropoints)

    # Compute errors.
    mag_err = 2.5 / np.log(10.) * err / phot

    return mag, mag_err


def inv_magnitude(mag, err, zeropoints=1., *args, **kwargs):
    """
    Convert AB magnitudes to photometry.

    Parameters
    ----------
    mag : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Magnitudes.

    err : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Magnitude errors.

    zeropoints : float or `~numpy.ndarray` with shape (Nfilt,)
        Flux density zero-points. Used as a "location parameter".
        Default is `1.`.

    Returns
    -------
    phot : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Photometric flux densities corresponding to input `mag`.

    phot_err : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Photometric errors corresponding to input `err`.

    """

    # Compute magnitudes.
    phot = 10**(-0.4 * mag) * zeropoints

    # Compute errors.
    phot_err = err * 0.4 * np.log(10.) * phot

    return phot, phot_err


def luptitude(phot, err, skynoise=1., zeropoints=1., *args, **kwargs):
    """
    Convert photometry to asinh magnitudes (i.e. "Luptitudes"). See Lupton et
    al. (1999) for more details.

    Parameters
    ----------
    phot : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Observed photometric flux densities.

    err : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Observed photometric flux density errors.

    skynoise : float or `~numpy.ndarray` with shape (Nfilt,)
        Background sky noise. Used as a "softening parameter".
        Default is `1.`.

    zeropoints : float or `~numpy.ndarray` with shape (Nfilt,)
        Flux density zero-points. Used as a "location parameter".
        Default is `1.`.

    Returns
    -------
    mag : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Asinh magnitudes corresponding to input `phot`.

    mag_err : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Asinh magnitudes errors corresponding to input `err`.

    """

    # Compute asinh magnitudes.
    mag = -2.5 / np.log(10.) * (np.arcsinh(phot / (2. * skynoise)) +
                                np.log(skynoise / zeropoints))

    # Compute errors.
    mag_err = np.sqrt(np.square(2.5 * np.log10(np.e) * err) /
                      (np.square(2. * skynoise) + np.square(phot)))

    return mag, mag_err


def inv_luptitude(mag, err, skynoise=1., zeropoints=1., *args, **kwargs):
    """
    Convert asinh magnitudes ("Luptitudes") to photometry.

    Parameters
    ----------
    mag : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Asinh magnitudes.

    err : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Asinh magnitude errors.

    skynoise : float or `~numpy.ndarray` with shape (Nfilt,)
        Background sky noise. Used as a "softening parameter".
        Default is `1.`.

    zeropoints : float or `~numpy.ndarray` with shape (Nfilt,)
        Flux density zero-points. Used as a "location parameter".
        Default is `1.`.

    Returns
    -------
    phot : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Photometric flux densities corresponding to input `mag`.

    phot_err : `~numpy.ndarray` with shape (Nobs, Nfilt)
        Photometric errors corresponding to input `err`.

    """

    # Compute photometry.
    phot = (2. * skynoise) * np.sinh(np.log(10.) / -2.5 * mag -
                                     np.log(skynoise / zeropoint))

    # Compute errors.
    phot_err = np.sqrt((np.square(2. * skynoise) + np.square(phot)) *
                       np.square(err)) / (2.5 * np.log10(np.e))

    return phot, phot_err


class PDFDict():
    """
    Class used to establish a set of underlying grids and Gaussian kernels
    used to quickly compute PDFs. PDFs are computed by sliding, truncating, and
    stacking our kernels along the underlying grid.

    Parameters
    ----------
    pdf_grid : `~numpy.ndarray` of shape (Ngrid,)
        The underlying discretized grid used to evaluate PDFs. **This grid
        must be evenly spaced.**

    sigma_grid : `~numpy.ndarray` of shape (Ndict,)
        The standard deviations used to compute the set of discretized
        Gaussian kernels.

    sigma_trunc : float, optional
        The number of sigma used before truncating our Gaussian kernels.
        Default is `5.`.

    """

    def __init__(self, pdf_grid, sigma_grid, sigma_trunc=5.):

        # Initialize quantities.
        self.Ngrid = len(pdf_grid)
        self.min, self.max = min(pdf_grid), max(pdf_grid)
        self.delta = pdf_grid[1] - pdf_grid[0]
        self.grid = np.array(pdf_grid)

        # Create dictionary.
        self.Ndict = len(sigma_grid)
        self.sigma_grid = np.array(sigma_grid)
        self.dsigma = sigma_grid[1] - sigma_grid[0]
        self.sigma_width = np.array(np.ceil(sigma_grid * sigma_trunc /
                                    self.delta), dtype='int')
        mid = int(self.Ngrid / 2)
        self.sigma_dict = [gaussian(mu=self.grid[mid], std=s,
                                    x=self.grid[mid-w:mid+w+1])
                           for i, (s, w) in enumerate(zip(self.sigma_grid,
                                                          self.sigma_width))]
        self.sigma_dict_cdf = [np.cumsum(p) for p in self.sigma_dict]

    def fit(self, X, Xe):
        """
        Map Gaussian PDFs onto the dictionary.

        Parameters
        ----------
        X : `~numpy.ndarray` of shape (Nobs,)
            Observed values.

        Xe : `~numpy.ndarray` of shape (Nobs,)
            Observed errors.

        Returns
        -------
        X_idx : `~numpy.ndarray` of shape (Nobs,)
            Corresponding indices on the dicretized mean grid.

        Xe_idx : `~numpy.ndarray` of shape (Nobs,)
            Corresponding indices on the discretized sigma grid.

        """

        # Mean indices.
        X_idx = ((X - self.grid[0]) / self.delta).round().astype('int')

        # Sigma (dictionary) indices.
        Xe_idx = np.array(np.round((Xe - self.sigma_grid[0]) / self.dsigma),
                          dtype='int')
        Xe_idx[Xe_idx >= self.Ndict] = self.Ndict - 1  # impose error ceiling
        Xe_idx[Xe_idx < 0] = 0  # impose error floor

        return X_idx, Xe_idx
