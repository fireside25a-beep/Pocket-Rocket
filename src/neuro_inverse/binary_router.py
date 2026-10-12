"""Deterministic 256-bit random-hyperplane router for dense-to-MoE experts."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .codes import hamming256


def projection_matrix(input_dim: int, *, bits: int = 256, seed: int = 20260817) -> np.ndarray:
    if bits != 256:
        raise ValueError("NeuroRoute v1 requires exactly 256 bits")
    rng = np.random.default_rng(seed)
    # Sparse Achlioptas projection: {-1,0,+1}; deterministic for a fixed NumPy version/seed.
    raw = rng.integers(0, 6, size=(bits, input_dim), dtype=np.int8)
    return np.where(raw == 0, -1, np.where(raw == 1, 1, 0)).astype(np.int8)


def binary_code(vector: np.ndarray, projection: np.ndarray) -> bytes:
    values = projection.astype(np.float32) @ np.asarray(vector, dtype=np.float32)
    bits = values >= 0
    return np.packbits(bits, bitorder="little").tobytes()


@dataclass(frozen=True)
class BinaryExpertRouter:
    projection: np.ndarray
    centroids: tuple[bytes, ...]

    @classmethod
    def from_keys(cls, keys: np.ndarray, *, seed: int = 20260817) -> "BinaryExpertRouter":
        projection = projection_matrix(keys.shape[1], seed=seed)
        return cls(projection, tuple(binary_code(key, projection) for key in keys))

    def rank(self, hidden: np.ndarray) -> tuple[tuple[int, int], ...]:
        query = binary_code(hidden, self.projection)
        return tuple(sorted(
            ((expert_id, hamming256(query, centroid)) for expert_id, centroid in enumerate(self.centroids)),
            key=lambda item: (item[1], item[0]),
        ))


def calibrated_centroid(codes: list[bytes]) -> bytes:
    if not codes:
        raise ValueError("cannot calibrate centroid without codes")
    unpacked = np.stack([np.unpackbits(np.frombuffer(code, dtype=np.uint8), bitorder="little") for code in codes])
    majority = unpacked.sum(axis=0) * 2 >= len(codes)
    return np.packbits(majority, bitorder="little").tobytes()

