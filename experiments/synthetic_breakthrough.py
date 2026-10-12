#!/usr/bin/env python3
"""Small reproducible proof of the three architectural invariants."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from neuro_inverse.binary_router import BinaryExpertRouter
from neuro_inverse.moefication import dense_swiglu, equal_expert_slices, expert_key, sparse_swiglu
from neuro_inverse.nprq import decode_tensor, encode_tensor


def relative_error(expected: np.ndarray, actual: np.ndarray) -> float:
    return float(np.linalg.norm(expected - actual) / max(np.linalg.norm(expected), 1e-12))


def main() -> int:
    rng = np.random.default_rng(20260817)
    hidden, intermediate, expert_count = 64, 256, 16
    x = rng.normal(size=(32, hidden)).astype(np.float32)
    gate = rng.normal(scale=0.08, size=(intermediate, hidden)).astype(np.float32)
    up = rng.normal(scale=0.08, size=(intermediate, hidden)).astype(np.float32)
    down = rng.normal(scale=0.08, size=(hidden, intermediate)).astype(np.float32)
    experts = equal_expert_slices(intermediate, expert_count)
    keys = np.stack([expert_key(gate, up, down, expert) for expert in experts])
    router = BinaryExpertRouter.from_keys(keys)
    dense = dense_swiglu(x, gate, up, down)
    order = tuple(item[0] for item in router.rank(x.mean(axis=0)))
    routed = {str(k): relative_error(dense, sparse_swiglu(x, gate, up, down, experts, order[:k]))
              for k in (1, 2, 4, 8, 16)}

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        meta = encode_tensor(gate, root, "synthetic.gate", stages=4, block_size=256)
        stage_error = [relative_error(gate, decode_tensor(root, meta, stage_count=i)) for i in range(1, 5)]
        stage_bytes = [sum((root / name).stat().st_size for name in meta.stage_files[:i]) for i in range(1, 5)]
    result = {
        "seed": 20260817,
        "dense_reconstruction_relative_error_all_experts": routed["16"],
        "hamming_code_bits": len(router.centroids[0]) * 8,
        "route_repeatable": router.rank(x.mean(axis=0)) == router.rank(x.mean(axis=0)),
        "routed_output_relative_error_by_experts": routed,
        "nprq_weight_relative_error_by_stages": stage_error,
        "nprq_bytes_by_stages": stage_bytes,
        "important": "Sparse quality is empirical; only all-expert structural reconstruction and NPRQ weight-error monotonicity are invariants.",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
