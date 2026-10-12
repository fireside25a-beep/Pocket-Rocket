"""Deterministic, bounded outer container for NPRQ stage bytes.

Pocket Rocket is deliberately lossless: it wraps existing stage bytes in
independently addressable chunks and never changes the bytes returned by a
reader.  Each chunk is stored with zlib only when compression makes it
strictly smaller; otherwise the original bytes are stored verbatim.

The container is not a model format and does not claim a model-size ratio.
It is a transport/page container with authenticated metadata, strict file
bounds, and bounded decompression.
"""
from __future__ import annotations

import hashlib
import io
import os
import struct
import tempfile
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


MAGIC = b"NRPQR001"
VERSION = 1
HEADER_STRUCT = struct.Struct("<8sHHIQQ32s")
ENTRY_STRUCT = struct.Struct("<QQQIB3x32s")
HEADER_SIZE = HEADER_STRUCT.size
ENTRY_SIZE = ENTRY_STRUCT.size
CODEC_RAW = 0
CODEC_ZLIB = 1
MAX_CHUNK_SIZE = 64 * 1024 * 1024
DEFAULT_MAX_SOURCE_BYTES = 128 * 1024 * 1024 * 1024
DEFAULT_MAX_RANGE_BYTES = 256 * 1024 * 1024


class PocketRocketError(ValueError):
    """Raised for malformed containers, bounds violations, or bad hashes."""


@dataclass(frozen=True)
class ChunkInfo:
    index: int
    offset: int
    stored_bytes: int
    raw_bytes: int
    crc32: int
    codec: int
    sha256: bytes


@dataclass(frozen=True)
class ContainerInfo:
    source_bytes: int
    chunk_size: int
    chunk_count: int
    source_sha256: str
    container_bytes: int


def _checked_chunk_size(chunk_size: int) -> int:
    if not isinstance(chunk_size, int) or isinstance(chunk_size, bool):
        raise ValueError("chunk_size must be an integer")
    if not 1 <= chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError(f"chunk_size must be between 1 and {MAX_CHUNK_SIZE}")
    return chunk_size


