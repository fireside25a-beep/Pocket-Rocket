"""Portable deterministic governance receipts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Any

from .envelope import canonical_sha256


@dataclass(frozen=True, slots=True)
class GovernanceReceipt:
    source_kind: str
    transcript: Mapping[str, Any]
    source_certificate: str
    model_root: str
    request_root: str
    arithmetic_mode: str
    why: str
    receipt_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "domain": "neuro-inverse-governance-receipt-v1",
            "source_kind": self.source_kind,
            "transcript": dict(self.transcript),
            "source_certificate": self.source_certificate,
            "source_certificate_verified": True,
            "model_root": self.model_root,
            "request_root": self.request_root,
            "arithmetic_mode": self.arithmetic_mode,
            "why": self.why,
            "receipt_sha256": self.receipt_sha256,
        }


def _why(transcript: Mapping[str, Any]) -> str:
    checks = transcript.get("conditional_checks")
    passes = transcript.get("conditional_passes")
    failures = transcript.get("conditional_failures")
    if all(isinstance(item, int) for item in (checks, passes, failures)):
        return f"conditional checks={checks}, passes={passes}, failures={failures}"
    rounds = transcript.get("rounds")
    if isinstance(rounds, list):
        status = transcript.get("status_name", transcript.get("status", "unknown"))
        return f"bounded recursive execution completed {len(rounds)} level(s); final status={status}"
    return f"deterministic decision status={transcript.get('status', 'unknown')}"


def create_receipt(*, source_kind: str, transcript: Mapping[str, Any], certificate: str,
                   model_root: str, request_root: str, arithmetic_mode: str,
                   answer: str | None = None) -> GovernanceReceipt:
    if arithmetic_mode not in {"integer_oracle", "x87_verified", "avx2_verified"}:
        raise ValueError("unsupported arithmetic mode")
    if not isinstance(transcript, Mapping):
        raise TypeError("transcript must be a mapping")
    if source_kind == "agent-run":
        if answer is None:
            raise ValueError("agent-run attestation requires the committed answer")
        from .agent_fabric import verify_run_certificate
        verified = verify_run_certificate(dict(transcript), answer, certificate)
    else:
        verified = canonical_sha256(dict(transcript)) == certificate
    if not verified:
        raise ValueError("source certificate does not verify")
    for label, value in (("model_root", model_root), ("request_root", request_root)):
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError(f"{label} must be lowercase SHA-256")
    payload = {
        "domain": "neuro-inverse-governance-receipt-v1",
        "source_kind": source_kind,
        "transcript": dict(transcript),
        "source_certificate": certificate,
        "source_certificate_verified": True,
        "model_root": model_root,
        "request_root": request_root,
        "arithmetic_mode": arithmetic_mode,
        "why": _why(transcript),
    }
    digest = canonical_sha256(payload)
    return GovernanceReceipt(source_kind, transcript, certificate, model_root, request_root,
                             arithmetic_mode, str(payload["why"]), digest)
