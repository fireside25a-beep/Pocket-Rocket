"""Stable binary32 conformance-vector generation for the exact reference."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from .binary32 import add_bits, divide_bits, multiply_bits, sqrt_bits


VECTOR_VERSION = 2
DEFAULT_SEED = 20260817
DEFAULT_RANDOM_COUNT = 64


def _hex(bits: int) -> str:
    return f"0x{bits:08x}"


# Each tuple is operation, label, left bits, right bits.  These cases are
# deliberately encoding-level so signed zeros, NaN payloads, and infinities
# cannot be normalized by a host float parser.
EDGE_CASES: tuple[tuple[str, str, int, int], ...] = (
    ("add", "nan_payload", 0x7FA12345, 0x3F800000),
    ("multiply", "nan_payload", 0xFFA12345, 0x3F800000),
    ("add", "invalid_infinity", 0x7F800000, 0xFF800000),
    ("multiply", "invalid_infinity_zero", 0x7F800000, 0x00000000),
    ("add", "infinity_finite", 0x7F800000, 0x7F7FFFFF),
    ("multiply", "infinity_finite", 0xFF800000, 0xC0000000),
    ("add", "positive_zero_negative_zero", 0x00000000, 0x80000000),
    ("add", "negative_zero_negative_zero", 0x80000000, 0x80000000),
    ("multiply", "signed_zero", 0x00000000, 0x80000000),
    ("add", "max_finite_overflow", 0x7F7FFFFF, 0x7F7FFFFF),
    ("multiply", "max_finite_overflow", 0x7F7FFFFF, 0x40000000),
    ("add", "finite_cancellation", 0x7F7FFFFF, 0xFF7FFFFF),
    ("add", "min_normal_subnormal_boundary", 0x00800000, 0x807FFFFF),
    ("add", "min_normal_plus_min_normal", 0x00800000, 0x00800000),
    ("multiply", "min_normal_to_subnormal", 0x00800000, 0x3F000000),
    ("multiply", "min_subnormal_halfway_to_zero", 0x00000001, 0x3F000000),
    ("multiply", "negative_min_subnormal_halfway", 0x80000001, 0x3F000000),
    ("add", "one_plus_half_ulp_tie_even", 0x3F800000, 0x33800000),
    ("add", "one_plus_three_half_ulp_tie_even", 0x3F800000, 0x34400000),
    ("add", "largest_subnormal_to_min_normal", 0x007FFFFF, 0x00000001),
    ("add", "two_min_subnormals", 0x00000001, 0x00000001),
    ("multiply", "subnormal_underflow", 0x00000001, 0x00000001),
    ("divide", "division_nan_payload", 0x7FA12345, 0x3F800000),
    ("divide", "division_invalid_infinity", 0x7F800000, 0x7F800000),
    ("divide", "division_zero_zero", 0x00000000, 0x80000000),
    ("divide", "division_finite_zero", 0x3F800000, 0x00000000),
    ("divide", "division_infinity_finite", 0xFF800000, 0xC0000000),
    ("divide", "division_finite_infinity", 0xC0000000, 0x7F800000),
    ("divide", "division_signed_zero", 0x80000000, 0x3F800000),
    ("divide", "division_overflow", 0x7F7FFFFF, 0x00000001),
    ("divide", "division_min_subnormal_halfway", 0x00000001, 0x40000000),
    ("divide", "division_min_normal_to_subnormal", 0x00800000, 0x40000000),
    ("divide", "division_repeating", 0x3F800000, 0x40400000),
    ("divide", "division_exact_normal", 0x7F7FFFFF, 0x7F7FFFFF),
)

UNARY_EDGE_CASES: tuple[tuple[str, str, int], ...] = (
    ("sqrt", "sqrt_nan_payload", 0x7FA12345),
    ("sqrt", "sqrt_negative_nan_payload", 0xFFA12345),
    ("sqrt", "sqrt_positive_zero", 0x00000000),
    ("sqrt", "sqrt_negative_zero", 0x80000000),
    ("sqrt", "sqrt_infinity", 0x7F800000),
    ("sqrt", "sqrt_negative_invalid", 0xBF800000),
    ("sqrt", "sqrt_min_normal", 0x00800000),
    ("sqrt", "sqrt_min_subnormal", 0x00000001),
    ("sqrt", "sqrt_max_finite", 0x7F7FFFFF),
    ("sqrt", "sqrt_two", 0x40000000),
)


def _random_finite_bits(rng: random.Random) -> int:
    while True:
        bits = rng.getrandbits(32)
        if ((bits >> 23) & 0xFF) != 0xFF:
            return bits


def generate_vectors(*, seed: int = DEFAULT_SEED, random_count: int = DEFAULT_RANDOM_COUNT) -> dict[str, Any]:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if isinstance(random_count, bool) or not isinstance(random_count, int) or random_count < 0:
        raise ValueError("random_count must be a non-negative integer")
    vectors: list[dict[str, str]] = []
    operations = {"add": add_bits, "multiply": multiply_bits, "divide": divide_bits}
    for operation, label, left, right in EDGE_CASES:
        vectors.append({
            "label": label,
            "operation": operation,
            "left": _hex(left),
            "right": _hex(right),
            "expected": _hex(operations[operation](left, right)),
        })
    for operation, label, operand in UNARY_EDGE_CASES:
        vectors.append({
            "label": label,
            "operation": operation,
            "left": _hex(operand),
            "expected": _hex(sqrt_bits(operand)),
        })
    rng = random.Random(seed)
    random_operations = ("add", "multiply", "divide")
    for index in range(random_count):
        operation = random_operations[index % len(random_operations)]
        left, right = _random_finite_bits(rng), _random_finite_bits(rng)
        vectors.append({
            "label": f"seeded_random_{index:04d}",
            "operation": operation,
            "left": _hex(left),
            "right": _hex(right),
            "expected": _hex(operations[operation](left, right)),
        })
    return {
        "format": "neuro-inverse-binary32-conformance-v2",
        "seed": seed,
        "random_count": random_count,
        "vectors": vectors,
    }


def serialize_vectors(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_vectors(path: str | Path, *, seed: int = DEFAULT_SEED, random_count: int = DEFAULT_RANDOM_COUNT) -> bytes:
    payload = generate_vectors(seed=seed, random_count=random_count)
    data = serialize_vectors(payload)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return data


def vector_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "DEFAULT_RANDOM_COUNT", "DEFAULT_SEED", "EDGE_CASES", "VECTOR_VERSION",
    "generate_vectors", "serialize_vectors", "vector_sha256", "write_vectors",
]
