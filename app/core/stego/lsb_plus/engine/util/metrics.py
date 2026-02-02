from __future__ import annotations

import numpy as np
from scipy import ndimage


def _to_float_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3 and img.shape[2] == 3:
        r = img[:, :, 0].astype(np.float32)
        g = img[:, :, 1].astype(np.float32)
        b = img[:, :, 2].astype(np.float32)
        gray = 0.299 * r + 0.587 * g + 0.114 * b
    elif img.ndim == 2:
        gray = img.astype(np.float32)
    else:
        raise ValueError("Invalid image dimensions for gray conversion.")
    return gray


def compute_psnr(orig: np.ndarray, stego: np.ndarray) -> float:
    orig = orig.astype(np.float32)
    stego = stego.astype(np.float32)
    mse = np.mean((orig - stego) ** 2)
    if mse <= 1e-12:
        return float("inf")
    max_i = 255.0
    psnr = 20.0 * np.log10(max_i) - 10.0 * np.log10(mse)
    return float(psnr)


def compute_ssim(orig: np.ndarray, stego: np.ndarray) -> float:
    """
    Single-scale SSIM implementation for grayscale images.
    """
    x = _to_float_gray(orig)
    y = _to_float_gray(stego)

    K1, K2 = 0.01, 0.03
    L = 255.0
    C1 = (K1 * L) ** 2
    C2 = (K2 * L) ** 2

    # Gaussian filter
    win = 11
    sigma = 1.5
    filt = np.zeros((win, win), dtype=np.float32)
    ax = np.arange(-win // 2 + 1.0, win // 2 + 1.0)
    xx, yy = np.meshgrid(ax, ax)
    filt = np.exp(-(xx**2 + yy**2) / (2.0 * sigma**2))
    filt /= filt.sum()

    mu_x = ndimage.convolve(x, filt, mode="reflect")
    mu_y = ndimage.convolve(y, filt, mode="reflect")

    mu_x2 = mu_x * mu_x
    mu_y2 = mu_y * mu_y
    mu_xy = mu_x * mu_y

    sigma_x2 = ndimage.convolve(x * x, filt, mode="reflect") - mu_x2
    sigma_y2 = ndimage.convolve(y * y, filt, mode="reflect") - mu_y2
    sigma_xy = ndimage.convolve(x * y, filt, mode="reflect") - mu_xy

    num1 = 2 * mu_xy + C1
    num2 = 2 * sigma_xy + C2
    den1 = mu_x2 + mu_y2 + C1
    den2 = sigma_x2 + sigma_y2 + C2

    ssim_map = (num1 * num2) / (den1 * den2 + 1e-12)
    return float(ssim_map.mean())


def histogram_drift(orig: np.ndarray, stego: np.ndarray) -> float:
    """
    Global histogram drift between two RGB images (L1 distance of normalized hist).
    """
    o = _to_float_gray(orig).astype(np.uint8).ravel()
    s = _to_float_gray(stego).astype(np.uint8).ravel()

    hist_o, _ = np.histogram(o, bins=256, range=(0, 255), density=True)
    hist_s, _ = np.histogram(s, bins=256, range=(0, 255), density=True)

    drift = np.sum(np.abs(hist_o - hist_s))
    return float(drift)


def histogram_drift_block(orig_block: np.ndarray, stego_block: np.ndarray) -> float:
    return histogram_drift(orig_block, stego_block)


def variance_ratio_block(orig_block: np.ndarray, stego_block: np.ndarray) -> float:
    go = _to_float_gray(orig_block)
    gs = _to_float_gray(stego_block)
    var_o = float(go.var())
    var_s = float(gs.var())
    if var_o < 1e-6:
        return 0.0
    return abs(var_s - var_o) / (var_o + 1e-6)


def chi_square_block(orig_block: np.ndarray, stego_block: np.ndarray) -> float:
    go = _to_float_gray(orig_block).astype(np.uint8).ravel()
    gs = _to_float_gray(stego_block).astype(np.uint8).ravel()
    hist_o, _ = np.histogram(go, bins=256, range=(0, 255))
    hist_s, _ = np.histogram(gs, bins=256, range=(0, 255))
    expected = hist_o + 1e-3
    diff = hist_s - hist_o
    chi_sq = np.sum((diff**2) / expected)
    return float(chi_sq)
