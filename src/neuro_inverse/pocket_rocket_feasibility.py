"""Byte-feasibility accounting for the DeepSeek V4 Flash Pocket Rocket.

The pinned model is a GGUF whose exact size is known, but the recovered model
contract does not publish a trustworthy parameter count. This module never
reverse-engineers a parameter count from compressed bytes. When parameter
counts are supplied explicitly, the generic arithmetic path is available; the
default target reports exact file storage and a conservative routed-page proxy.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any

from .model_target import ACTIVE_EXPERTS, DEEPSEEK_V4_FLASH, LAYERS, ROUTED_EXPERTS

GIB = 1024**3
SYSTEM_RAM_BUDGET_BYTES = 16 * GIB
NON_ROUTED_WEIGHT_BUDGET_BYTES = int(8.20 * GIB)
ROUTED_CACHE_DEFAULT_BYTES = 1 * GIB

# Exact DeepSeek V4 Flash CPU-context shape from the pinned ds4 revision.
# This is MLA/compressed attention, not the ordinary two-tensor GQA formula.
DS4_FLASH_HIDDEN_SIZE = 4096
DS4_FLASH_KV_HEADS = 1
DS4_FLASH_HEAD_DIM = 512
DS4_FLASH_SWA_ROWS = 128
DS4_FLASH_INDEXER_HEAD_DIM = 128
DS4_FLASH_FLOAT_BYTES = 4


def _int(name: str, value: int, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or (value <= 0 if positive else value < 0):
        adjective = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must be a {adjective} integer")
    return value


def _bits(value: float) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("bits_per_param must be finite and positive") from None
    if not result.is_finite() or result <= 0:
        raise ValueError("bits_per_param must be finite and positive")
    return result


def quantized_payload_bytes(parameters: int, bits_per_param: float) -> int:
    _int("parameters", parameters)
    return int((Decimal(parameters) * _bits(bits_per_param) / Decimal(8)).to_integral_value(rounding=ROUND_CEILING))


def scale_metadata_bytes(parameters: int, *, block_size: int, scale_bytes: int, zero_point_bytes: int = 0) -> int:
    _int("parameters", parameters)
    _int("block_size", block_size, positive=True)
    _int("scale_bytes", scale_bytes)
    _int("zero_point_bytes", zero_point_bytes)
    return math.ceil(parameters / block_size) * (scale_bytes + zero_point_bytes)


@dataclass(frozen=True)
class ModelGeometry:
    """Model dimensions used by the estimator.

    ``total_params`` and ``active_params`` are optional because the pinned
    GGUF contract gives no independently verified counts. ``source_bytes`` is
    exact on the default DeepSeek target.
    """

    total_params: int | None = None
    active_params: int | None = None
    expert_count: int = ROUTED_EXPERTS
    active_experts: int = ACTIVE_EXPERTS
    layers: int = LAYERS
    hidden_size: int | None = None
    kv_heads: int | None = None
    head_dim: int | None = None
    source_bytes: int | None = DEEPSEEK_V4_FLASH.weight_size_bytes

    def validate(self) -> None:
        if self.total_params is None or self.active_params is None:
            if self.source_bytes is None:
                raise ValueError("source_bytes is required when parameter counts are unknown")
            _int("source_bytes", self.source_bytes, positive=True)
        else:
            _int("total_params", self.total_params, positive=True)
            _int("active_params", self.active_params, positive=True)
            if self.active_params > self.total_params:
                raise ValueError("active_params cannot exceed total_params")
        _int("expert_count", self.expert_count, positive=True)
        _int("active_experts", self.active_experts, positive=True)
        if self.active_experts > self.expert_count:
            raise ValueError("active_experts cannot exceed expert_count")
        _int("layers", self.layers, positive=True)
        for name in ("hidden_size", "kv_heads", "head_dim"):
            value = getattr(self, name)
            if value is not None:
                _int(name, value, positive=True)


DEEPSEEK_V4_FLASH_GEOMETRY = ModelGeometry(
    hidden_size=DS4_FLASH_HIDDEN_SIZE,
    kv_heads=DS4_FLASH_KV_HEADS,
    head_dim=DS4_FLASH_HEAD_DIM,
)


@dataclass(frozen=True)
class ContextMemory:
    raw_bytes: int
    compressed_bytes: int
    scratch_bytes: int
    total_bytes: int
    raw_rows: int
    ratio4_rows: int
    basis: str


def ds4_flash_cpu_context_memory(context_tokens: int) -> ContextMemory:
    """Mirror pinned ds4 CPU context accounting for DeepSeek V4 Flash.

    Layers 0-1 retain only the 128-row sliding window. Layers 2-42 alternate
    4:1 and 128:1 compressed attention. Ratio-4 layers also retain the
    128-wide indexer cache. Integer division and the two-row tail reserve are
    deliberately identical to ds4.
    """
    _int("context_tokens", context_tokens, positive=True)
    raw_rows = min(DS4_FLASH_SWA_ROWS, context_tokens)
    raw = LAYERS * raw_rows * DS4_FLASH_HEAD_DIM * DS4_FLASH_FLOAT_BYTES
    compressed = 0
    ratio4_rows = context_tokens // 4 + 2
    for layer in range(LAYERS):
        ratio = 0 if layer < 2 else (4 if layer % 2 == 0 else 128)
        if ratio == 0:
            continue
        rows = context_tokens // ratio + 2
        compressed += rows * DS4_FLASH_HEAD_DIM * DS4_FLASH_FLOAT_BYTES
        if ratio == 4:
            compressed += rows * DS4_FLASH_INDEXER_HEAD_DIM * DS4_FLASH_FLOAT_BYTES
    # ds4 CPU attention-score/index scratch grows with the ratio-4 cache.
    scratch = (
        (raw_rows + ratio4_rows) * DS4_FLASH_FLOAT_BYTES
        + ratio4_rows * DS4_FLASH_FLOAT_BYTES
        + ratio4_rows  # sizeof(bool) is one in the pinned C ABI/build.
    )
    return ContextMemory(
        raw_bytes=raw,
        compressed_bytes=compressed,
        scratch_bytes=scratch,
        total_bytes=raw + compressed + scratch,
        raw_rows=raw_rows,
        ratio4_rows=ratio4_rows,
        basis="PINNED_DS4_FLASH_CPU_COMPRESSED_KV_V1",
    )


@dataclass(frozen=True)
class MemoryBudget:
    budget_gib: int
    fits: bool
    margin_bytes: int


@dataclass(frozen=True)
class FeasibilityEstimate:
    basis: str
    measurement_status: str
    geometry: ModelGeometry
    bits_per_param: float
    block_size: int
    scale_bytes: int
    zero_point_bytes: int
    resident_common_params: int
    cache_budget_bytes: int
    context_tokens: int
    batch_size: int
    kv_bytes_per_element: int
    runtime_overhead_bytes: int
    full_weight_payload_bytes: int
    full_weight_scale_metadata_bytes: int
    full_ssd_bytes: int
    resident_common_bytes: int
    active_expert_page_bytes: int
    active_weight_ram_bytes: int
    kv_cache_bytes: int
    context_scratch_bytes: int
    context_buffer_bytes: int
    context_memory_basis: str
    working_set_ram_bytes: int
    budgets: tuple[MemoryBudget, ...]
    active_ram_basis: str

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["geometry"] = asdict(self.geometry)
        result["budgets"] = [asdict(item) for item in self.budgets]
        return result


def strict_16gb_admission(
    estimate: FeasibilityEstimate,
    *, available_bytes: int = SYSTEM_RAM_BUDGET_BYTES,
    non_routed_bytes: int = NON_ROUTED_WEIGHT_BUDGET_BYTES,
) -> dict[str, int | bool | str]:
    """Apply the conservative target-machine RAM envelope.

    The 8.20-GiB non-routed figure is an external runtime measurement, not a
    parameter-count inference. Admission is fail-closed: callers must refuse
    to start when the available byte budget is insufficient.
    """
    _int("available_bytes", available_bytes, positive=True)
    _int("non_routed_bytes", non_routed_bytes, positive=True)
    required = (non_routed_bytes + estimate.cache_budget_bytes +
                estimate.context_buffer_bytes + estimate.runtime_overhead_bytes)
    return {
        "admitted": required <= available_bytes,
        "available_bytes": available_bytes,
        "required_bytes": required,
        "margin_bytes": available_bytes - required,
        "basis": "NON_ROUTED_WEIGHT_BUDGET_PLUS_CACHE_KV_RUNTIME",
    }


def estimate_deepseek_v4_flash(
    geometry: ModelGeometry = DEEPSEEK_V4_FLASH_GEOMETRY,
    *, bits_per_param: float = 4.0, block_size: int = 256,
    scale_bytes: int = 2, zero_point_bytes: int = 0,
    resident_common_params: int = 0, cache_budget_bytes: int = 2 * GIB,
    context_tokens: int = 4096, batch_size: int = 1,
    kv_bytes_per_element: int = DS4_FLASH_FLOAT_BYTES, runtime_overhead_bytes: int = 0,
    budget_gib: tuple[int, ...] = (16, 20, 32),
) -> FeasibilityEstimate:
    geometry.validate()
    bits = _bits(bits_per_param)
    _int("block_size", block_size, positive=True)
    _int("scale_bytes", scale_bytes)
    _int("zero_point_bytes", zero_point_bytes)
    _int("resident_common_params", resident_common_params)
    if geometry.active_params is not None and resident_common_params > geometry.active_params:
        raise ValueError("resident_common_params cannot exceed active_params")
    _int("cache_budget_bytes", cache_budget_bytes)
    _int("context_tokens", context_tokens, positive=True)
    _int("batch_size", batch_size, positive=True)
    _int("kv_bytes_per_element", kv_bytes_per_element, positive=True)
    _int("runtime_overhead_bytes", runtime_overhead_bytes)
    if not budget_gib or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in budget_gib):
        raise ValueError("budget_gib must contain positive integers")

    if geometry.total_params is None:
        assert geometry.source_bytes is not None
        full_payload = geometry.source_bytes
        full_scales = 0
        resident = 0
        active_expert = math.ceil(full_payload * geometry.active_experts / geometry.expert_count)
        active_basis = "ROUTED_GGUF_BYTE_PROXY; NOT A PARAMETER COUNT"
    else:
        full_payload = quantized_payload_bytes(geometry.total_params, float(bits))
        full_scales = scale_metadata_bytes(
            geometry.total_params, block_size=block_size, scale_bytes=scale_bytes,
            zero_point_bytes=zero_point_bytes,
        )
        resident = quantized_payload_bytes(resident_common_params, float(bits)) + scale_metadata_bytes(
            resident_common_params, block_size=block_size, scale_bytes=scale_bytes,
            zero_point_bytes=zero_point_bytes,
        )
        active_expert_params = geometry.active_params - resident_common_params
        active_expert = quantized_payload_bytes(active_expert_params, float(bits)) + scale_metadata_bytes(
            active_expert_params, block_size=block_size, scale_bytes=scale_bytes,
            zero_point_bytes=zero_point_bytes,
        )
        active_basis = "PARAMETER_ACCOUNTING"
    active_weight = resident + active_expert
    exact_ds4_shape = (
        geometry.total_params is None
        and geometry.source_bytes == DEEPSEEK_V4_FLASH.weight_size_bytes
        and geometry.expert_count == ROUTED_EXPERTS
        and geometry.active_experts == ACTIVE_EXPERTS
        and geometry.layers == LAYERS
        and geometry.hidden_size == DS4_FLASH_HIDDEN_SIZE
        and geometry.kv_heads == DS4_FLASH_KV_HEADS
        and geometry.head_dim == DS4_FLASH_HEAD_DIM
    )
    if exact_ds4_shape:
        if batch_size != 1:
            raise ValueError("pinned ds4 CPU context accounting currently admits batch_size=1")
        if kv_bytes_per_element != DS4_FLASH_FLOAT_BYTES:
            raise ValueError("pinned ds4 CPU context buffers use four-byte float elements")
        context_memory = ds4_flash_cpu_context_memory(context_tokens)
        kv_cache = context_memory.raw_bytes + context_memory.compressed_bytes
        context_scratch = context_memory.scratch_bytes
        context_buffers = context_memory.total_bytes
        context_basis = context_memory.basis
    else:
        kv_per_token = 0
        if geometry.hidden_size is not None and geometry.kv_heads is not None and geometry.head_dim is not None:
            kv_per_token = geometry.layers * 2 * geometry.kv_heads * geometry.head_dim * kv_bytes_per_element
        kv_cache = context_tokens * batch_size * kv_per_token
        context_scratch = 0
        context_buffers = kv_cache
        context_basis = "GENERIC_UNCOMPRESSED_KV_FORMULA"
    working = active_weight + context_buffers + cache_budget_bytes + runtime_overhead_bytes
    budgets = tuple(MemoryBudget(item, item * GIB >= working, item * GIB - working) for item in budget_gib)
    return FeasibilityEstimate(
        basis="EXACT_PINNED_GGUF_PLUS_ROUTED_PAGE_PROXY" if geometry.total_params is None else "THEORETICAL_BYTE_ACCOUNTING",
        measurement_status="UNMEASURED_ON_TARGET_HARDWARE",
        geometry=geometry, bits_per_param=float(bits), block_size=block_size,
        scale_bytes=scale_bytes, zero_point_bytes=zero_point_bytes,
        resident_common_params=resident_common_params, cache_budget_bytes=cache_budget_bytes,
        context_tokens=context_tokens, batch_size=batch_size,
        kv_bytes_per_element=kv_bytes_per_element, runtime_overhead_bytes=runtime_overhead_bytes,
        full_weight_payload_bytes=full_payload, full_weight_scale_metadata_bytes=full_scales,
        full_ssd_bytes=full_payload + full_scales, resident_common_bytes=resident,
        active_expert_page_bytes=active_expert, active_weight_ram_bytes=active_weight,
        kv_cache_bytes=kv_cache, context_scratch_bytes=context_scratch,
        context_buffer_bytes=context_buffers, context_memory_basis=context_basis,
        working_set_ram_bytes=working, budgets=budgets,
        active_ram_basis=active_basis,
    )
