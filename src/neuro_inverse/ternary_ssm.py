"""Exact diagonal ternary SSM reference and checkpoint comparator.

This is deliberately not a Mamba compatibility layer. It consumes a small,
explicit NPZ contract (A, B, output_weight) and reports the divergence caused
by the fixed ternarization rule. No training or threshold fitting occurs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import numpy as np


@dataclass(frozen=True, slots=True)
class DiagonalSSMCheckpoint:
    a_source: np.ndarray
    b_source: np.ndarray
    output_weight: np.ndarray
    sha256: str

    @property
    def hidden_dim(self) -> int:
        return int(self.a_source.size)


def quantize_exact_ternary(values: np.ndarray) -> np.ndarray:
    """Map <=-0.5 to -1, >=+0.5 to +1, and the open interval to zero."""
    array = np.asarray(values, dtype=np.float32)
    if not np.isfinite(array).all():
        raise ValueError("ternary quantization rejects non-finite values")
    return np.where(array <= np.float32(-0.5), -1,
                    np.where(array >= np.float32(0.5), 1, 0)).astype(np.int8)


def load_diagonal_checkpoint(path: Path) -> DiagonalSSMCheckpoint:
    raw = path.read_bytes()
    with np.load(path, allow_pickle=False) as archive:
        required = {"A", "B", "output_weight"}
        if set(archive.files) != required:
            raise ValueError("checkpoint must contain exactly A, B, output_weight")
        a = np.asarray(archive["A"], dtype=np.float32)
        b = np.asarray(archive["B"], dtype=np.float32)
        out = np.asarray(archive["output_weight"], dtype=np.float32)
    if a.ndim != 1 or b.ndim != 1 or out.ndim != 1 or not (a.shape == b.shape == out.shape):
        raise ValueError("diagonal checkpoint arrays must be equal-length vectors")
    if not 1 <= a.size <= 4096:
        raise ValueError("hidden dimension must be 1..4096")
    if not np.isfinite(a).all() or not np.isfinite(b).all() or not np.isfinite(out).all():
        raise ValueError("checkpoint contains non-finite values")
    return DiagonalSSMCheckpoint(a, b, out, hashlib.sha256(raw).hexdigest())


def compare_checkpoint(checkpoint: DiagonalSSMCheckpoint, inputs: np.ndarray) -> dict[str, object]:
    sequence = np.asarray(inputs)
    if sequence.ndim != 2 or sequence.shape[1] != checkpoint.hidden_dim:
        raise ValueError("input must have shape [tokens, hidden_dim]")
    if not np.issubdtype(sequence.dtype, np.integer):
        raise TypeError("exact SSM comparison requires integer inputs")
    seq64 = sequence.astype(np.int64, copy=False)
    if np.any(seq64 < np.iinfo(np.int32).min) or np.any(seq64 > np.iinfo(np.int32).max):
        raise ValueError("input exceeds int32 range")
    aq = quantize_exact_ternary(checkpoint.a_source).astype(np.int64)
    bq = quantize_exact_ternary(checkpoint.b_source).astype(np.int64)
    exact_state = np.zeros(checkpoint.hidden_dim, dtype=np.int64)
    source_state = np.zeros(checkpoint.hidden_dim, dtype=np.float32)
    exact_outputs: list[np.float32] = []
    source_outputs: list[np.float32] = []
    for row in seq64:
        exact_state = aq * exact_state + bq * row
        if np.any(exact_state < np.iinfo(np.int32).min) or np.any(exact_state > np.iinfo(np.int32).max):
            raise OverflowError("exact ternary state exceeded int32")
        # Source path is an explicit float32 comparator, not part of the exact plane.
        source_state = checkpoint.a_source * source_state + checkpoint.b_source * row.astype(np.float32)
        exact_outputs.append(np.float32(np.dot(exact_state.astype(np.float32), checkpoint.output_weight)))
        source_outputs.append(np.float32(np.dot(source_state, checkpoint.output_weight)))
    exact = np.asarray(exact_outputs, dtype=np.float32)
    source = np.asarray(source_outputs, dtype=np.float32)
    delta = np.abs(exact.astype(np.float64) - source.astype(np.float64))
    return {
        "checkpoint_sha256": checkpoint.sha256,
        "hidden_dim": checkpoint.hidden_dim,
        "tokens": int(sequence.shape[0]),
        "quantization_rule": "x<=-0.5:-1; -0.5<x<0.5:0; x>=0.5:+1",
        "max_abs_divergence": float(delta.max(initial=0.0)),
        "mean_abs_divergence": float(delta.mean()) if delta.size else 0.0,
        "p50_abs_divergence": float(np.quantile(delta, 0.5)) if delta.size else 0.0,
        "p95_abs_divergence": float(np.quantile(delta, 0.95)) if delta.size else 0.0,
    }
