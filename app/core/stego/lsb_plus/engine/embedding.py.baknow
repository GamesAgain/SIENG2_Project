from __future__ import annotations
from typing import List
import numpy as np
from numba import njit
from tqdm import tqdm

@njit(cache=True)
def _bitwise_lsb(val: int, bit: int) -> int:
    """คำนวณค่า LSB"""
    return (val & 0xFE) | (bit & 0x01)

def embed_bits_low_level(
    rgb: np.ndarray,
    order: np.ndarray,
    capacity_flat: np.ndarray,
    bits: List[int] | np.ndarray,
    block_map: np.ndarray,
    block_done: np.ndarray,
    block_pixel_positions: dict[int, np.ndarray],
    gray_for_coords: np.ndarray,
    adjust_capacity_fn,
    block_safety_checker,
):

    h, w, _ = rgb.shape
    # ใช้ View 1D เพื่อความเร็ว (Zero-copy)
    flat = rgb.reshape(-1, 3)

    # แปลง bits เป็น numpy array
    bits_arr = np.asarray(bits, dtype=np.uint8)
    total_bits = int(bits_arr.size)
    bit_pos = 0

    channels = (2, 1, 0)  # B, G, R
    block_cols = (w + 7) // 8

    # Pre-calculate Mask
    is_last_pos = np.zeros(order.size, dtype=bool)
    for positions in block_pixel_positions.values():
        if positions.size > 0:
            is_last_pos[int(positions[-1])] = True

    # Dictionary เก็บ Undo Log 
    pending_changes = {}

    # --- Main Loop ---
    for pos in tqdm(range(order.size), desc="Embedding", unit="px", disable=True):
        if bit_pos >= total_bits:
            break

        flat_idx = int(order[pos])
        block_id = int(block_map[flat_idx])

        if block_done[block_id]:
            continue

        requested_cap = int(capacity_flat[flat_idx])
        if requested_cap <= 0:
            continue

        y, x = divmod(flat_idx, w)
        
        cap = int(adjust_capacity_fn(gray_for_coords, y, x, requested_cap))
        if cap <= 0:
            continue

        current_val_ref = flat[flat_idx]
        old_pixel_tuple = (current_val_ref[0], current_val_ref[1], current_val_ref[2])
        
        changed = False

        for ch in channels:
            if bit_pos >= total_bits or cap <= 0:
                break

            orig_v = current_val_ref[ch]
            new_v = _bitwise_lsb(int(orig_v), int(bits_arr[bit_pos]))

            if new_v != orig_v:
                flat[flat_idx, ch] = new_v
                changed = True

            bit_pos += 1
            cap -= 1

        if changed:
            # เก็บลง Dict
            # ข้อมูลใน List คือ (index, (r,g,b))
            pending_changes.setdefault(block_id, []).append((flat_idx, old_pixel_tuple))

        # --- Block Safety Check ---
        if is_last_pos[pos] or bit_pos >= total_bits:
            changes = pending_changes.get(block_id)
            if changes:
                row, col = divmod(block_id, block_cols)
                y0, x0 = row * 8, col * 8
                y1, x1 = min(h, y0 + 8), min(w, x0 + 8)

                stego_block = rgb[y0:y1, x0:x1]
                original_block = stego_block.copy()

                for idx, old_vals in changes:
                    py, px = divmod(idx, w)
                    original_block[py - y0, px - x0] = old_vals

                if not block_safety_checker(original_block, stego_block):
                    # Rollback
                    for idx, old_vals in changes:
                        flat[idx] = old_vals
                    block_done[block_id] = True

            pending_changes.pop(block_id, None)

    if bit_pos < total_bits:
        raise RuntimeError(f"Capacity Fail: {bit_pos}/{total_bits}")

    return rgb