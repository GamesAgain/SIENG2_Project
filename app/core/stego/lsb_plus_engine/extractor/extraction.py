from __future__ import annotations

from typing import List

import numpy as np


def extract_bits_low_level(
    rgb: np.ndarray,
    order: np.ndarray,
    capacity_flat: np.ndarray,
) -> List[int]:
    """
    Reverse of embedding: read LSBs in the same order/capacity.
    Reads *all* available bits, excess bits may be ignored later
    when parsing header+payload.
    """
    h, w, _ = rgb.shape
    flat = rgb.reshape(-1, 3)
    bits: List[int] = []
    channels = (2, 1, 0)  # B, G, R

    for flat_idx in order:
        cap = int(capacity_flat[int(flat_idx)])
        if cap <= 0:
            continue
        for ch in channels:
            if cap <= 0:
                break
            v = int(flat[int(flat_idx), ch])
            bits.append(v & 1)
            cap -= 1

    return bits
