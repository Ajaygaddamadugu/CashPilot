"""Seeded random streams.

Each generator module asks for its own named stream. The stream seed is derived
from (dataset seed, stream name), so changing how many draws one module makes
never shifts the numbers produced by another module.
"""

from __future__ import annotations

import hashlib

import numpy as np


def stream(seed: int, name: str) -> np.random.Generator:
    digest = hashlib.sha256(f"{seed}:{name}".encode("utf-8")).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))
