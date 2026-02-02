from __future__ import annotations

import os
from typing import Tuple

import numpy as np
from PIL import Image



def _validate_png_image(img: Image.Image, path: str) -> None:
    if img.format != "PNG":
        raise Exception(f"File is not PNG: {path}")
    if img.mode not in ("RGB", "RGBA"):
        raise Exception(f"Invalid PNG mode (expected RGB/RGBA): {img.mode}")


def load_png(path: str) -> np.ndarray:
    """
    Load PNG (24-bit) and return as HxWx3 uint8 array.
    Reject non-PNG formats.
    """
    if not os.path.isfile(path):
        raise Exception(f"File not found: {path}")
    try:
        img = Image.open(path)
    except Exception as exc:
        raise Exception(f"Failed to open image: {exc}") from exc

    _validate_png_image(img, path)

    if img.mode == "RGBA":
        # drop alpha (we only operate on RGB)
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    arr = np.asarray(img, dtype=np.uint8)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise Exception("Expected 24-bit RGB PNG.")
    return arr


def save_png_array(arr: np.ndarray, path: str) -> None:
    """
    Save RGB array as PNG, preserving dimensions.
    """
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise Exception("save_png_array expects HxWx3 array.")

    img = Image.fromarray(arr.astype(np.uint8), mode="RGB")
    try:
        img.save(path, format="PNG")
    except Exception as exc:
        raise Exception(f"Failed to save PNG: {exc}") from exc
