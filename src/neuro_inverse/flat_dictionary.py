"""Exact lossless 32-byte flat dictionary codec.

This is a generic byte-stream codec, not a model or wire-format integration.
Full 32-byte blocks are represented by a one-bit registration bitmap and an
8-bit dictionary token when present; unregistered blocks retain all 32 raw
bytes. The final tail is framed and copied byte-for-byte.

``train_dictionary`` is deterministic but intentionally does not split data:
callers must pass training-only streams and keep evaluation/test streams out of
the trainer. This module never claims a quality or generalization result from
dictionary coverage.
"""
from __future__ import annotations

import hashlib
import io
import math
import struct
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


BLOCK_SIZE = 32
MAX_DICTIONARY_ENTRIES = 256
MAGIC = b"NRFLAT32"
VERSION = 1
HEADER = struct.Struct("<8sHHHHQQQQ32s32s")
HEADER_SIZE = HEADER.size
DICTIONARY_MAGIC = b"NRDICT32"
DICTIONARY_VERSION = 1
DICTIONARY_HEADER = struct.Struct("<8sHHH32s")
MAX_SOURCE_BYTES = 128 * 1024 * 1024 * 1024
MAX_ENCODED_BYTES = 128 * 1024 * 1024 * 1024
# Training is deliberately fail-closed.  A caller may provide arbitrarily
# large streams, but a dictionary trainer must never grow a Counter without a
# hard memory bound.  The adaptive package builder uses the same bound for its
# prefix sample.
MAX_TRAINING_BLOCKS = 65_536
MAX_TRAINING_UNIQUE_BLOCKS = 65_536


class FlatDictionaryError(ValueError):
    """Raised when a dictionary stream fails strict structural validation."""


@dataclass(frozen=True)
class Dictionary32:
    """Immutable ordered dictionary of unique exact 32-byte blocks."""

    entries: tuple[bytes, ...]

    def __post_init__(self) -> None:
        normalized = tuple(bytes(entry) for entry in self.entries)
        if len(normalized) > MAX_DICTIONARY_ENTRIES:
            raise ValueError("dictionary cannot contain more than 256 entries")
        if any(len(entry) != BLOCK_SIZE for entry in normalized):
            raise ValueError("every dictionary entry must contain exactly 32 bytes")
        if len(set(normalized)) != len(normalized):
            raise ValueError("dictionary entries must be unique")
        object.__setattr__(self, "entries", normalized)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(b"".join(self.entries)).hexdigest()

    @property
    def bytes(self) -> int:
        return len(self.entries) * BLOCK_SIZE

    def index(self) -> dict[bytes, int]:
        return {entry: index for index, entry in enumerate(self.entries)}

    def serialize(self) -> bytes:
        """Return the deterministic standalone shared-dictionary file bytes."""
        return serialize_dictionary(self)

    @classmethod
    def deserialize(cls, data: bytes | bytearray | memoryview) -> "Dictionary32":
        return deserialize_dictionary(data)


