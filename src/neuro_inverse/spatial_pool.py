"""Optional Python golden-hash accelerator for the exact 256-bit router.

The index is only a candidate accelerator. Every hash hit is verified against
all four 64-bit coordinate words, and ranking still evaluates every eligible
record by exact Hamming distance. A primary hash collision can therefore
never become a false route or replace the correctness-preserving linear
fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .codes import CODE_BYTES, hamming256, simhash256


KNUTH_GOLDEN_RATIO_64 = 0x9E3779B97F4A7C15
MASK64 = (1 << 64) - 1
BUCKET_COUNT = 512


def splitmix64(value: int) -> int:
    """Apply the specified SplitMix64 avalanche to one unsigned word."""
    value = (value + KNUTH_GOLDEN_RATIO_64) & MASK64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
    return (value ^ (value >> 31)) & MASK64


def coordinate_words(code: bytes) -> tuple[int, int, int, int]:
    """Decode a 256-bit little-endian code into its four verified words."""
    if len(code) != CODE_BYTES:
        raise ValueError("SpatialPool coordinates must contain exactly 256 bits")
    return tuple(int.from_bytes(code[offset:offset + 8], "little") for offset in range(0, CODE_BYTES, 8))  # type: ignore[return-value]


def golden_bucket(code: bytes) -> int:
    """Map four coordinate words to one of the 512 deterministic buckets."""
    words = coordinate_words(code)
    state = KNUTH_GOLDEN_RATIO_64
    for index, word in enumerate(words, 1):
        mixed = (state ^ word ^ ((KNUTH_GOLDEN_RATIO_64 * index) & MASK64)) & MASK64
        state = splitmix64(mixed)
    return splitmix64(state) & (BUCKET_COUNT - 1)


@dataclass(frozen=True)
class _Entry:
    words: tuple[int, int, int, int]
    stable_id: str
    record: Any


class GoldenHashIndex:
    """Immutable 512-bucket index with mandatory exact-coordinate checks."""

    def __init__(self, records: tuple[Any, ...] | list[Any]) -> None:
        ordered = tuple(sorted(records, key=lambda item: item.expert_id))
        stable_ids = [item.expert_id for item in ordered]
        if len(set(stable_ids)) != len(stable_ids):
            raise ValueError("SpatialPool stable IDs must be unique")
        buckets: list[list[_Entry]] = [[] for _ in range(BUCKET_COUNT)]
        for record in ordered:
            code = record.code
            entry = _Entry(coordinate_words(code), record.expert_id, record)
            buckets[golden_bucket(code)].append(entry)
        self.records = ordered
        self._buckets = tuple(tuple(bucket) for bucket in buckets)

    def lookup_exact(self, code: bytes) -> tuple[Any, ...]:
        """Return only full four-word coordinate matches in the hash bucket."""
        words = coordinate_words(code)
        bucket = self._buckets[golden_bucket(code)]
        return tuple(entry.record for entry in bucket if entry.words == words)

    def rank_code(self, code: bytes, *, top_k: int = 3,
                  domain: str | None = None, task_kind: str | None = None) -> tuple[tuple[Any, int], ...]:
        """Rank exactly like linear Hamming routing, using verified zero hits."""
        if top_k < 1:
            raise ValueError("top_k must be positive")
        exact_ids = {record.expert_id for record in self.lookup_exact(code)}
        eligible = tuple(
            record for record in self.records
            if record.compatibility.allows(domain, task_kind)
        )
        # The fallback scans every eligible record. Exact hits are distance
        # zero only after full-word verification; collisions never skip this.
        ranked = sorted(
            (
                (record, 0 if record.expert_id in exact_ids else hamming256(code, record.code))
                for record in eligible
            ),
            key=lambda item: (item[1], 0 if item[0].compatibility.allows(domain, task_kind) else 1, item[0].expert_id),
        )
        return tuple(ranked[:top_k])


class GoldenHammingRouter:
    """Drop-in text router using the optional verified golden-hash index."""

    def __init__(self, records: tuple[Any, ...] | list[Any], *, index: GoldenHashIndex | None = None) -> None:
        self.index = index or GoldenHashIndex(records)

    def route(self, text: str, *, top_k: int = 3, domain: str | None = None,
              task_kind: str | None = None):
        query = simhash256(text)
        from .router import Route
        return tuple(Route(record, distance) for record, distance in self.index.rank_code(
            query, top_k=top_k, domain=domain, task_kind=task_kind
        ))


__all__ = [
    "BUCKET_COUNT", "GoldenHashIndex", "GoldenHammingRouter", "KNUTH_GOLDEN_RATIO_64",
    "coordinate_words", "golden_bucket", "splitmix64",
]
