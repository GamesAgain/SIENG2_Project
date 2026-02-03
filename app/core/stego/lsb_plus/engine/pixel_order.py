from __future__ import annotations
import hashlib
import numpy as np

def build_pixel_order(entropy_map: np.ndarray, seed: str) -> np.ndarray:
    """
    Optimized Pixel Ordering:
    1) Flatten entropy map (Zero-copy)
    2) Sort indices by entropy descending (Fast NumPy Sort)
    3) Shuffle with NumPy PRNG (In-place Machine Code Shuffle)
    """
    # 1. ตรวจสอบขนาด Input
    if entropy_map.ndim != 2:
        raise ValueError("entropy_map must be 2D")

    # 2. Flatten แบบ View (เร็วและไม่กิน RAM เพิ่ม)
    flat_entropy = entropy_map.ravel()

    # 3. เรียงลำดับ (Sort) ด้วย NumPy 
    # ใช้ [::-1] เพื่อกลับด้านให้เป็น "มาก -> น้อย"
    sorted_idx = np.argsort(flat_entropy)[::-1]

    # 4. สร้าง RNG จาก Seed (ใช้ NumPy Generator แทน Python Random)
    # 4.1 Hash Seed เป็นตัวเลข
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    seed_int = int.from_bytes(h[:8], "big") # ใช้ 64-bit seed พอสำหรับ NumPy
    
    # 4.2 สร้าง Generator (PCG64) ที่เร็วมาก
    rng = np.random.default_rng(seed_int)
    
    # 5. สลับตำแหน่ง (Shuffle) บน Memory โดยตรง
    # ขั้นตอนนี้เร็วกว่าเดิมมาก เพราะไม่ต้องแปลงเป็น List
    rng.shuffle(sorted_idx)

    # คืนค่าเป็น int64
    return sorted_idx.astype(np.int64, copy=False)