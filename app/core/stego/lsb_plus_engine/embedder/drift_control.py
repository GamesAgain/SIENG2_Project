from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.stego.lsb_plus_engine.analyzer.metrics import chi_square_block, histogram_drift_block, variance_ratio_block




@dataclass
class BlockSafetyThresholds:
    max_hist_drift: float = 0.15
    max_var_ratio: float = 0.5   # |var_s - var_o| / (var_o + eps)
    max_chi_square: float = 5_000.0


def is_block_safe(
    original_block: np.ndarray,
    stego_block: np.ndarray,
    thresholds: BlockSafetyThresholds,
) -> bool:
    """
    Evaluate whether a block is safe to keep embedded changes.

    Checks:
      - histogram drift
      - variance ratio
      - chi-square value
    """
    hd = histogram_drift_block(original_block, stego_block)
    vr = variance_ratio_block(original_block, stego_block)
    cs = chi_square_block(original_block, stego_block)

    if hd > thresholds.max_hist_drift:
        return False
    if vr > thresholds.max_var_ratio:
        return False
    if cs > thresholds.max_chi_square:
        return False
    return True
