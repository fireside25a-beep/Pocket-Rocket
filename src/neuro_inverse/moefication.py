"""Exact structural partitioning of a dense SwiGLU FFN into experts."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def silu(x: np.ndarray) -> np.ndarray:
    values = np.asarray(x)
    # The direct formula overflows for large negative activations, turning a
    # perfectly finite FFN into NaN.  This branch is algebraically identical
    # while remaining finite for float32/float64 inputs.
    result = np.empty_like(values, dtype=np.result_type(values, np.float32))
    positive = values >= 0
    result[positive] = values[positive] / (1.0 + np.exp(-values[positive]))
    negative = ~positive
    exp_values = np.exp(values[negative])
    result[negative] = values[negative] * exp_values / (1.0 + exp_values)
    # Preserve SiLU's negative sign when a very large negative value
    # underflows to IEEE ``-0`` in float32.  This remains finite and avoids a
    # surprising sign loss in deterministic numerical checks.
    underflow = negative & (result == 0)
    if np.any(underflow):
        zero = np.array(0, dtype=result.dtype)
        result[underflow] = np.nextafter(zero, np.array(-np.inf, dtype=result.dtype))
    return result


def dense_swiglu(x: np.ndarray, gate: np.ndarray, up: np.ndarray, down: np.ndarray) -> np.ndarray:
    return (silu(x @ gate.T) * (x @ up.T)) @ down.T


@dataclass(frozen=True)
class ExpertSlice:
    expert_id: int
    indices: np.ndarray


def equal_expert_slices(intermediate_size: int, expert_count: int) -> tuple[ExpertSlice, ...]:
    if expert_count < 1 or expert_count > intermediate_size:
        raise ValueError("invalid expert count")
    parts = np.array_split(np.arange(intermediate_size, dtype=np.int64), expert_count)
    return tuple(ExpertSlice(i, part) for i, part in enumerate(parts))


def expert_swiglu(x: np.ndarray, gate: np.ndarray, up: np.ndarray, down: np.ndarray,
                  expert: ExpertSlice) -> np.ndarray:
    idx = expert.indices
    return (silu(x @ gate[idx].T) * (x @ up[idx].T)) @ down[:, idx].T


def sparse_swiglu(x: np.ndarray, gate: np.ndarray, up: np.ndarray, down: np.ndarray,
                   experts: tuple[ExpertSlice, ...], selected: tuple[int, ...]) -> np.ndarray:
    output = np.zeros((*x.shape[:-1], down.shape[0]), dtype=np.result_type(x, gate, up, down))
    for expert_id in selected:
        output += expert_swiglu(x, gate, up, down, experts[expert_id])
    return output


def expert_key(gate: np.ndarray, up: np.ndarray, down: np.ndarray, expert: ExpertSlice) -> np.ndarray:
    """Zero-shot routing key in hidden space, weighted by output column norms."""
    idx = expert.indices
    weights = np.linalg.norm(down[:, idx].astype(np.float32), axis=0)
    directions = gate[idx].astype(np.float32) + up[idx].astype(np.float32)
    key = (directions * weights[:, None]).sum(axis=0)
    norm = np.linalg.norm(key)
    return key / norm if norm else key


def contribution_bound_coefficient(gate: np.ndarray, up: np.ndarray, down: np.ndarray) -> float:
    """Return C such that ||expert(x)||_2 <= C ||x||_2^2.

    This uses |silu(t)| <= |t|, Cauchy-Schwarz for each gate/up row,
    and the triangle inequality over down-projection columns.  It is deliberately
    conservative, but it is a certificate rather than a confidence score.
    """
    if gate.shape != up.shape or down.shape != (gate.shape[1], gate.shape[0]):
        raise ValueError("incompatible SwiGLU expert shapes")
    if not (np.isfinite(gate).all() and np.isfinite(up).all() and np.isfinite(down).all()):
        raise ValueError("SwiGLU certificate requires finite weights")
    gate_norm = np.linalg.norm(gate.astype(np.float64), axis=1)
    up_norm = np.linalg.norm(up.astype(np.float64), axis=1)
    down_norm = np.linalg.norm(down.astype(np.float64), axis=0)
    return float(np.sum(gate_norm * up_norm * down_norm))


def precision_delta_bound_coefficient(
    gate_low: np.ndarray, up_low: np.ndarray, down_low: np.ndarray,
    gate_high: np.ndarray, up_high: np.ndarray, down_high: np.ndarray,
) -> float:
    """C such that ||expert_high(x)-expert_low(x)|| <= C||x||^2.

    The derivation expands the output difference into a down-matrix term and a
    gated-activation term.  A conservative 1.25 global Lipschitz constant is
    used for SiLU (its true maximum derivative is below 1.1).
    """
    for gate, up, down in ((gate_low, up_low, down_low), (gate_high, up_high, down_high)):
        if gate.shape != up.shape or down.shape != (gate.shape[1], gate.shape[0]):
            raise ValueError("incompatible SwiGLU expert shapes")
        if not (np.isfinite(gate).all() and np.isfinite(up).all() and np.isfinite(down).all()):
            raise ValueError("SwiGLU certificate requires finite weights")
    g0, u0, d0 = (value.astype(np.float64) for value in (gate_low, up_low, down_low))
    g1, u1, d1 = (value.astype(np.float64) for value in (gate_high, up_high, down_high))
    max_row = lambda matrix: float(np.linalg.norm(matrix, axis=1).max(initial=0.0))
    z_high = float(np.linalg.norm(g1)) * max_row(u1)
    z_delta = 1.25 * float(np.linalg.norm(g1 - g0)) * max_row(u1)
    z_delta += float(np.linalg.norm(g0)) * max_row(u1 - u0)
    return float(np.linalg.norm(d1 - d0)) * z_high + float(np.linalg.norm(d0)) * z_delta
