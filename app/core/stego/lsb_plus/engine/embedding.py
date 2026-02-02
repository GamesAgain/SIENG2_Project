from __future__ import annotations

from typing import List
import numpy as np
from tqdm import tqdm


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
    """
    Core low-level embedding loop.
    """

    h, w, _ = rgb.shape
    flat = rgb.reshape(-1, 3)

    # --- Preprocessing ---
    bits_arr = (
        np.asarray(bits, dtype=np.uint8)
        if not isinstance(bits, np.ndarray)
        else bits.astype(np.uint8, copy=False)
    )
    total_bits: int = int(bits_arr.size)
    bit_pos: int = 0

    channels = (2, 1, 0)  # B, G, R

    # Pre-calc coordinates for order
    y_coords = order // w
    x_coords = order % w

    # Block geometry
    block_cols: int = (w + 7) // 8

    # Track pending changes per block
    pending_changes: dict[int, list[tuple[int, np.ndarray]]] = {}

    # Mark last position of each block in order (O(1) check)
    is_last_pos = np.zeros(order.size, dtype=bool)
    for positions in block_pixel_positions.values():
        if positions.size:
            is_last_pos[int(positions[-1])] = True

    # --- Main loop ---
    for pos in tqdm(range(order.size), desc="Embedding", unit="px", disable=True):
        if bit_pos >= total_bits:
            break

        flat_idx: int = int(order[pos])
        block_id: int = int(block_map[flat_idx])

        if block_done[block_id]:
            continue

        requested_cap: int = int(capacity_flat[flat_idx])
        if requested_cap <= 0:
            continue

        y: int = int(y_coords[pos])
        x: int = int(x_coords[pos])
        cap: int = int(adjust_capacity_fn(gray_for_coords, y, x, requested_cap))
        if cap <= 0:
            continue

        old_pixel = flat[flat_idx].copy()
        changed = False

        for ch in channels:
            if bit_pos >= total_bits or cap <= 0:
                break

            v: int = int(flat[flat_idx, ch])
            new_v: int = (v & 0xFE) | int(bits_arr[bit_pos] & 1)

            if new_v != v:
                flat[flat_idx, ch] = new_v
                changed = True

            bit_pos += 1
            cap -= 1

        if changed:
            pending_changes.setdefault(block_id, []).append((flat_idx, old_pixel))

        # --- Block safety check ---
        if is_last_pos[pos] or bit_pos >= total_bits:
            changes = pending_changes.get(block_id)
            if changes:
                row: int = block_id // block_cols
                col: int = block_id % block_cols

                y0: int = row * 8
                x0: int = col * 8
                y1: int = min(h, y0 + 8)
                x1: int = min(w, x0 + 8)

                stego_block = rgb[y0:y1, x0:x1].copy()
                original_block = stego_block.copy()

                for idx, old_pix in changes:
                    yy: int = idx // w
                    xx: int = idx % w
                    original_block[yy - y0, xx - x0] = old_pix

                if not block_safety_checker(original_block, stego_block):
                    for idx, old_pix in changes:
                        flat[idx] = old_pix
                    block_done[block_id] = True

            pending_changes.pop(block_id, None)

    # --- Final check ---
    if bit_pos < total_bits:
        raise RuntimeError(
            f"Not enough safe capacity: embedded {bit_pos}/{total_bits} bits "
            f"({bit_pos / total_bits * 100:.1f}%)"
        )

    return rgb
