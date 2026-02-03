from __future__ import annotations
import numpy as np
from numba import njit

@njit(cache=True)
def _sobel_reflect_jit(gray: np.ndarray) -> np.ndarray:
    """
    คำนวณ Sobel Magnitude แบบ Single-pass
    """
    rows, cols = gray.shape
    magnitude = np.zeros((rows, cols), dtype=np.float32)

    for y in range(rows):
        for x in range(cols):
            # --- Logic การสะท้อนขอบ ---
            # ถ้า index หลุดขอบซ้าย (-1) ให้ใช้ขอบซ้าย (0) แทน
            # ถ้า index หลุดขอบขวา (cols) ให้ใช้ขอบขวา (cols-1) แทน
            
            x_L = max(x - 1, 0)         # Left index
            x_R = min(x + 1, cols - 1)  # Right index
            y_T = max(y - 1, 0)         # Top index
            y_B = min(y + 1, rows - 1)  # Bottom index

            # 1. ดึงค่าจากตาราง 3x3 รอบจุด (y, x) โดยใช้พิกัดที่ปลอดภัย
            val_TL = gray[y_T, x_L]; val_T = gray[y_T, x]; val_TR = gray[y_T, x_R]
            val_L  = gray[y,   x_L];                       val_R  = gray[y,   x_R]
            val_BL = gray[y_B, x_L]; val_B = gray[y_B, x]; val_BR = gray[y_B, x_R]

            # 2. คำนวณ Gx (แนวนอน)
            # Kernel: [-1, 0, 1]
            gx = (val_TR + 2*val_R + val_BR) - (val_TL + 2*val_L + val_BL)

            # 3. คำนวณ Gy (แนวตั้ง)
            # Kernel: [-1, -2, -1] (Transpose)
            gy = (val_BL + 2*val_B + val_BR) - (val_TL + 2*val_T + val_TR)

            # 4. รวมร่าง Magnitude (Hypot)
            magnitude[y, x] = np.sqrt(gx**2 + gy**2)

    return magnitude

def compute_normalized_sobel(gray: np.ndarray) -> np.ndarray:
    """
    Compute Sobel gradient magnitude and normalize to [0, 1].
    Optimized version with Numba (maintains 'reflect' border behavior).
    """
    if gray.ndim != 2:
        raise ValueError("gray must be 2D")

    # 1. เรียกใช้ JIT Function (เร็ว + ประหยัดแรม)
    mag = _sobel_reflect_jit(gray)

    # 2. Normalize
    mag_min = float(mag.min())
    mag_max = float(mag.max())
    denom = (mag_max - mag_min)
    if denom == 0:
        denom = 1.0
        
    grad_norm = (mag - mag_min) / denom
    
    return grad_norm.astype(np.float32)