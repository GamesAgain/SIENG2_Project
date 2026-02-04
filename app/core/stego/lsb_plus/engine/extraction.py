from __future__ import annotations
from typing import List
import numpy as np
from numba import njit

@njit(cache=True)
def extract_bits_low_level(
    rgb: np.ndarray,
    order: np.ndarray,
    capacity_flat: np.ndarray,
) -> List[int]:
    """
    JIT-Optimized Extraction Loop
    """
    h, w, c = rgb.shape
    flat = rgb.reshape(-1, 3)
    bits = [] # Numba handles list efficiently in newer versions, or use array builder if strict
    
    # Pre-define channels
    channels = (2, 1, 0)
    
    for i in range(len(order)):
        flat_idx = order[i]
        cap = capacity_flat[flat_idx]
        
        if cap <= 0: continue
        
        for k in channels:
            if cap <= 0: break
            val = flat[flat_idx, k]
            bits.append(val & 1)
            cap -= 1
            
    return bits