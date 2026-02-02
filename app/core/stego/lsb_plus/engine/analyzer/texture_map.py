from __future__ import annotations

import numpy as np

from .gradient import compute_normalized_sobel
from .entropy import compute_local_entropy


def compute_texture_features(rgb: np.ndarray):
    """
    Compute texture-related maps:

    - gray image (float32, 0..255)
    - normalized Sobel gradient
    - normalized local entropy
    - surface score map = 0.6 * grad + 0.4 * entropy

    Before analysis, all LSB bits are zeroed out to make analyzer
    invariant between cover and stego images (only LSBs are modified).
    """
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be HxWx3 array")

    # zero-out LSBs so analysis is invariant to our embedding
    rgb_even = (rgb & 0xFE).astype(np.float32)

    r = rgb_even[:, :, 0]
    g = rgb_even[:, :, 1]
    b = rgb_even[:, :, 2]

    gray = 0.299 * r + 0.587 * g + 0.114 * b

    grad_norm = compute_normalized_sobel(gray)
    entropy_norm = compute_local_entropy(gray, window_size=5)

    surface = 0.6 * grad_norm + 0.4 * entropy_norm
    surface = np.clip(surface, 0.0, 1.0)

    return gray.astype(np.float32), grad_norm, entropy_norm, surface
