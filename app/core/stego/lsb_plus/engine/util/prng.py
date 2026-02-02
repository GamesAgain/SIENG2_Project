from __future__ import annotations

import hashlib
import random
from typing import Iterable, List


def rng_from_seed(seed: str) -> random.Random:
    """
    Deterministic RNG from a string seed using SHA-256.
    """
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    seed_int = int.from_bytes(h[:8], "big", signed=False)
    return random.Random(seed_int)


def shuffle_indices(indices: Iterable[int], seed: str) -> List[int]:
    rng = rng_from_seed(seed)
    lst = list(indices)
    rng.shuffle(lst)
    return lst
