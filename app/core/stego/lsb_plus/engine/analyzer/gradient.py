from __future__ import annotations

import numpy as np
from scipy import ndimage


def compute_normalized_sobel(gray: np.ndarray) -> np.ndarray:
    """
    Compute Sobel gradient magnitude and normalize to [0, 1].

    Parameters
    ----------
    gray : np.ndarray
        2D grayscale image, float32 or float64.

    Returns
    -------
    grad_norm : np.ndarray
        2D float32 array in [0, 1].
    """
    if gray.ndim != 2:
        raise ValueError("gray must be 2D")

    gx = ndimage.sobel(gray, axis=1, mode="reflect")
    gy = ndimage.sobel(gray, axis=0, mode="reflect")
    mag = np.hypot(gx, gy)

    mag = mag.astype(np.float32)
    mag_min = float(mag.min())
    mag_max = float(mag.max())
    denom = (mag_max - mag_min) or 1.0
    grad_norm = (mag - mag_min) / denom
    return grad_norm.astype(np.float32)
