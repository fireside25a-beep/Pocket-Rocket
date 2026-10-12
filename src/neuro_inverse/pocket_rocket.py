"""Pocket Rocket feasibility entry point for DeepSeek V4 Flash."""

from .model_target import DEEPSEEK_V4_FLASH, verify_weight_file
from .pocket_rocket_feasibility import (
    GIB,
    DEEPSEEK_V4_FLASH_GEOMETRY,
    FeasibilityEstimate,
    MemoryBudget,
    ModelGeometry,
    ContextMemory,
    ds4_flash_cpu_context_memory,
    estimate_deepseek_v4_flash,
    strict_16gb_admission,
    SYSTEM_RAM_BUDGET_BYTES,
    NON_ROUTED_WEIGHT_BUDGET_BYTES,
    ROUTED_CACHE_DEFAULT_BYTES,
    quantized_payload_bytes,
    scale_metadata_bytes,
)

__all__ = [
    "GIB", "DEEPSEEK_V4_FLASH", "DEEPSEEK_V4_FLASH_GEOMETRY",
    "FeasibilityEstimate", "MemoryBudget", "ModelGeometry", "ContextMemory",
    "ds4_flash_cpu_context_memory",
    "estimate_deepseek_v4_flash", "quantized_payload_bytes",
    "scale_metadata_bytes", "verify_weight_file", "strict_16gb_admission",
    "SYSTEM_RAM_BUDGET_BYTES", "NON_ROUTED_WEIGHT_BUDGET_BYTES",
    "ROUTED_CACHE_DEFAULT_BYTES",
]
