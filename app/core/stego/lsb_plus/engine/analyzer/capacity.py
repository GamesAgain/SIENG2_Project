from __future__ import annotations
import numpy as np
from numba import njit

@njit(cache=True)
def _compute_capacity_jit(surface_map: np.ndarray) -> np.ndarray:
    rows, cols = surface_map.shape
    # สร้างตาราง2มิติที่มีแต่ 0
    cap = np.zeros((rows, cols), dtype=np.uint8)

    for y in range(rows):
        for x in range(cols):
            val = surface_map[y, x]
            
            # Spec:
            # > 0.65       -> 3 bits
            # 0.25 - 0.65  -> 2 bits
            # 0.15 - 0.25  -> 1 bit
            # <= 0.15      -> 0 bits (Default เป็น 0 อยู่แล้วจาก np.zeros)
            
            if val > 0.65:
                cap[y, x] = 3
            elif val > 0.25:
                cap[y, x] = 2
            elif val > 0.15:
                cap[y, x] = 1
            # else: เป็น 0 โดยอัตโนมัติ
            
    return cap

def compute_capacity(surface_map: np.ndarray) -> np.ndarray:
    """
    Convert surface score [0,1] into capacity map (0..3 bits per pixel).
    Optimized with Numba for single-pass processing.
    """
    if surface_map.ndim != 2:
        raise ValueError("surface_map must be 2D")
    
    return _compute_capacity_jit(surface_map)