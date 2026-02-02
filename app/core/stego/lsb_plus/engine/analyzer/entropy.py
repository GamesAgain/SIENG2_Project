from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def compute_local_entropy(gray: np.ndarray, window_size: int = 5) -> np.ndarray:
    """
    Compute local entropy for each pixel based on a sliding window.

    Parameters
    ----------
    gray : np.ndarray
        2D grayscale image, values in [0, 255].
    window_size : int
        Size of the square window (odd), default=5.

    Returns
    -------
    entropy_map : np.ndarray
        2D array of entropy values normalized to [0, 1].
    """
    if gray.ndim != 2:
        raise ValueError("gray must be 2D")

    if window_size % 2 == 0 or window_size < 3:
        raise ValueError("window_size must be odd and >= 3")

    gray_u8 = np.clip(gray, 0, 255).astype(np.uint8)

    pad = window_size // 2
    padded = np.pad(gray_u8, pad_width=pad, mode="reflect")

    windows = sliding_window_view(padded, (window_size, window_size))
    H, W = windows.shape[:2]
    entropy_map = np.zeros((H, W), dtype=np.float32)

    # loop: simple but clear; window is small
    for i in range(H):
        row = windows[i]
        for j in range(W):
            block = row[j].ravel()
            hist = np.bincount(block, minlength=256).astype(np.float32)
            total = hist.sum()
            if total <= 0:
                continue
            p = hist / total
            p_nonzero = p[p > 0]
            entropy = -np.sum(p_nonzero * np.log2(p_nonzero))
            # max entropy for 8-bit is log2(256) = 8
            entropy_map[i, j] = entropy / 8.0

    # entropy_map already 0..1 but clamp
    np.clip(entropy_map, 0.0, 1.0, out=entropy_map)
    return entropy_map
