from __future__ import annotations
import numpy as np
from numba import njit

from .gradient import compute_normalized_sobel
from .entropy import compute_local_entropy

@njit(cache=True)
def _preprocess_image(rgb: np.ndarray) -> np.ndarray:
    """
    ฟังก์ชันช่วย (Helper): ทำงานแบบ Single-pass
    1. Zero-out LSB (rgb & 0xFE)
    2. คำนวณ Grayscale (BT.601)
    """
    rows, cols, channels = rgb.shape
    gray = np.zeros((rows, cols), dtype=np.float32)

    for row in range(rows):
        for col in range(cols):
            # 1. ดึงค่าสีและเคลียร์ LSB ทันที
            r = rgb[row, col, 0] & 0xFE
            g = rgb[row, col, 1] & 0xFE
            b = rgb[row, col, 2] & 0xFE
            
            # 2.แปลงเป็นภาพขาวดำ (Grayscale Conversion)
            # ใช้สูตรมาตรฐาน ITU-R BT.601 (Luma Transform) ในการคำนวณความสว่าง
            # สูตรนี้ถ่วงน้ำหนักตาม Human Eye Sensitivity
            # - สีเขียว (59%): ตาไวต่อแสงนี้มากที่สุด จึงมีผลต่อความสว่างมากที่สุด
            # - สีแดง (30%) และ สีน้ำเงิน (11%): มีผลรองลงมา
            gray[row, col] = 0.299 * r + 0.587 * g + 0.114 * b
            
    return gray

# -------------------------------------------------------------------------
# ฟังก์ชันหลัก
# -------------------------------------------------------------------------
def compute_texture_features(rgb: np.ndarray):
    """
    Computes texture feature maps for adaptive capacity estimation.
    Includes optimization for memory usage and speed.
    """
    
    # 1. Validation: ตรวจสอบขนาดภาพ
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be Height * Width * 3 array")

    # 2. Preprocessing (Optimized):
    gray = _preprocess_image(rgb)

    # 3. Feature Extraction: คำนวณขอบ (Gradient) และความยุ่งเหยิง (Entropy)
    grad_norm = compute_normalized_sobel(gray)
    entropy_norm = compute_local_entropy(gray, window_size=5)

    # 4. Score Calculation: รวมคะแนน
    # ให้ความสำคัญกับขอบภาพ (0.6) มากกว่า Noise (0.4)
    surface = 0.6 * grad_norm + 0.4 * entropy_norm
    
    # Clip ค่าให้อยู่ในช่วง 0.0 - 1.0 เสมอ
    surface = np.clip(surface, 0.0, 1.0)

    return gray, grad_norm, entropy_norm, surface