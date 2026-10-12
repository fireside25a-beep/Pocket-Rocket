"""Content-addressed, demand-materialised pages for the pinned model.

Static and demand modes share one manifest and therefore one model root.  The
manifest authenticates raw pages.  Local storage measures raw, DEFLATE, and
2/4/8-byte shuffle plus DEFLATE encodings and commits the exact smallest page,
with a stable codec-ID tie break.  Decoding is always bounded by the
authenticated raw length.  This is a storage transform, not a claim that an
already-quantised GGUF becomes materially smaller.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
import tempfile
import zlib
from dataclasses import dataclass
from math import gcd
from pathlib import Path
from typing import BinaryIO, Iterator


MANIFEST_FORMAT = "pocket-model-pages-v1"
PAGE_MAGIC = b"PRPG0002"
LEGACY_PAGE_MAGIC = b"PRPG0001"
PAGE_HEADER = struct.Struct("<8sB7xQ32s")
CODEC_RAW = 0
CODEC_ZLIB = 1
CODEC_SHUFFLE2_ZLIB = 2
CODEC_SHUFFLE4_ZLIB = 3
CODEC_SHUFFLE8_ZLIB = 4
CODEC_NAMES = {
    CODEC_RAW: "raw",
    CODEC_ZLIB: "deflate",
    CODEC_SHUFFLE2_ZLIB: "shuffle2-deflate",
    CODEC_SHUFFLE4_ZLIB: "shuffle4-deflate",
    CODEC_SHUFFLE8_ZLIB: "shuffle8-deflate",
}
SHUFFLE_WIDTHS = {
    CODEC_SHUFFLE2_ZLIB: 2,
    CODEC_SHUFFLE4_ZLIB: 4,
    CODEC_SHUFFLE8_ZLIB: 8,
}
DEFAULT_PAGE_BYTES = 1 * 1024 * 1024
MIN_PAGE_BYTES = 64 * 1024
MAX_PAGE_BYTES = 64 * 1024 * 1024
MAX_MODEL_BYTES = 128 * 1024 * 1024 * 1024
MAX_RANGE_BYTES = 256 * 1024 * 1024


class ModelPageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PageEncoding:
    codec: int
    payload: bytes
    candidates: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class CompressionReport:
    source_bytes: int
    stored_bytes: int
    pages: int
    codecs: tuple[tuple[str, int], ...]
    decision_root: str

    def as_dict(self) -> dict[str, object]:
        if self.source_bytes == 0 and self.stored_bytes == 0:
            ratio_numerator, ratio_denominator = 1, 1
        else:
            divisor = gcd(self.source_bytes, self.stored_bytes)
            ratio_numerator = self.source_bytes // divisor
            ratio_denominator = self.stored_bytes // divisor
        return {
            "source_bytes": self.source_bytes,
            "stored_bytes": self.stored_bytes,
            "pages": self.pages,
            "codecs": dict(self.codecs),
            "exact_source_to_stored_ratio": {
                "numerator": ratio_numerator,
                "denominator": ratio_denominator,
            },
            "decision_root": self.decision_root,
        }


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _validate_digest(text: str, name: str) -> str:
    if not isinstance(text, str) or len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise ModelPageError(f"{name} must be lowercase SHA-256")
    return text


def _validate_page_bytes(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("page_bytes must be an integer")
    if not MIN_PAGE_BYTES <= value <= MAX_PAGE_BYTES or value & (value - 1):
        raise ModelPageError("page_bytes must be a power of two from 64 KiB through 64 MiB")
    return value


def _open_regular_binary(path: Path, label: str) -> BinaryIO:
    if path.is_symlink():
        raise ModelPageError(f"{label} must not be a symbolic link")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ModelPageError(f"cannot open {label}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ModelPageError(f"{label} must be a regular file")
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def _read_bounded_file(path: Path, limit: int, label: str) -> bytes:
    with _open_regular_binary(path, label) as handle:
        size = os.fstat(handle.fileno()).st_size
        if size < 0 or size > limit:
            raise ModelPageError(f"{label} exceeds its storage bound")
        data = handle.read(limit + 1)
        if len(data) != size or len(data) > limit:
            raise ModelPageError(f"{label} changed or exceeds its storage bound")
        return data


def byte_shuffle(data: bytes, width: int) -> bytes:
    """Group equal byte lanes of fixed-width elements; preserve any tail."""
    if width not in (2, 4, 8):
        raise ModelPageError("shuffle width must be 2, 4, or 8")
    elements = len(data) // width
    body = elements * width
    output = bytearray(len(data))
    for lane in range(width):
        start = lane * elements
        output[start:start + elements] = data[lane:body:width]
    output[body:] = data[body:]
    return bytes(output)


def byte_unshuffle(data: bytes, width: int) -> bytes:
    if width not in (2, 4, 8):
        raise ModelPageError("shuffle width must be 2, 4, or 8")
    elements = len(data) // width
    body = elements * width
    output = bytearray(len(data))
    for lane in range(width):
        start = lane * elements
        output[lane:body:width] = data[start:start + elements]
    output[body:] = data[body:]
    return bytes(output)


def select_page_encoding(raw: bytes) -> PageEncoding:
    """Run every admitted lossless encoding and select exact smallest bytes."""
    candidates: list[tuple[int, bytes]] = [(CODEC_RAW, raw)]
    candidates.append((CODEC_ZLIB, zlib.compress(raw, level=6)))
    for codec in (CODEC_SHUFFLE2_ZLIB, CODEC_SHUFFLE4_ZLIB, CODEC_SHUFFLE8_ZLIB):
        shuffled = byte_shuffle(raw, SHUFFLE_WIDTHS[codec])
        candidates.append((codec, zlib.compress(shuffled, level=6)))
    codec, payload = min(candidates, key=lambda item: (len(item[1]), item[0]))
    sizes = tuple((CODEC_NAMES[item_codec], len(item_payload)) for item_codec, item_payload in candidates)
    return PageEncoding(codec, payload, sizes)


@dataclass(frozen=True, slots=True)
class Page:
    index: int
    raw_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.index, int) or isinstance(self.index, bool) or self.index < 0:
            raise ModelPageError("invalid page index")
        if not isinstance(self.raw_bytes, int) or isinstance(self.raw_bytes, bool) or self.raw_bytes < 1:
            raise ModelPageError("invalid page length")
        _validate_digest(self.sha256, "page sha256")


@dataclass(frozen=True, slots=True)
class ModelManifest:
    source_bytes: int
    page_bytes: int
    source_sha256: str
    model_root: str
    pages: tuple[Page, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_bytes, int) or isinstance(self.source_bytes, bool):
            raise TypeError("source_bytes must be an integer")
        if not 0 <= self.source_bytes <= MAX_MODEL_BYTES:
            raise ModelPageError("source size exceeds the 128 GiB model bound")
        _validate_page_bytes(self.page_bytes)
        _validate_digest(self.source_sha256, "source sha256")
        _validate_digest(self.model_root, "model root")
        expected_count = (self.source_bytes + self.page_bytes - 1) // self.page_bytes
        if len(self.pages) != expected_count:
            raise ModelPageError("manifest page count does not match source size")
        for index, page in enumerate(self.pages):
            expected = min(self.page_bytes, self.source_bytes - index * self.page_bytes)
            if page.index != index or page.raw_bytes != expected:
                raise ModelPageError("manifest page order or length is non-canonical")
        if calculate_model_root(
            self.source_bytes, self.page_bytes, self.source_sha256, self.pages
        ) != self.model_root:
            raise ModelPageError("manifest model root mismatch")

    def as_dict(self) -> dict[str, object]:
        return {
            "format": MANIFEST_FORMAT,
            "source_bytes": self.source_bytes,
            "page_bytes": self.page_bytes,
            "source_sha256": self.source_sha256,
            "model_root": self.model_root,
            "pages": [
                {"index": page.index, "raw_bytes": page.raw_bytes, "sha256": page.sha256}
                for page in self.pages
            ],
        }

    def write(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode()
        _atomic_write(destination, encoded)

    @classmethod
    def read(cls, path: str | Path) -> "ModelManifest":
        raw = _read_bounded_file(Path(path), 64 * 1024 * 1024, "model manifest")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelPageError("invalid model manifest JSON") from exc
        if not isinstance(payload, dict) or payload.get("format") != MANIFEST_FORMAT:
            raise ModelPageError("unsupported model manifest")
        expected_keys = {
            "format", "source_bytes", "page_bytes", "source_sha256", "model_root", "pages"
        }
        if set(payload) != expected_keys or not isinstance(payload["pages"], list):
            raise ModelPageError("non-canonical model manifest fields")
        pages = []
        for row in payload["pages"]:
            if not isinstance(row, dict) or set(row) != {"index", "raw_bytes", "sha256"}:
                raise ModelPageError("invalid page manifest row")
            pages.append(Page(row["index"], row["raw_bytes"], row["sha256"]))
        return cls(
            payload["source_bytes"], payload["page_bytes"], payload["source_sha256"],
            payload["model_root"], tuple(pages)
        )


def calculate_model_root(
    source_bytes: int, page_bytes: int, source_sha256: str, pages: tuple[Page, ...]
) -> str:
    leaves = [
        _sha256(
            b"pocket-page-leaf-v1\0"
            + page.index.to_bytes(8, "little")
            + page.raw_bytes.to_bytes(8, "little")
            + bytes.fromhex(page.sha256)
        )
        for page in pages
    ]
    if not leaves:
        tree = _sha256(b"pocket-empty-tree-v1\0")
    else:
        while len(leaves) > 1:
            if len(leaves) & 1:
                leaves.append(leaves[-1])
            leaves = [
                _sha256(b"pocket-page-node-v1\0" + leaves[i] + leaves[i + 1])
                for i in range(0, len(leaves), 2)
            ]
        tree = leaves[0]
    return hashlib.sha256(
        b"pocket-model-root-v1\0"
        + source_bytes.to_bytes(8, "little")
        + page_bytes.to_bytes(8, "little")
        + len(pages).to_bytes(8, "little")
        + bytes.fromhex(source_sha256)
        + tree
    ).hexdigest()


def _read_pages(handle: BinaryIO, page_bytes: int) -> Iterator[bytes]:
    while True:
        page = handle.read(page_bytes)
        if not isinstance(page, bytes):
            raise TypeError("binary source reader must return bytes")
        if not page:
            return
        yield page


def build_manifest(source: str | Path, *, page_bytes: int = DEFAULT_PAGE_BYTES) -> ModelManifest:
    page_bytes = _validate_page_bytes(page_bytes)
    path = Path(source)
    source_digest = hashlib.sha256()
    pages: list[Page] = []
    actual_size = 0
    with _open_regular_binary(path, "model source") as handle:
        declared_size = os.fstat(handle.fileno()).st_size
        if not 0 <= declared_size <= MAX_MODEL_BYTES:
            raise ModelPageError("source exceeds the 128 GiB model bound")
        for index, data in enumerate(_read_pages(handle, page_bytes)):
            actual_size += len(data)
            if actual_size > MAX_MODEL_BYTES:
                raise ModelPageError("source changed beyond the model bound during hashing")
            source_digest.update(data)
            pages.append(Page(index, len(data), hashlib.sha256(data).hexdigest()))
    if actual_size != declared_size:
        raise ModelPageError("source size changed while building its manifest")
    source_sha = source_digest.hexdigest()
    frozen_pages = tuple(pages)
    root = calculate_model_root(actual_size, page_bytes, source_sha, frozen_pages)
    return ModelManifest(actual_size, page_bytes, source_sha, root, frozen_pages)


def _atomic_write(path: Path, data: bytes) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ModelPageError("atomic output path must not contain a terminal symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _encode_page(raw: bytes, expected: Page) -> bytes:
    if len(raw) != expected.raw_bytes or hashlib.sha256(raw).hexdigest() != expected.sha256:
        raise ModelPageError(f"source page {expected.index} failed manifest authentication")
    selected = select_page_encoding(raw)
    return (
        PAGE_HEADER.pack(
            PAGE_MAGIC, selected.codec, len(raw), bytes.fromhex(expected.sha256)
        )
        + selected.payload
    )


def _decompress_exact(payload: bytes, raw_bytes: int) -> bytes:
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(payload, raw_bytes + 1)
        if len(raw) > raw_bytes or decoder.unconsumed_tail:
            raise ModelPageError("compressed page exceeds its authenticated bound")
        raw += decoder.flush(raw_bytes + 1 - len(raw))
    except zlib.error as exc:
        raise ModelPageError("invalid compressed page") from exc
    if len(raw) != raw_bytes or decoder.unconsumed_tail or decoder.unused_data or not decoder.eof:
        raise ModelPageError("compressed page exceeds or misses its authenticated bound")
    return raw


def _decode_page(encoded: bytes, expected: Page) -> bytes:
    if len(encoded) < PAGE_HEADER.size:
        raise ModelPageError("truncated stored page")
    magic, codec, raw_bytes, digest = PAGE_HEADER.unpack(encoded[:PAGE_HEADER.size])
    if magic not in (PAGE_MAGIC, LEGACY_PAGE_MAGIC):
        raise ModelPageError("stored page magic mismatch")
    if raw_bytes != expected.raw_bytes or digest.hex() != expected.sha256:
        raise ModelPageError("stored page header mismatch")
    if magic == LEGACY_PAGE_MAGIC and codec not in (CODEC_RAW, CODEC_ZLIB):
        raise ModelPageError("legacy page uses an unsupported codec")
    payload = encoded[PAGE_HEADER.size:]
    if codec == CODEC_RAW:
        if len(payload) != raw_bytes:
            raise ModelPageError("raw stored page length mismatch")
        raw = payload
    elif codec == CODEC_ZLIB:
        raw = _decompress_exact(payload, raw_bytes)
    elif codec in SHUFFLE_WIDTHS:
        raw = byte_unshuffle(_decompress_exact(payload, raw_bytes), SHUFFLE_WIDTHS[codec])
    else:
        raise ModelPageError("unknown stored page codec")
    if hashlib.sha256(raw).hexdigest() != expected.sha256:
        raise ModelPageError("stored page SHA-256 mismatch")
    return raw


def analyze_compression(source: str | Path, manifest: ModelManifest) -> CompressionReport:
    """Measure the exact canonical page competition without publishing cache files."""
    path = Path(source)
    codec_counts = {name: 0 for name in CODEC_NAMES.values()}
    stored_bytes = 0
    source_digest = hashlib.sha256()
    decisions = hashlib.sha256(b"pocket-codec-decisions-v1\0")
    with _open_regular_binary(path, "model source") as handle:
        if os.fstat(handle.fileno()).st_size != manifest.source_bytes:
            raise ModelPageError("model source size does not match manifest")
        for page in manifest.pages:
            raw = handle.read(page.raw_bytes)
            if len(raw) != page.raw_bytes or hashlib.sha256(raw).hexdigest() != page.sha256:
                raise ModelPageError(f"source page {page.index} failed manifest authentication")
            source_digest.update(raw)
            selected = select_page_encoding(raw)
            encoded_bytes = PAGE_HEADER.size + len(selected.payload)
            codec_counts[CODEC_NAMES[selected.codec]] += 1
            stored_bytes += encoded_bytes
            decisions.update(page.index.to_bytes(8, "little"))
            decisions.update(page.raw_bytes.to_bytes(8, "little"))
            decisions.update(selected.codec.to_bytes(1, "little"))
            decisions.update(encoded_bytes.to_bytes(8, "little"))
            for _, candidate_bytes in selected.candidates:
                decisions.update(candidate_bytes.to_bytes(8, "little"))
        if handle.read(1):
            raise ModelPageError("model source grew during compression analysis")
    if source_digest.hexdigest() != manifest.source_sha256:
        raise ModelPageError("model source digest does not match manifest")
    return CompressionReport(
        manifest.source_bytes,
        stored_bytes,
        len(manifest.pages),
        tuple((name, codec_counts[name]) for name in CODEC_NAMES.values()),
        decisions.hexdigest(),
    )


class ModelPageStore:
    """Authenticated page cache with static and demand materialisation."""

    def __init__(self, root: str | Path, manifest: ModelManifest, source: str | Path | None = None):
        requested_root = Path(root)
        if requested_root.is_symlink():
            raise ModelPageError("page-store root must not be a symbolic link")
        requested_root.mkdir(parents=True, exist_ok=True)
        self.root = requested_root.resolve()
        self.manifest = manifest
        self.source = None if source is None else Path(source)
        if self.source is not None and self.source.is_symlink():
            raise ModelPageError("model source must not be a symbolic link")
        self.objects = self.root / "objects"
        if self.objects.is_symlink():
            raise ModelPageError("page-store objects directory must not be a symbolic link")
        self.objects.mkdir(parents=True, exist_ok=True)
        if self.objects.resolve().parent != self.root:
            raise ModelPageError("page-store objects directory escaped its root")

    def _object_path(self, page: Page) -> Path:
        directory = self.objects / page.sha256[:2]
        if directory.is_symlink():
            raise ModelPageError("page-store shard must not be a symbolic link")
        directory.mkdir(parents=False, exist_ok=True)
        if directory.resolve().parent != self.objects:
            raise ModelPageError("page-store shard escaped its root")
        return directory / (page.sha256 + ".prpg")

    @staticmethod
    def _exists_regular(path: Path) -> bool:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(metadata.st_mode):
            raise ModelPageError("stored page must be a regular file")
        return True

    @staticmethod
    def _read_stored(path: Path, page: Page) -> bytes:
        maximum = PAGE_HEADER.size + page.raw_bytes
        return _read_bounded_file(path, maximum, "stored page")

    def has_page(self, index: int) -> bool:
        page = self._page(index)
        return self._exists_regular(self._object_path(page))

    def _page(self, index: int) -> Page:
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(self.manifest.pages):
            raise ModelPageError("page index out of range")
        return self.manifest.pages[index]

    def _source_page(self, page: Page) -> bytes:
        if self.source is None:
            raise ModelPageError("missing demand source for uncached page")
        with _open_regular_binary(self.source, "model source") as handle:
            handle.seek(page.index * self.manifest.page_bytes)
            raw = handle.read(page.raw_bytes)
        if len(raw) != page.raw_bytes or hashlib.sha256(raw).hexdigest() != page.sha256:
            raise ModelPageError(f"demand source page {page.index} does not match manifest")
        return raw

    def materialize(self, index: int) -> Path:
        page = self._page(index)
        destination = self._object_path(page)
        if self._exists_regular(destination):
            _decode_page(self._read_stored(destination, page), page)
            return destination
        encoded = _encode_page(self._source_page(page), page)
        _atomic_write(destination, encoded)
        return destination

    def materialize_all(self) -> int:
        for page in self.manifest.pages:
            self.materialize(page.index)
        return len(self.manifest.pages)

    def read_page(self, index: int) -> bytes:
        page = self._page(index)
        destination = self.materialize(index)
        return _decode_page(self._read_stored(destination, page), page)

    def read_range(self, offset: int, length: int) -> bytes:
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ModelPageError("range offset must be a non-negative integer")
        if not isinstance(length, int) or isinstance(length, bool) or not 0 <= length <= MAX_RANGE_BYTES:
            raise ModelPageError("range length exceeds the 256 MiB bound")
        if offset > self.manifest.source_bytes or length > self.manifest.source_bytes - offset:
            raise ModelPageError("range exceeds model bounds")
        if length == 0:
            return b""
        first = offset // self.manifest.page_bytes
        last = (offset + length - 1) // self.manifest.page_bytes
        output = bytearray()
        for index in range(first, last + 1):
            page = self.read_page(index)
            begin = offset % self.manifest.page_bytes if index == first else 0
            remaining = length - len(output)
            output.extend(page[begin:begin + remaining])
        if len(output) != length:
            raise ModelPageError("internal range assembly mismatch")
        return bytes(output)

    def verify_cached(self) -> tuple[int, int]:
        present = 0
        for page in self.manifest.pages:
            destination = self._object_path(page)
            if self._exists_regular(destination):
                _decode_page(self._read_stored(destination, page), page)
                present += 1
        return present, len(self.manifest.pages)