def _checked_limit(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@contextmanager
def _open_source(source: bytes | bytearray | memoryview | str | Path | BinaryIO):
    if isinstance(source, (bytes, bytearray, memoryview)):
        yield io.BytesIO(bytes(source))
        return
    if isinstance(source, (str, Path)):
        with Path(source).open("rb") as handle:
            yield handle
        return
    if not hasattr(source, "read"):
        raise TypeError("source must be bytes, a path, or a binary reader")
    yield source


def _read_chunks(handle: BinaryIO, chunk_size: int) -> Iterator[bytes]:
    while True:
        chunk = handle.read(chunk_size)
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError("source reader must return bytes")
        if not chunk:
            return
        yield bytes(chunk)


def pack(
    source: bytes | bytearray | memoryview | str | Path | BinaryIO,
    output: str | Path,
    *,
    chunk_size: int = 1 * 1024 * 1024,
    zlib_level: int = 9,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> ContainerInfo:
    """Pack *source* into a deterministic Pocket Rocket container.

    The source is read once into a temporary payload spool; no complete source
    or decompressed chunk is duplicated in memory.  Compression is selected
    independently for every chunk and only when the zlib payload is smaller.
    """
    chunk_size = _checked_chunk_size(chunk_size)
    max_source_bytes = _checked_limit(max_source_bytes, "max_source_bytes")
    if not isinstance(zlib_level, int) or not 0 <= zlib_level <= 9:
        raise ValueError("zlib_level must be between 0 and 9")
    destination = Path(output)
    if isinstance(source, (str, Path)):
        source_path = Path(source)
        try:
            aliases_source = source_path.resolve() == destination.resolve()
            if destination.exists():
                aliases_source = aliases_source or source_path.samefile(destination)
        except OSError as exc:
            raise PocketRocketError("cannot establish source/output identity") from exc
        if aliases_source:
            raise PocketRocketError("output aliases the source file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_digest = hashlib.sha256()
    source_bytes = 0
    entries: list[tuple[int, int, int, int, int, bytes]] = []
    with tempfile.TemporaryFile(mode="w+b") as spool:
        payload_relative = 0
        with _open_source(source) as handle:
            for index, raw in enumerate(_read_chunks(handle, chunk_size)):
                source_bytes += len(raw)
                if source_bytes > max_source_bytes:
                    raise PocketRocketError("source exceeds configured size limit")
                source_digest.update(raw)
                compressed = zlib.compress(raw, level=zlib_level)
                if len(compressed) < len(raw):
                    stored, codec = compressed, CODEC_ZLIB
                else:
                    stored, codec = raw, CODEC_RAW
                crc = zlib.crc32(raw) & 0xFFFFFFFF
                digest = hashlib.sha256(raw).digest()
                spool.write(stored)
                entries.append((payload_relative, len(stored), len(raw), crc, codec, digest))
                payload_relative += len(stored)
        chunk_count = len(entries)
        expected_count = (source_bytes + chunk_size - 1) // chunk_size if source_bytes else 0
        if chunk_count != expected_count:
            raise PocketRocketError("internal chunk count mismatch")
        payload_start = HEADER_SIZE + ENTRY_SIZE * chunk_count
        header = HEADER_STRUCT.pack(
            MAGIC, VERSION, 0, chunk_size, source_bytes, chunk_count, source_digest.digest()
        )
        table = bytearray()
        for index, (relative, stored_bytes, raw_bytes, crc, codec, digest) in enumerate(entries):
            absolute = payload_start + relative
            table.extend(ENTRY_STRUCT.pack(absolute, stored_bytes, raw_bytes, crc, codec, digest))
        spool.flush()
        spool.seek(0)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=destination.name + ".", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(header)
                target.write(table)
                while True:
                    block = spool.read(8 * 1024 * 1024)
                    if not block:
                        break
                    target.write(block)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
    return ContainerInfo(
        source_bytes, chunk_size, chunk_count, source_digest.hexdigest(), destination.stat().st_size
    )


class PocketRocketReader:
    """Strict random-access reader with bounded zlib expansion."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
        max_chunk_bytes: int = MAX_CHUNK_SIZE,
        max_range_bytes: int = DEFAULT_MAX_RANGE_BYTES,
    ) -> None:
        self.path = Path(path)
        self.max_source_bytes = _checked_limit(max_source_bytes, "max_source_bytes")
        self.max_chunk_bytes = _checked_chunk_size(max_chunk_bytes)
        self.max_range_bytes = _checked_limit(max_range_bytes, "max_range_bytes")
        try:
            self._handle = self.path.open("rb")
            self._file_size = os.fstat(self._handle.fileno()).st_size
            self._info, self._chunks = self._read_index()
        except Exception:
            if hasattr(self, "_handle"):
                self._handle.close()
            raise

    def __enter__(self) -> "PocketRocketReader":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        if getattr(self, "_handle", None) is not None:
            self._handle.close()
            self._handle = None

    @property
    def info(self) -> ContainerInfo:
        return self._info

    @property
    def chunks(self) -> tuple[ChunkInfo, ...]:
        return self._chunks

    def _read_exact(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset > self._file_size - length:
            raise PocketRocketError("container read exceeds file bounds")
        self._handle.seek(offset)
        data = self._handle.read(length)
        if len(data) != length:
            raise PocketRocketError("truncated container")
        return data

    def _read_index(self) -> tuple[ContainerInfo, tuple[ChunkInfo, ...]]:
        if self._file_size < HEADER_SIZE:
            raise PocketRocketError("truncated Pocket Rocket header")
        raw_header = self._read_exact(0, HEADER_SIZE)
        magic, version, flags, chunk_size, source_bytes, chunk_count, source_digest = HEADER_STRUCT.unpack(raw_header)
        if magic != MAGIC or version != VERSION or flags != 0:
            raise PocketRocketError("unsupported Pocket Rocket header")
        if chunk_size < 1 or chunk_size > self.max_chunk_bytes or chunk_size > MAX_CHUNK_SIZE:
            raise PocketRocketError("chunk size exceeds reader bounds")
        if source_bytes > self.max_source_bytes:
            raise PocketRocketError("source size exceeds reader bounds")
        expected_count = (source_bytes + chunk_size - 1) // chunk_size if source_bytes else 0
        if chunk_count != expected_count:
            raise PocketRocketError("chunk count does not match source size")
        table_bytes = ENTRY_SIZE * chunk_count
        payload_start = HEADER_SIZE + table_bytes
        if payload_start > self._file_size:
            raise PocketRocketError("truncated Pocket Rocket index")
        chunks: list[ChunkInfo] = []
        previous_end = payload_start
        for index in range(chunk_count):
            row = self._read_exact(HEADER_SIZE + index * ENTRY_SIZE, ENTRY_SIZE)
            offset, stored_bytes, raw_bytes, crc, codec, digest = ENTRY_STRUCT.unpack(row)
            expected_raw = min(chunk_size, source_bytes - index * chunk_size)
            if raw_bytes != expected_raw or raw_bytes < 1:
                raise PocketRocketError("invalid chunk raw length")
            if stored_bytes < 1 or offset != previous_end:
                raise PocketRocketError("non-contiguous or empty chunk payload")
            if codec not in (CODEC_RAW, CODEC_ZLIB):
                raise PocketRocketError("unknown chunk codec")
            if codec == CODEC_RAW and stored_bytes != raw_bytes:
                raise PocketRocketError("raw chunk length mismatch")
            if codec == CODEC_ZLIB and stored_bytes >= raw_bytes:
                raise PocketRocketError("zlib chunk was not smaller than raw data")
            if offset > self._file_size - stored_bytes:
                raise PocketRocketError("chunk payload exceeds file bounds")
            previous_end = offset + stored_bytes
            chunks.append(ChunkInfo(index, offset, stored_bytes, raw_bytes, crc, codec, digest))
        if previous_end != self._file_size:
            raise PocketRocketError("unexpected trailing container bytes")
        return ContainerInfo(
            source_bytes, chunk_size, chunk_count, source_digest.hex(), self._file_size
        ), tuple(chunks)

    def _decode(self, chunk: ChunkInfo) -> bytes:
        stored = self._read_exact(chunk.offset, chunk.stored_bytes)
        if chunk.codec == CODEC_RAW:
            raw = stored
        else:
            decompressor = zlib.decompressobj()
            try:
                raw = decompressor.decompress(stored, chunk.raw_bytes + 1)
                if len(raw) > chunk.raw_bytes or decompressor.unconsumed_tail:
                    raise PocketRocketError("chunk decompression exceeds declared bound")
                raw += decompressor.flush(chunk.raw_bytes + 1 - len(raw))
            except zlib.error as exc:
                raise PocketRocketError("invalid zlib chunk") from exc
            if len(raw) > chunk.raw_bytes or not decompressor.eof or decompressor.unused_data:
                raise PocketRocketError("invalid or oversized zlib chunk")
        if len(raw) != chunk.raw_bytes:
            raise PocketRocketError("chunk decompressed length mismatch")
        if (zlib.crc32(raw) & 0xFFFFFFFF) != chunk.crc32:
            raise PocketRocketError("chunk CRC mismatch")
        if hashlib.sha256(raw).digest() != chunk.sha256:
            raise PocketRocketError("chunk SHA-256 mismatch")
        return raw

    def read_chunk(self, index: int) -> bytes:
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(self._chunks):
            raise IndexError("chunk index outside container")
        return self._decode(self._chunks[index])

    def read_range(self, offset: int, length: int) -> bytes:
        if not isinstance(offset, int) or not isinstance(length, int) or offset < 0 or length < 0:
            raise ValueError("range offset and length must be non-negative integers")
        if length > self.max_range_bytes or offset > self._info.source_bytes - length:
            raise PocketRocketError("requested range exceeds reader bounds")
        if length == 0:
            return b""
        first = offset // self._info.chunk_size
        last = (offset + length - 1) // self._info.chunk_size
        result = bytearray()
        for index in range(first, last + 1):
            result.extend(self.read_chunk(index))
        start = offset - first * self._info.chunk_size
        return bytes(result[start:start + length])

    def iter_chunks(self) -> Iterator[bytes]:
        for index in range(len(self._chunks)):
            yield self.read_chunk(index)

    def verify(self) -> None:
        digest = hashlib.sha256()
        total = 0
        for raw in self.iter_chunks():
            digest.update(raw)
            total += len(raw)
        if total != self._info.source_bytes or digest.hexdigest() != self._info.source_sha256:
            raise PocketRocketError("whole-source SHA-256 mismatch")


def open_container(path: str | Path, **kwargs: int) -> PocketRocketReader:
    """Open and strictly index a Pocket Rocket container."""
    return PocketRocketReader(path, **kwargs)


pack_nprq_stage = pack


__all__ = [
    "CODEC_RAW", "CODEC_ZLIB", "ChunkInfo", "ContainerInfo", "PocketRocketError",
    "PocketRocketReader", "open_container", "pack", "pack_nprq_stage",
]