def _validate_limit(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@contextmanager
def _open_stream(source: bytes | bytearray | memoryview | str | Path | BinaryIO):
    if isinstance(source, (bytes, bytearray, memoryview)):
        yield io.BytesIO(bytes(source))
    elif isinstance(source, (str, Path)):
        with Path(source).open("rb") as handle:
            yield handle
    elif hasattr(source, "read"):
        yield source
    else:
        raise TypeError("stream must be bytes, a path, or a binary reader")


def _blocks(handle: BinaryIO, *, chunk_bytes: int = 1024 * 1024) -> Iterator[bytes]:
    carry = bytearray()
    while True:
        chunk = handle.read(chunk_bytes)
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError("binary reader must return bytes")
        if not chunk:
            break
        carry.extend(chunk)
        complete = (len(carry) // BLOCK_SIZE) * BLOCK_SIZE
        for offset in range(0, complete, BLOCK_SIZE):
            yield bytes(carry[offset:offset + BLOCK_SIZE])
        del carry[:complete]


def train_dictionary(
    streams: Iterable[bytes | bytearray | memoryview | str | Path | BinaryIO],
    *,
    max_entries: int = MAX_DICTIONARY_ENTRIES,
) -> Dictionary32:
    """Train a deterministic dictionary from multiple training-only streams.

    Blocks are ranked by descending frequency, then lexicographic block bytes;
    this makes ties independent of hash-table iteration and input scheduling.
    Evaluation data must not be supplied to this function.
    """
    if not isinstance(max_entries, int) or isinstance(max_entries, bool):
        raise ValueError("max_entries must be an integer")
    if not 0 <= max_entries <= MAX_DICTIONARY_ENTRIES:
        raise ValueError("max_entries must be between 0 and 256")
    counts: Counter[bytes] = Counter()
    for source in streams:
        with _open_stream(source) as handle:
            for block in _blocks(handle):
                counts[block] += 1
                if len(counts) > MAX_TRAINING_UNIQUE_BLOCKS:
                    raise FlatDictionaryError(
                        "dictionary training unique-block bound exceeded"
                    )
    ranked = sorted(counts, key=lambda block: (-counts[block], block))
    return Dictionary32(tuple(ranked[:max_entries]))


def train_dictionary_bounded(
    streams: Iterable[bytes | bytearray | memoryview | str | Path | BinaryIO],
    *,
    max_entries: int = MAX_DICTIONARY_ENTRIES,
    max_sample_blocks: int = 65_536,
) -> Dictionary32:
    """Train from a deterministic bounded prefix sample.

    This is the production package-builder path: it caps the number of unique
    32-byte keys retained in RAM.  It does not claim to find the global most
    frequent blocks.  The adaptive packer measures the complete encoded result
    and rejects Flat32 when the sampled dictionary does not produce a byte win.
    """
    if not isinstance(max_sample_blocks, int) or isinstance(max_sample_blocks, bool):
        raise ValueError("max_sample_blocks must be an integer")
    if not 1 <= max_sample_blocks <= MAX_TRAINING_BLOCKS:
        raise ValueError(
            f"max_sample_blocks must be between 1 and {MAX_TRAINING_BLOCKS}"
        )
    if not isinstance(max_entries, int) or isinstance(max_entries, bool):
        raise ValueError("max_entries must be an integer")
    if not 0 <= max_entries <= MAX_DICTIONARY_ENTRIES:
        raise ValueError("max_entries must be between 0 and 256")
    counts: Counter[bytes] = Counter()
    sampled = 0
    for source in streams:
        with _open_stream(source) as handle:
            for block in _blocks(handle):
                counts[block] += 1
                if len(counts) > MAX_TRAINING_UNIQUE_BLOCKS:
                    raise FlatDictionaryError(
                        "dictionary training unique-block bound exceeded"
                    )
                sampled += 1
                if sampled >= max_sample_blocks:
                    ranked = sorted(counts, key=lambda value: (-counts[value], value))
                    return Dictionary32(tuple(ranked[:max_entries]))
    ranked = sorted(counts, key=lambda value: (-counts[value], value))
    return Dictionary32(tuple(ranked[:max_entries]))


def serialize_dictionary(dictionary: Dictionary32) -> bytes:
    """Serialize dictionary entries with an authenticated exact byte layout."""
    if not isinstance(dictionary, Dictionary32):
        raise TypeError("dictionary must be Dictionary32")
    entries = b"".join(dictionary.entries)
    return DICTIONARY_HEADER.pack(
        DICTIONARY_MAGIC, DICTIONARY_VERSION, 0, len(dictionary.entries),
        bytes.fromhex(dictionary.sha256),
    ) + entries


def deserialize_dictionary(data: bytes | bytearray | memoryview) -> Dictionary32:
    """Strictly parse a standalone shared dictionary, rejecting any tail."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("dictionary data must be bytes-like")
    raw = bytes(data)
    if len(raw) < DICTIONARY_HEADER.size:
        raise FlatDictionaryError("truncated dictionary header")
    magic, version, flags, count, digest = DICTIONARY_HEADER.unpack_from(raw)
    if magic != DICTIONARY_MAGIC or version != DICTIONARY_VERSION or flags != 0:
        raise FlatDictionaryError("unsupported dictionary header")
    if count > MAX_DICTIONARY_ENTRIES:
        raise FlatDictionaryError("dictionary entry count exceeds 256")
    expected = DICTIONARY_HEADER.size + count * BLOCK_SIZE
    if len(raw) != expected:
        raise FlatDictionaryError("dictionary framing length mismatch")
    dictionary = Dictionary32(tuple(
        raw[offset:offset + BLOCK_SIZE]
        for offset in range(DICTIONARY_HEADER.size, expected, BLOCK_SIZE)
    ))
    if bytes.fromhex(dictionary.sha256) != digest:
        raise FlatDictionaryError("dictionary SHA-256 mismatch")
    return dictionary


def write_dictionary(dictionary: Dictionary32, path: str | Path) -> None:
    """Write deterministic dictionary bytes to a file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(serialize_dictionary(dictionary))
    temporary.replace(destination)


def read_dictionary(path: str | Path, *, max_bytes: int = DICTIONARY_HEADER.size + MAX_DICTIONARY_ENTRIES * BLOCK_SIZE) -> Dictionary32:
    """Read and strictly validate a standalone dictionary file."""
    if not isinstance(max_bytes, int) or max_bytes < DICTIONARY_HEADER.size:
        raise ValueError("max_bytes is too small for a dictionary header")
    source = Path(path)
    if source.stat().st_size > max_bytes:
        raise FlatDictionaryError("dictionary file exceeds configured bounds")
    return deserialize_dictionary(source.read_bytes())


@dataclass(frozen=True)
class CompressionMetrics:
    """Measured codec accounting.

    ``coverage = registered_blocks / full_blocks``;
    ``token_ratio = token_bytes / source_bytes``;
    ``hybrid_ratio = source_bytes / payload_bytes`` (bitmap plus body, with no
    shared dictionary charge); and
    ``dictionary_inclusive_ratio = source_bytes / (encoded_bytes + dictionary_bytes)``.
    """

    source_bytes: int
    full_blocks: int
    tail_bytes: int
    registered_blocks: int
    raw_fallback_blocks: int
    bitmap_bytes: int
    token_bytes: int
    raw_bytes: int
    payload_bytes: int
    framing_bytes: int
    dictionary_bytes: int
    encoded_bytes: int

    @property
    def coverage(self) -> float:
        return self.registered_blocks / self.full_blocks if self.full_blocks else 0.0

    @property
    def token_ratio(self) -> float:
        return self.token_bytes / self.source_bytes if self.source_bytes else 0.0

    @property
    def hybrid_ratio(self) -> float:
        return self.source_bytes / self.payload_bytes if self.payload_bytes else 1.0

    @property
    def dictionary_inclusive_ratio(self) -> float:
        total = self.encoded_bytes + self.dictionary_bytes
        return self.source_bytes / total if total else 1.0


@dataclass(frozen=True)
class _Parsed:
    dictionary_count: int
    source_bytes: int
    block_count: int
    bitmap: bytes
    body: bytes
    tail_bytes: int
    registered_blocks: int
    source_sha256: bytes


def _parse(encoded: bytes, dictionary: Dictionary32, *, max_source_bytes: int,
           max_encoded_bytes: int) -> _Parsed:
    if not isinstance(encoded, (bytes, bytearray, memoryview)):
        raise TypeError("encoded stream must be bytes-like")
    encoded = bytes(encoded)
    if len(encoded) > max_encoded_bytes or len(encoded) < HEADER_SIZE:
        raise FlatDictionaryError("encoded stream exceeds bounds or is truncated")
    magic, version, flags, block_size, dictionary_count, source_bytes, block_count, bitmap_bytes, body_bytes, dictionary_digest, source_digest = HEADER.unpack_from(encoded)
    if magic != MAGIC or version != VERSION or flags != 0 or block_size != BLOCK_SIZE:
        raise FlatDictionaryError("unsupported flat dictionary header")
    if dictionary_count > MAX_DICTIONARY_ENTRIES or dictionary_count != len(dictionary.entries):
        raise FlatDictionaryError("dictionary entry count mismatch")
    if source_bytes > max_source_bytes:
        raise FlatDictionaryError("source exceeds configured bounds")
    expected_blocks = source_bytes // BLOCK_SIZE
    tail_bytes = source_bytes % BLOCK_SIZE
    if block_count != expected_blocks:
        raise FlatDictionaryError("block count does not match source size")
    expected_bitmap_bytes = (block_count + 7) // 8
    if bitmap_bytes != expected_bitmap_bytes:
        raise FlatDictionaryError("bitmap length mismatch")
    end_bitmap = HEADER_SIZE + bitmap_bytes
    end_body = end_bitmap + body_bytes
    if end_body != len(encoded):
        raise FlatDictionaryError("flat dictionary framing length mismatch")
    if dictionary_digest != bytes.fromhex(dictionary.sha256):
        raise FlatDictionaryError("wrong dictionary identity")
    bitmap = encoded[HEADER_SIZE:end_bitmap]
    if block_count and block_count % 8:
        unused = bitmap[-1] >> (block_count % 8)
        if unused:
            raise FlatDictionaryError("non-zero unused bitmap bits")
    registered = sum(int(byte).bit_count() for byte in bitmap)
    expected_body = registered + (block_count - registered) * BLOCK_SIZE + tail_bytes
    if body_bytes != expected_body:
        raise FlatDictionaryError("body length does not match registration bitmap")
    return _Parsed(dictionary_count, source_bytes, block_count, bitmap,
                   encoded[end_bitmap:end_body], tail_bytes, registered, source_digest)


def encode(source: bytes | bytearray | memoryview, dictionary: Dictionary32,
           *, max_source_bytes: int = MAX_SOURCE_BYTES) -> bytes:
    """Encode source bytes exactly against an external shared dictionary."""
    if not isinstance(dictionary, Dictionary32):
        raise TypeError("dictionary must be Dictionary32")
    source = bytes(source)
    max_source_bytes = _validate_limit(max_source_bytes, "max_source_bytes")
    if len(source) > max_source_bytes:
        raise FlatDictionaryError("source exceeds configured bounds")
    block_count, tail_bytes = divmod(len(source), BLOCK_SIZE)
    bitmap = bytearray((block_count + 7) // 8)
    body = bytearray()
    dictionary_index = dictionary.index()
    for index in range(block_count):
        block = source[index * BLOCK_SIZE:(index + 1) * BLOCK_SIZE]
        token = dictionary_index.get(block)
        if token is None:
            body.extend(block)
        else:
            bitmap[index // 8] |= 1 << (index % 8)
            body.append(token)
    body.extend(source[-tail_bytes:] if tail_bytes else b"")
    header = HEADER.pack(
        MAGIC, VERSION, 0, BLOCK_SIZE, len(dictionary.entries), len(source),
        block_count, len(bitmap), len(body), bytes.fromhex(dictionary.sha256),
        hashlib.sha256(source).digest(),
    )
    return header + bytes(bitmap) + bytes(body)


def encode_file(source: str | Path, output: str | Path, dictionary: Dictionary32,
                *, max_source_bytes: int = MAX_SOURCE_BYTES) -> CompressionMetrics:
    """Encode a file with bounded memory and atomically publish the result.

    The source is scanned twice: once to construct the registration bitmap and
    once to emit tokens/raw blocks.  Both passes hash the source; a concurrent
    source mutation is rejected before the temporary output is published.
    """
    if not isinstance(dictionary, Dictionary32):
        raise TypeError("dictionary must be Dictionary32")
    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    if source_path == output_path:
        raise FlatDictionaryError("source and output must be different files")
    max_source_bytes = _validate_limit(max_source_bytes, "max_source_bytes")
    source_bytes = source_path.stat().st_size
    if source_bytes > max_source_bytes:
        raise FlatDictionaryError("source exceeds configured bounds")
    block_count, tail_bytes = divmod(source_bytes, BLOCK_SIZE)
    bitmap = bytearray((block_count + 7) // 8)
    dictionary_index = dictionary.index()
    first_digest = hashlib.sha256()
    registered = 0
    with source_path.open("rb") as handle:
        for index in range(block_count):
            block = handle.read(BLOCK_SIZE)
            if len(block) != BLOCK_SIZE:
                raise FlatDictionaryError("source changed during Flat32 first pass")
            first_digest.update(block)
            if block in dictionary_index:
                bitmap[index // 8] |= 1 << (index % 8)
                registered += 1
        tail = handle.read()
        if len(tail) != tail_bytes:
            raise FlatDictionaryError("source changed during Flat32 first pass")
        first_digest.update(tail)
    body_bytes = registered + (block_count - registered) * BLOCK_SIZE + tail_bytes
    header = HEADER.pack(
        MAGIC, VERSION, 0, BLOCK_SIZE, len(dictionary.entries), source_bytes,
        block_count, len(bitmap), body_bytes, bytes.fromhex(dictionary.sha256),
        first_digest.digest(),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    second_digest = hashlib.sha256()
    try:
        with source_path.open("rb") as input_handle, temporary.open("wb") as output_handle:
            output_handle.write(header)
            output_handle.write(bitmap)
            for index in range(block_count):
                block = input_handle.read(BLOCK_SIZE)
                if len(block) != BLOCK_SIZE:
                    raise FlatDictionaryError("source changed during Flat32 second pass")
                second_digest.update(block)
                token = dictionary_index.get(block)
                if token is None:
                    output_handle.write(block)
                else:
                    output_handle.write(bytes((token,)))
            tail = input_handle.read()
            if len(tail) != tail_bytes:
                raise FlatDictionaryError("source changed during Flat32 second pass")
            second_digest.update(tail)
            output_handle.write(tail)
        if second_digest.digest() != first_digest.digest():
            raise FlatDictionaryError("source changed between Flat32 passes")
        if temporary.stat().st_size != HEADER_SIZE + len(bitmap) + body_bytes:
            raise FlatDictionaryError("Flat32 output length mismatch")
        temporary.replace(output_path)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    raw_blocks = block_count - registered
    return CompressionMetrics(
        source_bytes=source_bytes,
        full_blocks=block_count,
        tail_bytes=tail_bytes,
        registered_blocks=registered,
        raw_fallback_blocks=raw_blocks,
        bitmap_bytes=len(bitmap),
        token_bytes=registered,
        raw_bytes=raw_blocks * BLOCK_SIZE,
        payload_bytes=len(bitmap) + body_bytes,
        framing_bytes=HEADER_SIZE,
        dictionary_bytes=dictionary.bytes,
        encoded_bytes=HEADER_SIZE + len(bitmap) + body_bytes,
    )


def decode(encoded: bytes | bytearray | memoryview, dictionary: Dictionary32,
           *, max_source_bytes: int = MAX_SOURCE_BYTES,
           max_encoded_bytes: int = MAX_ENCODED_BYTES) -> bytes:
    """Fail-closed exact decoder requiring the matching immutable dictionary."""
    if not isinstance(dictionary, Dictionary32):
        raise TypeError("dictionary must be Dictionary32")
    max_source_bytes = _validate_limit(max_source_bytes, "max_source_bytes")
    max_encoded_bytes = _validate_limit(max_encoded_bytes, "max_encoded_bytes")
    parsed = _parse(bytes(encoded), dictionary, max_source_bytes=max_source_bytes,
                    max_encoded_bytes=max_encoded_bytes)
    output = bytearray(parsed.source_bytes)
    body_offset = 0
    dictionary_entries = dictionary.entries
    for index in range(parsed.block_count):
        destination = index * BLOCK_SIZE
        if parsed.bitmap[index // 8] & (1 << (index % 8)):
            if body_offset >= len(parsed.body):
                raise FlatDictionaryError("truncated dictionary token stream")
            token = parsed.body[body_offset]
            body_offset += 1
            if token >= len(dictionary_entries):
                raise FlatDictionaryError("dictionary token outside dictionary")
            output[destination:destination + BLOCK_SIZE] = dictionary_entries[token]
        else:
            end = body_offset + BLOCK_SIZE
            if end > len(parsed.body):
                raise FlatDictionaryError("truncated raw fallback block")
            output[destination:destination + BLOCK_SIZE] = parsed.body[body_offset:end]
            body_offset = end
    if parsed.tail_bytes:
        end = body_offset + parsed.tail_bytes
        if end != len(parsed.body):
            raise FlatDictionaryError("tail framing mismatch")
        output[-parsed.tail_bytes:] = parsed.body[body_offset:end]
        body_offset = end
    if body_offset != len(parsed.body):
        raise FlatDictionaryError("unexpected trailing block payload")
    result = bytes(output)
    if hashlib.sha256(result).digest() != parsed.source_sha256:
        raise FlatDictionaryError("source SHA-256 mismatch")
    return result


def metrics(encoded: bytes | bytearray | memoryview, dictionary: Dictionary32,
            *, max_source_bytes: int = MAX_SOURCE_BYTES,
            max_encoded_bytes: int = MAX_ENCODED_BYTES) -> CompressionMetrics:
    """Return measured coverage and payload/dictionary-inclusive ratios."""
    max_source_bytes = _validate_limit(max_source_bytes, "max_source_bytes")
    max_encoded_bytes = _validate_limit(max_encoded_bytes, "max_encoded_bytes")
    parsed = _parse(bytes(encoded), dictionary, max_source_bytes=max_source_bytes,
                    max_encoded_bytes=max_encoded_bytes)
    raw_blocks = parsed.block_count - parsed.registered_blocks
    return CompressionMetrics(
        source_bytes=parsed.source_bytes,
        full_blocks=parsed.block_count,
        tail_bytes=parsed.tail_bytes,
        registered_blocks=parsed.registered_blocks,
        raw_fallback_blocks=raw_blocks,
        bitmap_bytes=len(parsed.bitmap),
        token_bytes=parsed.registered_blocks,
        raw_bytes=raw_blocks * BLOCK_SIZE,
        payload_bytes=len(parsed.bitmap) + len(parsed.body),
        framing_bytes=HEADER_SIZE,
        dictionary_bytes=dictionary.bytes,
        encoded_bytes=len(bytes(encoded)),
    )


__all__ = [
    "BLOCK_SIZE", "CompressionMetrics", "Dictionary32", "FlatDictionaryError",
    "MAX_DICTIONARY_ENTRIES", "decode", "deserialize_dictionary", "encode", "encode_file", "metrics",
    "read_dictionary", "serialize_dictionary", "train_dictionary", "train_dictionary_bounded",
    "write_dictionary",
]
