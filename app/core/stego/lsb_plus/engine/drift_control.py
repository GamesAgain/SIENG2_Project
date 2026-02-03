from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from numba import njit

from app.core.stego.lsb_plus.engine.util.metrics import _calc_hist_stats_jit, _to_gray_jit

# Import ฟังก์ชัน JIT จาก metrics.py (สมมติว่าอยู่ในระดับเดียวกันหรือแก้ path ตามจริง)


@dataclass
class BlockSafetyThresholds:
    max_hist_drift: float = 0.15
    max_var_ratio: float = 0.5
    max_chi_square: float = 5_000.0

# -----------------------------------------------------------------------------
# JIT Kernel: ส่วนประมวลผลความเร็วสูง
# -----------------------------------------------------------------------------
@njit(cache=True)
def _is_block_safe_jit(
    orig_block: np.ndarray,
    stego_block: np.ndarray,
    max_hd: float,
    max_vr: float,
    max_cs: float
) -> bool:
    """
    Core Logic: เช็คความปลอดภัยของ Block ในระดับ Machine Code
    """
    # 1. แปลงเป็น Gray (ถ้าเป็น RGB) - ใช้ฟังก์ชันที่แชร์กัน
    go = _to_gray_jit(orig_block)
    gs = _to_gray_jit(stego_block)

    # 2. Variance Ratio
    vo = np.var(go)
    vs = np.var(gs)
    
    vr = 0.0
    if vo >= 1e-6:
        vr = abs(vs - vo) / (vo + 1e-6)
    
    if vr > max_vr:
        return False

    # 3. Histogram-based Metrics (HD & CS)
    # ใช้ค่า Gray ที่เป็น uint8 เพื่อทำ Histogram
    go_u8 = go.astype(np.uint8)
    gs_u8 = gs.astype(np.uint8)
    
    # คำนวณ HD และ CS ในรอบเดียว (Single-pass)
    hd, cs = _calc_hist_stats_jit(go_u8, gs_u8, density=True)
    
    # เช็คเงื่อนไขที่เหลือ
    if hd > max_hd:
        return False
        
    # สำหรับ Chi-Square ในโหมด density=True ค่าจะถูก scale 
    # เราจะคำนวณแบบดิบ (Raw) อีกครั้งถ้าจำเป็น หรือปรับจูนที่ตัวเลข CS
    # ในที่นี้เพื่อให้ตรง 100% เราจะเรียกแบบ density=False สำหรับ CS
    _, cs_raw = _calc_hist_stats_jit(go_u8, gs_u8, density=False)
    
    if cs_raw > max_cs:
        return False

    return True

# -----------------------------------------------------------------------------
# Wrapper Function: ส่วนติดต่อกับโค้ดเดิม
# -----------------------------------------------------------------------------
def is_block_safe(
    original_block: np.ndarray,
    stego_block: np.ndarray,
    thresholds: BlockSafetyThresholds,
) -> bool:
    """
    Optimized version of is_block_safe.
    Maintains 100% identical logic to the original.
    """
    # Numba ไม่รองรับการส่ง Dataclass เข้าไปโดยตรง 
    # เราจึงต้องดึงค่าตัวเลข (Floats) ออกมาส่งให้ Jิต
    return _is_block_safe_jit(
        original_block,
        stego_block,
        thresholds.max_hist_drift,
        thresholds.max_var_ratio,
        thresholds.max_chi_square
    )