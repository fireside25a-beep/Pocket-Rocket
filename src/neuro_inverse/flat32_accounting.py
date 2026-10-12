"""Flat32 stream/dictionary byte accounting, independent of the codec.

The model is intentionally small and explicit:

* B=32 bytes per dense block;
* N total blocks, R registered/token blocks, F=N-R raw blocks;
* bitmap ``ceil(N/8)`` bytes;
* token bytes R and raw bytes 32F;
* dictionary bytes 32D, with D<=256;
* configurable header and tail framing.

Ratios are arithmetic estimates only.  They do not imply codec speed, quality,
or the existence of any particular framing in an external artifact.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

B = 32
MAX_DICTIONARY_ENTRIES = 256


def _nonnegative(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class Flat32Estimate:
    block_bytes: int
    total_blocks: int
    registered_blocks: int
    raw_blocks: int
    dictionary_entries: int
    header_bytes: int
    tail_bytes: int
    dense_bytes: int
    bitmap_bytes: int
    token_bytes: int
    raw_bytes: int
    dictionary_bytes: int
    framing_bytes: int
    stream_bytes: int
    dictionary_inclusive_bytes: int
    stream_ratio: float
    dictionary_inclusive_ratio: float
    registered_coverage: float
    break_even_registered_stream: int
    break_even_registered_dictionary: int
    break_even_coverage_stream: float
    break_even_coverage_dictionary: float
    break_even_total_blocks_stream: int
    break_even_total_blocks_dictionary: int
    target_stream_ratio: float | None
    target_dictionary_ratio: float | None
    target_stream_extra_bytes: float | None
    target_dictionary_extra_bytes: float | None
    target_dictionary_unaccounted_bytes: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_flat32(
    total_blocks: int,
    registered_blocks: int,
    *,
    dictionary_entries: int = MAX_DICTIONARY_ENTRIES,
    header_bytes: int = 32,
    tail_bytes: int = 32,
    target_stream_ratio: float | None = None,
    target_dictionary_ratio: float | None = None,
) -> Flat32Estimate:
    """Compute stream and dictionary-inclusive accounting from explicit counts."""
    _nonnegative("total_blocks", total_blocks)
    _nonnegative("registered_blocks", registered_blocks)
    _nonnegative("dictionary_entries", dictionary_entries)
    _nonnegative("header_bytes", header_bytes)
    _nonnegative("tail_bytes", tail_bytes)
    if total_blocks < 1:
        raise ValueError("total_blocks must be positive")
    if registered_blocks > total_blocks:
        raise ValueError("registered_blocks cannot exceed total_blocks")
    if dictionary_entries > MAX_DICTIONARY_ENTRIES:
        raise ValueError(f"dictionary_entries cannot exceed {MAX_DICTIONARY_ENTRIES}")
    for name, ratio in (("target_stream_ratio", target_stream_ratio), ("target_dictionary_ratio", target_dictionary_ratio)):
        if ratio is not None and (not isinstance(ratio, (float, int)) or isinstance(ratio, bool) or not math.isfinite(ratio) or ratio <= 0):
            raise ValueError(f"{name} must be finite and positive")

    raw_blocks = total_blocks - registered_blocks
    dense_bytes = B * total_blocks
    bitmap_bytes = math.ceil(total_blocks / 8)
    token_bytes = registered_blocks
    raw_bytes = B * raw_blocks
    dictionary_bytes = B * dictionary_entries
    framing_bytes = header_bytes + tail_bytes
    stream_bytes = framing_bytes + bitmap_bytes + token_bytes + raw_bytes
    dictionary_inclusive = stream_bytes + dictionary_bytes

    # Strictly cheaper than dense.  Registering one block replaces B raw
    # bytes with one token byte, so each registration saves B-1 bytes.
    stream_overhead = framing_bytes + bitmap_bytes
    dict_overhead = stream_overhead + dictionary_bytes
    break_stream = min(total_blocks + 1, stream_overhead // (B - 1) + 1)
    break_dict = min(total_blocks + 1, dict_overhead // (B - 1) + 1)
    def max_n(extra_bytes: int) -> int:
        capacity = (B - 1) * registered_blocks - framing_bytes - extra_bytes
        if capacity <= 0:
            return 0
        candidate = 8 * (capacity - 1)
        if candidate < registered_blocks:
            return 0
        return candidate
    max_n_stream = max_n(0)
    max_n_dictionary = max_n(dictionary_bytes)
    target_stream_extra = None if target_stream_ratio is None else dense_bytes / float(target_stream_ratio) - stream_bytes
    target_dict_extra = None if target_dictionary_ratio is None else dense_bytes / float(target_dictionary_ratio) - stream_bytes
    target_unaccounted = None if target_dict_extra is None else target_dict_extra - dictionary_bytes
    return Flat32Estimate(
        B, total_blocks, registered_blocks, raw_blocks, dictionary_entries,
        header_bytes, tail_bytes, dense_bytes, bitmap_bytes, token_bytes, raw_bytes,
        dictionary_bytes, framing_bytes, stream_bytes, dictionary_inclusive,
        dense_bytes / stream_bytes, dense_bytes / dictionary_inclusive,
        registered_blocks / total_blocks, break_stream, break_dict,
        break_stream / total_blocks, break_dict / total_blocks,
        max_n_stream, max_n_dictionary,
        None if target_stream_ratio is None else float(target_stream_ratio),
        None if target_dictionary_ratio is None else float(target_dictionary_ratio),
        target_stream_extra, target_dict_extra, target_unaccounted,
    )


RECALLED_REGISTERED = 701_489
RECALLED_RAW = 155_311
RECALLED_TOTAL = RECALLED_REGISTERED + RECALLED_RAW
