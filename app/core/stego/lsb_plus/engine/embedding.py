from __future__ import annotations
from typing import List, Union, Any
import numpy as np
from numba import njit
# ตัด tqdm ออกเพื่อให้ทำงานแบบ Silent/Fastest หรือจะใส่กลับมาก็ได้ถ้าต้องการ Progress Bar
# แต่ใน LSBPP เรามี callback update แยกต่างหากที่ชั้นบนอยู่แล้ว

@njit(cache=True)
def _bitwise_lsb(val: int, bit: int) -> int:
    """คำนวณค่า LSB: เปลี่ยนบิตสุดท้ายของ val ให้เป็น bit"""
    return (val & 0xFE) | (bit & 0x01)

def embed_bits_low_level(
    rgb: np.ndarray,
    order: np.ndarray,
    capacity_flat: np.ndarray,
    bits: Union[List[int], np.ndarray],
    block_map: np.ndarray,      # Unused in optimized version (legacy compatible)
    block_done: np.ndarray,     # Unused in optimized version (legacy compatible)
    block_pixel_positions: Any, # Unused in optimized version (legacy compatible)
    gray_for_coords: Any,       # Unused in optimized version (legacy compatible)
    adjust_capacity_fn: Any,    # Unused: ตัดออกเพื่อให้ Sync กับ Extractor
    block_safety_checker: Any,  # Unused: ตัด Rollback ทิ้งเพื่อรักษา Data Integrity
) -> np.ndarray:
    """
    Optimized Low-Level Embedding Function
    
    การแก้ไขปัญหา (Fixes):
    1. SYNC FIX: ใช้ 'capacity_flat' โดยตรง ไม่คำนวณ adjust_capacity ซ้ำ
       (เพื่อให้ Logic ตรงกับไฟล์ extraction.py 100% ป้องกัน Ciphertext truncated)
    2. DATA INTEGRITY: ตัดระบบ Rollback ทิ้ง เพื่อรับประกันว่าบิตถูกเขียนลงไปจริงๆ
       (ป้องกันข้อมูลแหว่งหายกลางทาง)
    3. SPEED UP: ตัด Dictionary Overhead และ Vectorize การทำงาน
    """

    # 1. เตรียมข้อมูล
    h, w, _ = rgb.shape
    # ใช้ View 1D เพื่อความเร็ว (Zero-copy) และแก้ไขค่าใน rgb ต้นฉบับได้เลย
    flat = rgb.reshape(-1, 3)

    # แปลง bits เป็น numpy array เพื่อการเข้าถึงที่รวดเร็ว
    bits_arr = np.asarray(bits, dtype=np.uint8)
    total_bits = int(bits_arr.size)
    bit_pos = 0

    channels = (2, 1, 0)  # ลำดับการฝัง: Blue -> Green -> Red
    
    # จำนวนพิกเซลทั้งหมดที่จะวิ่งผ่าน
    num_pixels = order.size

    # 2. Main Loop: วนลูปตามลำดับ Pixel Order
    for i in range(num_pixels):
        # เงื่อนไขหยุด: ฝังข้อมูลครบทุกบิตแล้ว
        if bit_pos >= total_bits:
            break

        flat_idx = int(order[i])
        
        # [CRITICAL FIX] ใช้ความจุจาก Map โดยตรง (Pre-calculated)
        # เดิม: cap = adjust_capacity_fn(...) -> ทำให้ค่าไม่ตรงกับตอนถอดรหัส
        # ใหม่: cap = capacity_flat[...] -> ตรงกับ Extractor เป๊ะๆ
        cap = int(capacity_flat[flat_idx])
        
        # ข้ามพิกเซลที่ไม่มีความจุ (ตามที่วิเคราะห์มาแล้ว)
        if cap <= 0:
            continue
            
        current_val_ref = flat[flat_idx]

        # 3. ฝังข้อมูลลงแต่ละ Channel (B, G, R)
        for ch in channels:
            # หยุดถ้าข้อมูลหมด หรือความจุของพิกเซลนี้หมด
            if bit_pos >= total_bits or cap <= 0:
                break

            orig_v = int(current_val_ref[ch])
            bit_to_embed = int(bits_arr[bit_pos])
            
            # คำนวณและอัปเดตค่าสี
            new_v = _bitwise_lsb(orig_v, bit_to_embed)

            if new_v != orig_v:
                flat[flat_idx, ch] = new_v

            bit_pos += 1
            cap -= 1
            
    # 4. Final Verification (ตรวจสอบความสมบูรณ์)
    if bit_pos < total_bits:
        missing = total_bits - bit_pos
        raise RuntimeError(
            f"Insufficient Capacity Error: \n"
            f"Image is too small or payload is too large.\n"
            f"Missing {missing} bits. (Embedded: {bit_pos}/{total_bits})"
        )

    return rgb

@njit(cache=False) 
def calculate_exact_capacity(
    order: np.ndarray,
    capacity_flat: np.ndarray,
    gray_for_coords: np.ndarray,
    adjust_capacity_fn,
    width: int
) -> int:
    """
    Simulation Loop: นับบิตแบบดิบๆ (Raw Sum) เพื่อให้ตรงกับ Engine ที่สุด
    """
    total_bits = 0
    num_pixels = order.size

    for i in range(num_pixels):
        flat_idx = int(order[i])
        
        # [SYNC FIX] เอาค่าดิบมาเลย ไม่ต้องหักอะไรทั้งนั้น
        cap = int(capacity_flat[flat_idx]) 
        
        if cap > 0:
            total_bits += cap

    return total_bits