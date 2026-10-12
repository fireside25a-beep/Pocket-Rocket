from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

BITS = 256
CODE_BYTES = BITS // 8
_TOKEN = re.compile(r"[\w+#.-]+", re.UNICODE)


def _features(text: str) -> Iterable[str]:
    tokens = [t.casefold() for t in _TOKEN.findall(text)]
    yield from (f"u:{token}" for token in tokens)
    yield from (f"b:{a}|{b}" for a, b in zip(tokens, tokens[1:]))
    for token in tokens:
        padded = f"^{token}$"
        yield from (f"c:{padded[i:i+3]}" for i in range(max(0, len(padded) - 2)))


def simhash256(text: str) -> bytes:
    """Return a stable, similarity-preserving 256-bit code for a text string."""
    scores = [0] * BITS
    any_feature = False
    for feature in _features(text):
        any_feature = True
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=CODE_BYTES).digest()
        for bit in range(BITS):
            scores[bit] += 1 if digest[bit // 8] & (1 << (bit % 8)) else -1
    if not any_feature:
        return bytes(CODE_BYTES)
    out = bytearray(CODE_BYTES)
    for bit, score in enumerate(scores):
        if score >= 0:
            out[bit // 8] |= 1 << (bit % 8)
    return bytes(out)


def hamming256(left: bytes, right: bytes) -> int:
    if len(left) != CODE_BYTES or len(right) != CODE_BYTES:
        raise ValueError("Hamming codes must be exactly 256 bits")
    return int.from_bytes(left, "little").__xor__(int.from_bytes(right, "little")).bit_count()


def code_hex(code: bytes) -> str:
    if len(code) != CODE_BYTES:
        raise ValueError("Code must be exactly 256 bits")
    return code.hex()


def parse_code(value: str) -> bytes:
    raw = bytes.fromhex(value)
    if len(raw) != CODE_BYTES:
        raise ValueError("Encoded code must be exactly 64 hexadecimal characters")
    return raw

