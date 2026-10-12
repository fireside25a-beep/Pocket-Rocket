"""Read-only CPU host qualification for the Pocket Rocket runtime.

The preflight intentionally performs no privileged operation.  It reads Linux
process/kernel interfaces, classifies the available x86-64 ISA, and emits a
canonical certificate whose digest can be embedded in later token records.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ARITHMETIC_INTEGER_ORACLE = "integer_oracle"
ARITHMETIC_X87_VERIFIED = "x87_verified"
ARITHMETIC_AVX2_VERIFIED = "avx2_verified"

_V1_FLAGS = frozenset({"cmov", "cx8", "fpu", "fxsr", "mmx", "sse", "sse2"})
_V2_FLAGS = _V1_FLAGS | frozenset(
    {"cx16", "lahf_lm", "popcnt", "sse3", "ssse3", "sse4_1", "sse4_2"}
)
_V3_FLAGS = _V2_FLAGS | frozenset(
    {"avx", "avx2", "bmi1", "bmi2", "f16c", "fma", "lzcnt", "movbe", "xsave"}
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: dict[str, object]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return _sha256_bytes(payload.encode("ascii"))


def parse_cpu_flags(text: str) -> frozenset[str]:
    """Return normalized flags from Linux ``/proc/cpuinfo`` text."""
    flags: set[str] = set()
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() in {"flags", "features"}:
            flags.update(item.lower() for item in value.split())
    # Linux uses aliases that differ from the psABI spelling.
    if "abm" in flags:
        flags.add("lzcnt")
    if "pni" in flags:
        flags.add("sse3")
    return frozenset(flags)


def classify_x86_64(machine: str, flags: Iterable[str]) -> tuple[bool, bool, tuple[str, ...]]:
    """Classify the baseline and v3 paths without executing feature opcodes."""
    normalized_machine = machine.lower().replace("amd64", "x86_64")
    available = frozenset(item.lower() for item in flags)
    if normalized_machine != "x86_64":
        return False, False, tuple(sorted(_V1_FLAGS))
    missing_v1 = tuple(sorted(_V1_FLAGS - available))
    baseline = not missing_v1
    return baseline, baseline and _V3_FLAGS <= available, missing_v1


@dataclass(frozen=True)
class ArithmeticModeCertificate:
    """Names the three arithmetic modes admitted by the CPU architecture.

    An accelerated record is valid only when a separate conformance run has
    produced identical oracle and candidate digests.  Merely detecting AVX2
    and FMA never promotes the host to the accelerated mode.
    """

    mode: str
    oracle_vector_sha256: str
    candidate_vector_sha256: str
    candidate_binary_sha256: str
    equivalence_verified: bool

    def __post_init__(self) -> None:
        modes = {
            ARITHMETIC_INTEGER_ORACLE,
            ARITHMETIC_X87_VERIFIED,
            ARITHMETIC_AVX2_VERIFIED,
        }
        if self.mode not in modes:
            raise ValueError("unsupported arithmetic mode")
        for name in ("oracle_vector_sha256", "candidate_vector_sha256", "candidate_binary_sha256"):
            value = getattr(self, name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        same = self.oracle_vector_sha256 == self.candidate_vector_sha256
        if self.equivalence_verified != same:
            raise ValueError("equivalence flag must equal the vector digest comparison")
        if self.mode in {ARITHMETIC_X87_VERIFIED, ARITHMETIC_AVX2_VERIFIED} and not same:
            raise ValueError("verified arithmetic mode requires oracle-equivalent vectors")

    @property
    def certificate_sha256(self) -> str:
        return _canonical_sha256(asdict(self))


@dataclass(frozen=True)
class HostPreflight:
    architecture: str
    linux: bool
    x86_64_v1: bool
    x86_64_v3: bool
    avx2: bool
    fma: bool
    cpu_count: int
    allowed_cpus: tuple[int, ...]
    affinity_available: bool
    transparent_hugepage_mode: str
    privileged_tuning_performed: bool
    gpu_backend: str
    default_arithmetic_mode: str
    user_space_advice: tuple[str, ...]
    missing_v1_flags: tuple[str, ...]
    missing_v3_flags: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def certificate_sha256(self) -> str:
        return _canonical_sha256(self.as_dict())


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _transparent_hugepage_mode(root: Path = Path("/sys")) -> str:
    value = _read_text(root / "kernel/mm/transparent_hugepage/enabled").strip()
    if not value:
        return "unknown"
    for item in value.split():
        if item.startswith("[") and item.endswith("]"):
            return item[1:-1]
    return "unknown"


def inspect_host(*, cpuinfo_path: Path = Path("/proc/cpuinfo"), sys_root: Path = Path("/sys")) -> HostPreflight:
    """Inspect the current host without modifying affinity or kernel state."""
    machine = platform.machine().lower()
    flags = parse_cpu_flags(_read_text(cpuinfo_path))
    baseline, v3, missing_v1 = classify_x86_64(machine, flags)
    if hasattr(os, "sched_getaffinity"):
        try:
            allowed = tuple(sorted(os.sched_getaffinity(0)))
            affinity_available = True
        except OSError:
            allowed = tuple(range(os.cpu_count() or 1))
            affinity_available = False
    else:
        allowed = tuple(range(os.cpu_count() or 1))
        affinity_available = False
    thp_mode = _transparent_hugepage_mode(sys_root)
    advice: list[str] = []
    if affinity_available:
        advice.append("optional: pin only within allowed_cpus using sched_setaffinity")
    if thp_mode in {"always", "madvise"}:
        advice.append("optional: request transparent huge pages per allocation with MADV_HUGEPAGE")
    else:
        advice.append("transparent huge pages unavailable; continue with ordinary anonymous pages")
    return HostPreflight(
        architecture=machine,
        linux=platform.system() == "Linux",
        x86_64_v1=baseline,
        x86_64_v3=v3,
        avx2="avx2" in flags,
        fma="fma" in flags,
        cpu_count=os.cpu_count() or 1,
        allowed_cpus=allowed,
        affinity_available=affinity_available,
        transparent_hugepage_mode=thp_mode,
        privileged_tuning_performed=False,
        gpu_backend="disabled",
        # ISA discovery is not numerical qualification. Promotion to x87 or
        # AVX2 requires a separate matching ArithmeticModeCertificate.
        default_arithmetic_mode=ARITHMETIC_INTEGER_ORACLE,
        user_space_advice=tuple(advice),
        missing_v1_flags=missing_v1,
        missing_v3_flags=tuple(sorted(_V3_FLAGS - flags)),
    )


def require_cpu_host(report: HostPreflight) -> None:
    """Fail closed unless the portable x86-64-v1 CPU contract is present."""
    if not report.linux:
        raise RuntimeError("Pocket Rocket CPU runtime requires Linux")
    if not report.x86_64_v1:
        missing = ",".join(report.missing_v1_flags) or "architecture"
        raise RuntimeError(f"x86-64-v1 CPU contract not met: {missing}")
    if report.gpu_backend != "disabled" or report.privileged_tuning_performed:
        raise RuntimeError("CPU preflight state violates the user-space-only contract")
