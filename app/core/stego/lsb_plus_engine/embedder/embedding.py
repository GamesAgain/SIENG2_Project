from __future__ import annotations

from typing import List

import numpy as np

from app.utils.exceptions import StegoEngineError




def embed_in_lsb(
    rgb: np.ndarray,
    order: np.ndarray,
    capacity_flat: np.ndarray,
    bits: List[int],
    block_map: np.ndarray,
    block_done: np.ndarray,
    block_pixel_positions: dict[int, list[int]],
    gray_for_coords: np.ndarray,
    adjust_capacity_fn,
    block_safety_checker,
):
    """
    Core embedding loop.

    Parameters
    ----------
    rgb : np.ndarray
        Original image, modified in-place.
    order : np.ndarray
        Pixel order (flat indices).
    capacity_flat : np.ndarray
        Requested capacity per pixel (0..3), flattened.
    bits : list[int]
        Bitstream to embed.
    block_map : np.ndarray
        1D array, same length as number of pixels, mapping flat index -> block_id.
    block_done : np.ndarray
        Boolean (or int) array marking blocks that must be skipped (unsafe).
    block_pixel_positions : dict
        block_id -> sorted list of positions in "order" belonging to that block.
    gray_for_coords : np.ndarray
        2D gray map used by predictive noise correction.
    adjust_capacity_fn :
        Function (gray, y, x, capacity) -> adjusted capacity.
    block_safety_checker :
        Callable(original_block, stego_block) -> bool
    """
    h, w, _ = rgb.shape
    flat = rgb.reshape(-1, 3)

    total_bits = len(bits)
    bit_pos = 0
    channels = (2, 1, 0)  # B, G, R

    # track per-block modifications for rollback
    pending_changes: dict[int, list[tuple[int, np.ndarray]]] = {}

    # For quick check of last position per block
    last_pos_per_block = {
        b_id: positions[-1] for b_id, positions in block_pixel_positions.items()
    }

    from tqdm import tqdm

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

        y = flat_idx // w
        x = flat_idx % w
        cap = adjust_capacity_fn(gray_for_coords, y, x, requested_cap)
        if cap <= 0:
            continue

        old_pixel = flat[flat_idx].copy()
        changed = False

        for ch in channels:
            if bit_pos >= total_bits or cap <= 0:
                break
            v = int(flat[flat_idx, ch])
            new_v = (v & 0xFE) | (bits[bit_pos] & 1)
            if new_v != v:
                flat[flat_idx, ch] = new_v
                changed = True
            bit_pos += 1
            cap -= 1

        if changed:
            pending_changes.setdefault(block_id, []).append((flat_idx, old_pixel))

        # if this was the last pixel in this block (in global order),
        # evaluate block safety and rollback if necessary
        if pos == last_pos_per_block.get(block_id, -1) or bit_pos >= total_bits:
            if pending_changes.get(block_id):
                # build original & stego blocks
                block_pixels = [idx for idx, _ in pending_changes[block_id]]
                ys = [idx // w for idx in block_pixels]
                xs = [idx % w for idx in block_pixels]
                y0 = max(0, min(ys) // 8 * 8)
                x0 = max(0, min(xs) // 8 * 8)
                y1 = min(h, y0 + 8)
                x1 = min(w, x0 + 8)

                # slice blocks
                original_block = np.zeros((y1 - y0, x1 - x0, 3), dtype=np.uint8)
                stego_block = np.zeros_like(original_block)
                # reconstruct original from current stego and pending_changes
                stego_block[:] = rgb[y0:y1, x0:x1]
                original_block[:] = stego_block
                for idx, old_pix in pending_changes[block_id]:
                    yy = idx // w
                    xx = idx % w
                    if y0 <= yy < y1 and x0 <= xx < x1:
                        original_block[yy - y0, xx - x0] = old_pix

                if not block_safety_checker(original_block, stego_block):
                    # rollback
                    for idx, old_pix in pending_changes[block_id]:
                        flat[idx] = old_pix
                    block_done[block_id] = True

            # clear changes for this block (applied or rolled back)
            pending_changes.pop(block_id, None)

    if bit_pos < total_bits:
        raise StegoEngineError(
            f"Not enough safe capacity to embed payload. "
            f"Embedded bits: {bit_pos}/{total_bits}"
        )

    return rgb
