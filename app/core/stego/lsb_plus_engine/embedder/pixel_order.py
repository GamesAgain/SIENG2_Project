from __future__ import annotations

import numpy as np

from app.core.stego.lsb_plus_engine.lsb_utils.prng import rng_from_seed




def build_pixel_order(entropy_map: np.ndarray, seed: str) -> np.ndarray:
    """
    Build pixel ordering:

    1) Flatten entropy map
    2) Sort indices by entropy descending
    3) Shuffle with deterministic PRNG derived from seed
    """
    if entropy_map.ndim != 2:
        raise ValueError("entropy_map must be 2D")

    h, w = entropy_map.shape
    flat_entropy = entropy_map.reshape(-1).astype(np.float32)
    indices = np.arange(flat_entropy.size, dtype=np.int64)

    sorted_idx = np.argsort(-flat_entropy)  # highest entropy first
    sorted_list = sorted_idx.tolist()

    rng = rng_from_seed(seed)
    rng.shuffle(sorted_list)

    return np.array(sorted_list, dtype=np.int64)
