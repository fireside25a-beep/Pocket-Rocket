"""Immutable model identity used by the Pocket Rocket build.

The runtime target is DeepSeek V4 Flash.  The model weights are not included
in this repository; :mod:`scripts.download_deepseek_v4` obtains the exact
public GGUF selected by the recovered DwarfStar integration and verifies it
before publication.

Only facts present in that recovered source contract are encoded here.  In
particular, no parameter count is invented from the compressed file size.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path


MODEL_ID = "deepseek-ai/DeepSeek-V4-Flash"
WEIGHT_REPOSITORY = "antirez/deepseek-v4-gguf"
WEIGHT_REVISION = "b0c3326275d2207e25e42bc8ac0704952466b5bb"
WEIGHT_FILENAME = "DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf"
WEIGHT_SIZE_BYTES = 86_720_111_488
WEIGHT_SHA256 = "efc7ed607ff27076e3e501fc3fefefa33c0ed8cf1eff483a2b7fdc0c2e616668"
ROUTED_EXPERTS = 256
ACTIVE_EXPERTS = 6
LAYERS = 43


@dataclass(frozen=True)
class ModelTarget:
    model_id: str = MODEL_ID
    weight_repository: str = WEIGHT_REPOSITORY
    weight_revision: str = WEIGHT_REVISION
    weight_filename: str = WEIGHT_FILENAME
    weight_size_bytes: int = WEIGHT_SIZE_BYTES
    weight_sha256: str = WEIGHT_SHA256
    routed_experts: int = ROUTED_EXPERTS
    active_experts: int = ACTIVE_EXPERTS
    layers: int = LAYERS

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def validate(self) -> None:
        if self.model_id != MODEL_ID:
            raise ValueError("unsupported model target")
        if self.weight_repository != WEIGHT_REPOSITORY:
            raise ValueError("unsupported weight repository")
        if len(self.weight_revision) != 40 or any(c not in "0123456789abcdef" for c in self.weight_revision):
            raise ValueError("weight revision must be an immutable 40-character commit")
        if not self.weight_filename.endswith(".gguf"):
            raise ValueError("DeepSeek target must be a GGUF file")
        if self.weight_size_bytes <= 0 or len(self.weight_sha256) != 64:
            raise ValueError("invalid weight size or SHA-256")
        if self.routed_experts != 256 or self.active_experts != 6 or self.layers != 43:
            raise ValueError("DeepSeek V4 Flash geometry must be 256 routed / 6 active / 43 layers")


DEEPSEEK_V4_FLASH = ModelTarget()
DEEPSEEK_V4_FLASH.validate()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_weight_file(path: str | Path, target: ModelTarget = DEEPSEEK_V4_FLASH) -> dict[str, object]:
    """Verify one exact GGUF file and return a machine-readable report.

    The magic check is deliberately independent of the full digest so a
    partial or wrong-format file fails early.  No alternate model is accepted.
    """
    target.validate()
    candidate = Path(path)
    if not candidate.is_file():
        raise ValueError(f"missing model file: {candidate}")
    if candidate.name != target.weight_filename:
        raise ValueError(f"unexpected model filename: {candidate.name!r}")
    size = candidate.stat().st_size
    if size != target.weight_size_bytes:
        raise ValueError(f"model size mismatch: {size} != {target.weight_size_bytes}")
    with candidate.open("rb") as handle:
        if handle.read(4) != b"GGUF":
            raise ValueError("model does not have a GGUF header")
    actual = sha256(candidate)
    if actual != target.weight_sha256:
        raise ValueError(f"model SHA-256 mismatch: {actual} != {target.weight_sha256}")
    return {
        "model_id": target.model_id,
        "repository": target.weight_repository,
        "revision": target.weight_revision,
        "filename": candidate.name,
        "size_bytes": size,
        "sha256": actual,
        "verified": True,
        "routed_experts": target.routed_experts,
        "active_experts": target.active_experts,
        "layers": target.layers,
    }
