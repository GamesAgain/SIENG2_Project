from __future__ import annotations

import numpy as np


def adjust_capacity_for_pixel(
    gray: np.ndarray,
    y: int,
    x: int,
    requested_bits: int,
) -> int:
    """
    Predictive noise correction.

    - Compute mean of 8 neighbors around (y, x) in gray image
    - If current pixel already far from neighbor mean, allow more bits
    - If it is very smooth area, reduce capacity to avoid visible noise

    This is a heuristic but fully functional.
    """
    if requested_bits <= 0:
        return 0
    if gray.ndim != 2:
        raise ValueError("gray must be 2D")

    h, w = gray.shape
    if not (0 <= y < h and 0 <= x < w):
        return 0

    y0 = max(0, y - 1)
    y1 = min(h, y + 2)
    x0 = max(0, x - 1)
    x1 = min(w, x + 2)

    block = gray[y0:y1, x0:x1]
    if block.size <= 1:
        return min(1, requested_bits)

    # exclude center if possible
    block_flat = block.ravel()
    center_val = gray[y, x]
    if block_flat.size > 1:
        neighbors = block_flat.copy()
        neighbors[neighbors == center_val][:1] = center_val  # keep one center
        mean_neighbors = neighbors.mean()
        std_neighbors = neighbors.std()
    else:
        mean_neighbors = float(center_val)
        std_neighbors = 0.0

    diff = abs(float(center_val) - float(mean_neighbors))

    # very flat + small std → reduce bits
    if std_neighbors < 5.0 and diff < 5.0:
        return min(requested_bits, 1)

    # moderately flat → allow at most 2 bits
    if std_neighbors < 10.0 and diff < 10.0:
        return min(requested_bits, 2)

    # otherwise keep requested bits
    return requested_bits
