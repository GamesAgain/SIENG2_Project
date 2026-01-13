from __future__ import annotations

import numpy as np

from app.core.stego.lsb_plus_engine.analyzer.region_classifier import compute_capacity_map



def compute_capacity(surface_map: np.ndarray) -> np.ndarray:
    """
    Thin wrapper around analyzer.region_classifier for clearer API.
    """
    return compute_capacity_map(surface_map)
