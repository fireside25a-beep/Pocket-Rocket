"""Independent stage-wise NPRQ monotonicity verifier."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import math
import numpy as np

from .nprq import NPRQMeta, decode_tensor, verify_tensor
from .envelope import canonical_sha256


def prove_monotone(output_dir: Path, meta: NPRQMeta, source_npy: Path) -> dict[str, object]:
    """Recompute stage SSE against the original tensor and emit a certificate.

    The source tensor is mandatory: stage metadata alone can validate declared RMSE
    ordering, but cannot independently prove reconstruction SSE.
    """
    verify_tensor(output_dir, meta)
    source = np.load(source_npy, allow_pickle=False)
    if tuple(source.shape) != meta.shape:
        raise ValueError("source shape does not match NPRQ metadata")
    source32 = source.astype(np.float32, copy=False)
    source_digest = hashlib.sha256(source_npy.read_bytes()).hexdigest()
    sse: list[float] = []
    violation: int | None = None
    for stage_count in range(1, meta.stages + 1):
        reconstructed = decode_tensor(output_dir, meta, stage_count=stage_count)
        delta = source32 - reconstructed.astype(np.float32, copy=False)
        value = float(np.dot(delta.reshape(-1), delta.reshape(-1)))
        if not math.isfinite(value):
            raise ValueError("non-finite reconstructed SSE")
        sse.append(value)
        if len(sse) > 1 and sse[-1] > sse[-2]:
            violation = stage_count - 1
            break
    payload: dict[str, object] = {
        "domain": "nprq-monotonicity-proof-v1",
        "source_sha256": source_digest,
        "stage_count": meta.stages,
        "sse": sse,
        "monotone_non_increasing": violation is None,
        "violation_stage_index": violation,
    }
    payload["certificate"] = canonical_sha256(payload)
    return payload
