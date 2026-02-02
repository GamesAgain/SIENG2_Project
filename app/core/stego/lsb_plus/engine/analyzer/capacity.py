from __future__ import annotations

import numpy as np

def compute_capacity(surface_map: np.ndarray) -> np.ndarray:
        """
        Convert surface score [0,1] into capacity map (0..3 bits per pixel).

        Spec:
            Smooth (0–0.25)       → 0–1 bits
            Texture (0.26–0.65)   → 2 bits
            Edge (0.66–1.0)       → 3 bits

        Implementation:
            [0.00, 0.15] → 0 bits
            (0.15, 0.25] → 1 bit
            (0.25, 0.65] → 2 bits
            (0.65, 1.00] → 3 bits
        """
        if surface_map.ndim != 2:
            raise ValueError("surface_map must be 2D")

        s = surface_map.astype(np.float32)
        cap = np.zeros_like(s, dtype=np.uint8)

        cap[(s > 0.15) & (s <= 0.25)] = 1
        cap[(s > 0.25) & (s <= 0.65)] = 2
        cap[s > 0.65] = 3

        return cap