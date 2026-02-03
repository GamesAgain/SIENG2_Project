from __future__ import annotations

import numpy as np
from numba import njit

@njit(cache=True)
def _compute_entropy_jit(
    padded_gray: np.ndarray, 
    h: int, 
    w: int, 
    window_size: int, 
    entropy_lookup: np.ndarray
) -> np.ndarray:
    """
    JIT Kernel: คำนวณ Entropy อย่างรวดเร็ว
    โดยใช้ค่าจากตาราง (entropy_lookup) แทนการคำนวณ log2 สดๆ
    เพื่อรักษาความแม่นยำให้ตรงกับ NumPy ต้นฉบับ
    """
    entropy_map = np.zeros((h, w), dtype=np.float32)
    
    # จอง Memory สำหรับ Histogram ครั้งเดียวแล้วใช้ซ้ำ (เร็วกว่าสร้างใหม่ทุกรอบ)
    hist = np.zeros(256, dtype=np.int32)
    
    # วนลูปทุกพิกเซล (ส่วนที่เป็นคอขวดเดิม)
    for i in range(h):
        for j in range(w):
            # 1. Reset Histogram
            hist[:] = 0
            
            # 2. นับความถี่สีในหน้าต่าง (Window Scanning)
            # padded index: i -> i+wy, j -> j+wx
            for wy in range(window_size):
                for wx in range(window_size):
                    val = padded_gray[i + wy, j + wx]
                    hist[val] += 1
            
            # 3. คำนวณ Entropy โดยใช้ Lookup Table
            # (ดึงค่าที่คำนวณไว้แล้วมาบวกกัน แทนการคำนวณใหม่)
            ent_sum = 0.0
            for k in range(256):
                count = hist[k]
                if count > 0:
                    ent_sum += entropy_lookup[count]
            
            # 4. หาร 8.0 ตาม Logic เดิม
            entropy_map[i, j] = ent_sum / 8.0

    return entropy_map


def compute_local_entropy(gray: np.ndarray, window_size: int = 5) -> np.ndarray:
    """
    Compute local entropy for each pixel based on a sliding window.
    
    Optimization Strategy:
    - Pre-calculate all possible entropy terms using NumPy (Lookup Table) to match precision.
    - Use Numba JIT for high-speed iteration and histogram building.
    """
    if gray.ndim != 2:
        raise ValueError("gray must be 2D")

    if window_size % 2 == 0 or window_size < 3:
        raise ValueError("window_size must be odd and >= 3")

    # 1. Prepare Padded Image (Logic เดิม)
    gray_u8 = np.clip(gray, 0, 255).astype(np.uint8)
    
    pad = window_size // 2
    padded = np.pad(gray_u8, pad_width=pad, mode="reflect")
    
    h, w = gray.shape

    # -------------------------------------------------------------------------
    # 2. สร้าง Lookup Table (หัวใจสำคัญของการแก้ปัญหา)
    # -------------------------------------------------------------------------
    # ในหน้าต่างขนาดคงที่ (เช่น 5x5=25) ค่าความถี่ (Count) ของแต่ละสี
    # จะมีค่าได้ตั้งแต่ 0 ถึง 25 เท่านั้น เราจึงคำนวณค่าเทอมของ Entropy ไว้ก่อนได้เลย
    
    area = float(window_size * window_size)
    
    # สร้าง Array ที่ index คือจำนวนนับ (0..25)
    counts = np.arange(int(area) + 1, dtype=np.float32)
    
    # คำนวณความน่าจะเป็น p = count / area
    p = counts / area
    
    # คำนวณเทอม -p * log2(p) ด้วย NumPy (เพื่อให้ทศนิยมตรงกับ Code เดิม 100%)
    # กรณี count=0 จะได้ log2(0) ซึ่งเป็น -inf เราต้องจัดการให้เป็น 0
    lookup_table = np.zeros_like(counts)
    
    # คำนวณเฉพาะจุดที่ count > 0
    valid_mask = counts > 0
    # สูตร: - (p * log2(p))
    lookup_table[valid_mask] = - (p[valid_mask] * np.log2(p[valid_mask]))
    
    # -------------------------------------------------------------------------
    # 3. ส่งเข้า JIT Kernel
    # -------------------------------------------------------------------------
    entropy_map = _compute_entropy_jit(padded, h, w, window_size, lookup_table)
    
    # 4. Clamp Result (Logic เดิม)
    return np.clip(entropy_map, 0.0, 1.0)