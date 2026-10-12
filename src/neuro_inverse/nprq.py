"""NeuroRoute Progressive Residual Quantization (NPRQ).

The format stores a tensor as independently loadable ternary stages.  Each
stage uses an optimized signed-quaternary codebook, two packed bits per value,
and one float16 scale per block. Stages are fitted to the residual. A stage is accepted for a
block only when its *stored* float16 scale reduces squared reconstruction error,
which makes reconstruction error monotonic as stages are added.

This is a research format, not an optimized inference kernel.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np

from .pocket_pack import PocketRocketReader
from .flat_dictionary import decode as decode_flat32, read_dictionary

FORMAT = "nprq-signed-quaternary-residual-v2"
CODEBOOK = np.array([-3, -1, 1, 3], dtype=np.int8)
_BLOCK_CHUNK = 4096  # bounded working set: 4096 * 256 values per stage
# A metadata file is untrusted input.  Keep the largest stage and decoded
# tensor finite before allocating either the NumPy output or a container
# expansion buffer. This still accommodates multi-gigabyte model stages while
# turning absurd shape/file claims into a deterministic validation error.
MAX_STAGE_BYTES = 8 * 1024 * 1024 * 1024
MAX_DECODED_BYTES = 8 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class NPRQMeta:
    format: str
    shape: tuple[int, ...]
    source_dtype: str
    block_size: int
    stages: int
    numel: int
    stage_files: tuple[str, ...]
    stage_sha256: tuple[str, ...]
    rmse: tuple[float, ...]


def stage_filenames(name: str, stages: int) -> tuple[str, ...]:
    """Return the content-addressed stage names used for *name*."""
    if not isinstance(name, str) or not name:
        raise ValueError("tensor name must be a non-empty string")
    if stages < 1 or stages > 8:
        raise ValueError("stages must be between 1 and 8")
    safe_id = hashlib.sha256(name.encode("utf-8")).hexdigest()[:24]
    return tuple(f"{safe_id}.s{stage}.nprq" for stage in range(stages))


def _validate_meta(meta: NPRQMeta) -> None:
    """Validate persisted metadata before it is used to address files."""
    if meta.format not in {FORMAT, "nprq-ternary-residual-v1"}:
        raise ValueError(f"unsupported NPRQ format: {meta.format}")
    if any(int(value) < 0 for value in meta.shape):
        raise ValueError("NPRQ shape contains a negative dimension")
    if meta.block_size < 16 or meta.block_size % 4:
        raise ValueError("invalid NPRQ block size")
    if meta.stages < 1 or meta.stages > 8:
        raise ValueError("invalid NPRQ stage count")
    expected_numel = math.prod(meta.shape) if meta.shape else 1
    if meta.numel != expected_numel or meta.numel < 0:
        raise ValueError("NPRQ numel does not match shape")
    if len(meta.stage_files) != meta.stages or len(meta.stage_sha256) != meta.stages:
        raise ValueError("NPRQ stage metadata lengths do not match stages")
    if len(meta.rmse) != meta.stages:
        raise ValueError("NPRQ RMSE metadata length does not match stages")
    if not all(math.isfinite(float(value)) and float(value) >= 0 for value in meta.rmse):
        raise ValueError("invalid NPRQ RMSE metadata")
    if any(right > left for left, right in zip(meta.rmse, meta.rmse[1:])):
        raise ValueError("NPRQ stored-scale SSE/RMSE is not monotonic")
    for filename in meta.stage_files:
        path = Path(filename)
        if path.is_absolute() or path.name != filename or ".." in path.parts:
            raise ValueError(f"unsafe NPRQ stage filename: {filename!r}")
        if path.suffix not in {".nprq", ".prk", ".f32"}:
            raise ValueError(f"invalid NPRQ stage filename: {filename!r}")
    if len(set(meta.stage_files)) != len(meta.stage_files):
        raise ValueError("duplicate NPRQ stage filename")
    for digest in meta.stage_sha256:
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("invalid NPRQ stage SHA-256")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ValueError("invalid NPRQ stage SHA-256") from exc
    _stage_expected_bytes(meta)


def _codes_for_residual(residual: np.ndarray) -> tuple[np.ndarray, np.float16]:
    """Legacy ternary helper retained for compatibility with v1 experiments."""
    residual = residual.astype(np.float32, copy=False)
    baseline = float(np.dot(residual, residual))
    if baseline == 0.0:
        return np.zeros(residual.size, dtype=np.int8), np.float16(0)
    scale = float(np.mean(np.abs(residual)))
    if not math.isfinite(scale) or scale == 0.0:
        return np.zeros(residual.size, dtype=np.int8), np.float16(0)
    q = np.clip(np.rint(residual / scale), -1, 1).astype(np.int8)
    denom = int(np.dot(q.astype(np.int32), q.astype(np.int32)))
    if denom == 0:
        return np.zeros(residual.size, dtype=np.int8), np.float16(0)
    scale16 = np.float16(float(np.dot(residual, q.astype(np.float32))) / denom)
    candidate = q.astype(np.float32) * np.float32(scale16)
    if not np.isfinite(candidate).all() or float(np.dot(residual - candidate, residual - candidate)) >= baseline:
        return np.zeros(residual.size, dtype=np.int8), np.float16(0)
    return q, scale16


def pack_ternary(codes: np.ndarray, padded_count: int | None = None) -> bytes:
    flat = np.asarray(codes, dtype=np.int8).reshape(-1)
    if np.any((flat < -1) | (flat > 1)):
        raise ValueError("ternary codes must be -1, 0, or 1")
    count = padded_count if padded_count is not None else flat.size
    if isinstance(count, bool) or not isinstance(count, (int, np.integer)):
        raise TypeError("padded_count must be an integer")
    count = int(count)
    if count < flat.size:
        raise ValueError("padded_count cannot be smaller than code count")
    mapped = np.ones(count, dtype=np.uint8)
    mapped[:flat.size] = (flat + 1).astype(np.uint8)
    if count % 4:
        mapped = np.pad(mapped, (0, 4 - count % 4), constant_values=1)
    packed = mapped[0::4] | (mapped[1::4] << 2) | (mapped[2::4] << 4) | (mapped[3::4] << 6)
    return packed.tobytes()


def unpack_ternary(data: bytes, count: int) -> np.ndarray:
    if isinstance(count, bool) or not isinstance(count, (int, np.integer)):
        raise TypeError("count must be an integer")
    count = int(count)
    if count < 0:
        raise ValueError("count cannot be negative")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("packed ternary data must be bytes-like")
    raw = np.frombuffer(data, dtype=np.uint8)
    expected_bytes = (count + 3) // 4
    if raw.size != expected_bytes:
        raise ValueError("packed ternary payload has unexpected length")
    values = np.empty(raw.size * 4, dtype=np.int8)
    values[0::4] = raw & 0x03
    values[1::4] = (raw >> 2) & 0x03
    values[2::4] = (raw >> 4) & 0x03
    values[3::4] = (raw >> 6) & 0x03
    if np.any(values[:count] == 3):
        raise ValueError("invalid NPRQ ternary code 3")
    if count % 4 and np.any(values[count:] != 1):
        raise ValueError("non-canonical NPRQ ternary padding")
    return values[:count] - 1


def _record_bytes(block_size: int) -> int:
    return 2 + math.ceil(block_size / 4)


def encode_tensor(array: np.ndarray, output_dir: Path, name: str, *, stages: int = 3,
                  block_size: int = 256) -> NPRQMeta:
    if stages < 1 or stages > 8:
        raise ValueError("stages must be between 1 and 8")
    if block_size < 16 or block_size % 4:
        raise ValueError("block_size must be >=16 and divisible by four")
    source = np.asarray(array)
    if not np.issubdtype(source.dtype, np.floating):
        raise TypeError("NPRQ encodes floating tensors only")
    if not np.isfinite(source).all():
        raise ValueError("NPRQ cannot encode NaN or infinite tensor values")
    output_dir.mkdir(parents=True, exist_ok=True)
    stage_names = stage_filenames(name, stages)
    safe_id = stage_names[0].split(".s", 1)[0]
    errors = np.zeros(stages, dtype=np.float64)
    total = source.size
    block_count = math.ceil(total / block_size)
    padded_count = block_count * block_size
    if total == 0:
        for filename in stage_names:
            (output_dir / filename).write_bytes(b"")
        hashes = tuple(_sha256(output_dir / filename) for filename in stage_names)
        meta = NPRQMeta(
            format=FORMAT, shape=tuple(int(v) for v in source.shape), source_dtype=str(source.dtype),
            block_size=block_size, stages=stages, numel=0,
            stage_files=stage_names, stage_sha256=hashes, rmse=tuple(0.0 for _ in range(stages)),
        )
        (output_dir / f"{safe_id}.json").write_text(
            json.dumps({"name": name, **meta.__dict__}, indent=2) + "\n", encoding="utf-8"
        )
        return meta

    source_flat = source.reshape(-1)
    packed_width = block_size // 4
    # Keep the evolving residual on disk. A full model embedding can contain
    # billions of values; retaining residual, masks, q, and candidates at once
    # would exceed ordinary workstation RAM.  The chunk loop below is also the
    # reference ordering, so it remains deterministic and byte-compatible with
    # the original block-local algorithm.
    with tempfile.NamedTemporaryFile(prefix=f"{safe_id}.", suffix=".residual", dir=output_dir,
                                     delete=True) as temporary:
        residual = np.memmap(temporary.name, mode="w+", dtype=np.float32, shape=(padded_count,))
        for start in range(0, total, _BLOCK_CHUNK * block_size):
            stop = min(start + _BLOCK_CHUNK * block_size, total)
            residual[start:stop] = source_flat[start:stop].astype(np.float32, copy=False)
        if padded_count > total:
            residual[total:padded_count] = 0
        residual.flush()
        for stage, filename in enumerate(stage_names):
            stage_path = output_dir / filename
            with stage_path.open("wb") as handle:
                for block_start in range(0, block_count, _BLOCK_CHUNK):
                    block_stop = min(block_start + _BLOCK_CHUNK, block_count)
                    count = block_stop - block_start
                    value_start = block_start * block_size
                    value_stop = block_stop * block_size
                    block = np.asarray(residual[value_start:value_stop]).reshape(count, block_size)
                    valid_mask = np.ones((count, block_size), dtype=np.float32)
                    if block_stop == block_count and padded_count != total:
                        valid_mask[-1, total % block_size:] = 0
                    abs_sum = np.sum(np.abs(block), axis=1)
                    valid_per_block = np.sum(valid_mask, axis=1)
                    scale32 = np.divide(
                        abs_sum, 2 * valid_per_block, out=np.zeros_like(abs_sum),
                        where=valid_per_block != 0,
                    )
                    codes = np.zeros((count, block_size), dtype=np.uint8)
                    q = np.zeros((count, block_size), dtype=np.float32)
                    # Blockwise Lloyd updates optimize scale for the fixed
                    # four-symbol codebook. Six rounds are deterministic.
                    for _ in range(6):
                        boundary = 2 * scale32[:, None]
                        codes = np.where(
                            block < -boundary, 0,
                            np.where(block < 0, 1, np.where(block < boundary, 2, 3)),
                        ).astype(np.uint8)
                        q = CODEBOOK[codes].astype(np.float32) * valid_mask
                        denom = np.sum(q * q, axis=1)
                        numer = np.sum(block * q, axis=1)
                        scale32 = np.divide(numer, denom, out=np.zeros_like(numer), where=denom != 0)
                    scale = scale32.astype("<f2")
                    candidate = q * scale.astype(np.float32)[:, None]
                    before = np.sum(block * block, axis=1)
                    after = np.sum((block - candidate) ** 2, axis=1)
                    rejected = (~np.isfinite(after)) | (after >= before)
                    codes[rejected] = 1
                    scale[rejected] = 0
                    candidate[rejected] = 0
                    mapped = codes.reshape(count, packed_width, 4)
                    packed = (
                        mapped[:, :, 0] | (mapped[:, :, 1] << 2)
                        | (mapped[:, :, 2] << 4) | (mapped[:, :, 3] << 6)
                    )
                    records = np.empty((count, 2 + packed_width), dtype=np.uint8)
                    records[:, :2] = scale.view(np.uint8).reshape(count, 2)
                    records[:, 2:] = packed
                    handle.write(records.tobytes())
                    block -= candidate
                    residual[value_start:value_stop] = block.reshape(-1)
                    errors[stage] += float(np.sum((block * valid_mask) ** 2))
            residual.flush()
    hashes = tuple(_sha256(output_dir / filename) for filename in stage_names)
    rmse = tuple(float(math.sqrt(value / max(total, 1))) for value in errors)
    meta = NPRQMeta(
        format=FORMAT, shape=tuple(int(v) for v in source.shape), source_dtype=str(source.dtype),
        block_size=block_size, stages=stages, numel=total,
        stage_files=stage_names, stage_sha256=hashes, rmse=rmse,
    )
    (output_dir / f"{safe_id}.json").write_text(json.dumps({"name": name, **meta.__dict__}, indent=2) + "\n", encoding="utf-8")
    return meta


def decode_tensor(output_dir: Path, meta: NPRQMeta, *, stage_count: int | None = None,
                  dtype: np.dtype = np.float32) -> np.ndarray:
    _validate_meta(meta)
    try:
        dtype_obj = np.dtype(dtype)
    except TypeError as exc:
        raise TypeError("dtype must be a NumPy numeric dtype") from exc
    if dtype_obj.kind not in "biufc":
        raise TypeError("dtype must be a NumPy numeric dtype")
    if meta.numel * dtype_obj.itemsize > MAX_DECODED_BYTES:
        raise ValueError("decoded NPRQ tensor exceeds configured bounds")
    use_stages = meta.stages if stage_count is None else stage_count
    if not 1 <= use_stages <= meta.stages:
        raise ValueError("stage_count outside encoded range")
    block_count = math.ceil(meta.numel / meta.block_size)
    packed_width = meta.block_size // 4
    record_width = 2 + packed_width
    output = np.zeros((block_count, meta.block_size), dtype=np.float32)
    expected_bytes = block_count * record_width
    for stage in range(use_stages):
        raw_bytes = _read_stage_bytes(_safe_stage_path(output_dir, meta.stage_files[stage]), expected_bytes)
        raw = np.frombuffer(raw_bytes, dtype=np.uint8)
        if raw.size != expected_bytes:
            raise ValueError("truncated or oversized NPRQ stage")
        records = raw.reshape(block_count, record_width)
        scales = records[:, :2].copy().reshape(-1).view("<f2").astype(np.float32)
        packed = records[:, 2:]
        values = np.empty((block_count, packed_width, 4), dtype=np.int8)
        values[:, :, 0] = packed & 0x03
        values[:, :, 1] = (packed >> 2) & 0x03
        values[:, :, 2] = (packed >> 4) & 0x03
        values[:, :, 3] = (packed >> 6) & 0x03
        if meta.format == "nprq-ternary-residual-v1":
            if np.any(values == 3):
                raise ValueError("invalid legacy NPRQ ternary code 3")
            decoded = values.reshape(block_count, meta.block_size) - 1
        elif meta.format == FORMAT:
            decoded = CODEBOOK[values.reshape(block_count, meta.block_size)]
        else:
            raise ValueError(f"unsupported NPRQ format: {meta.format}")
        output += decoded.astype(np.float32) * scales[:, None]
    return output.reshape(-1)[:meta.numel].reshape(meta.shape).astype(dtype_obj, copy=False)


def meta_from_dict(raw: dict) -> NPRQMeta:
    if not isinstance(raw, dict):
        raise ValueError("NPRQ metadata must be an object")
    meta = NPRQMeta(
        format=raw.get("format", "nprq-ternary-residual-v1"),
        shape=tuple(int(value) for value in raw["shape"]), source_dtype=str(raw["source_dtype"]),
        block_size=int(raw["block_size"]), stages=int(raw["stages"]),
        numel=int(raw["numel"]), stage_files=tuple(raw["stage_files"]),
        stage_sha256=tuple(str(value) for value in raw["stage_sha256"]),
        rmse=tuple(float(value) for value in raw["rmse"]),
    )
    _validate_meta(meta)
    return meta


def verify_tensor(output_dir: Path, meta: NPRQMeta, *, stage_count: int | None = None) -> None:
    _validate_meta(meta)
    use_stages = meta.stages if stage_count is None else stage_count
    if not 1 <= use_stages <= meta.stages:
        raise ValueError("stage_count outside encoded range")
    for filename, expected in zip(meta.stage_files[:use_stages], meta.stage_sha256[:use_stages]):
        actual = _stage_sha256(_safe_stage_path(output_dir, filename), _stage_expected_bytes(meta))
        if actual != expected:
            raise ValueError(f"NPRQ hash mismatch for {filename}")


def _stage_expected_bytes(meta: NPRQMeta) -> int:
    block_count = math.ceil(meta.numel / meta.block_size)
    expected = block_count * _record_bytes(meta.block_size)
    if expected > MAX_STAGE_BYTES:
        raise ValueError("NPRQ stage exceeds configured bounds")
    return expected


def _safe_stage_path(output_dir: Path, filename: str) -> Path:
    """Resolve a stage and reject symlink/path escapes from its page root."""
    root = Path(output_dir).resolve()
    candidate = (root / filename).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"NPRQ stage escapes output directory: {filename!r}") from exc
    return candidate


def _read_stage_bytes(path: Path, expected_bytes: int) -> bytes:
    """Read one raw NPRQ stage, expanding a bounded ``.prk`` page if needed."""
    try:
        file_size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"NPRQ stage is not readable: {path.name}") from exc
    if path.suffix == ".nprq":
        if file_size != expected_bytes:
            raise ValueError("truncated or oversized NPRQ stage")
        return path.read_bytes()
    if path.suffix == ".f32":
        dictionary_path = path.parent / "_flat32.dict"
        if not dictionary_path.is_file():
            raise ValueError("Flat32 stage is missing its page dictionary")
        if file_size > MAX_STAGE_BYTES:
            raise ValueError("Flat32 stage exceeds configured bounds")
        raw = decode_flat32(
            path.read_bytes(), read_dictionary(dictionary_path),
            max_source_bytes=expected_bytes,
            max_encoded_bytes=max(file_size, 1),
        )
        if len(raw) != expected_bytes:
            raise ValueError("Flat32 stage length does not match NPRQ metadata")
        return raw
    if path.suffix != ".prk":
        raise ValueError(f"unsupported NPRQ stage container: {path.name}")
    if file_size > MAX_STAGE_BYTES:
        raise ValueError("Pocket Pack stage exceeds configured bounds")
    with PocketRocketReader(
        path, max_source_bytes=expected_bytes, max_range_bytes=expected_bytes
    ) as reader:
        if reader.info.source_bytes != expected_bytes:
            raise ValueError("Pocket Pack stage length does not match NPRQ metadata")
        expanded = bytearray(expected_bytes)
        digest = hashlib.sha256()
        position = 0
        for chunk in reader.iter_chunks():
            end = position + len(chunk)
            if end > expected_bytes:
                raise ValueError("Pocket Pack stage exceeds NPRQ metadata bounds")
            expanded[position:end] = chunk
            digest.update(chunk)
            position = end
        if position != expected_bytes:
            raise ValueError("truncated Pocket Pack stage")
        if digest.hexdigest() != reader.info.source_sha256:
            raise ValueError("Pocket Pack whole-source SHA-256 mismatch")
        return bytes(expanded)


def _stage_sha256(path: Path, expected_bytes: int) -> str:
    if path.suffix == ".nprq":
        if path.stat().st_size != expected_bytes:
            raise ValueError("truncated or oversized NPRQ stage")
        return _sha256(path)
    if path.suffix == ".f32":
        return hashlib.sha256(_read_stage_bytes(path, expected_bytes)).hexdigest()
    if path.suffix != ".prk":
        raise ValueError(f"unsupported NPRQ stage container: {path.name}")
    digest = hashlib.sha256()
    total = 0
    with PocketRocketReader(
        path, max_source_bytes=expected_bytes, max_range_bytes=expected_bytes
    ) as reader:
        if reader.info.source_bytes != expected_bytes:
            raise ValueError("Pocket Pack stage length does not match NPRQ metadata")
        for chunk in reader.iter_chunks():
            total += len(chunk)
            digest.update(chunk)
    if total != expected_bytes:
        raise ValueError("truncated Pocket Pack stage")
    if digest.hexdigest() != reader.info.source_sha256:
        raise ValueError("Pocket Pack whole-source SHA-256 mismatch")
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
