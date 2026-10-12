"""Locally executed typed decisions over exact triadic evidence."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable

from .ternary_exact import ExactRational, Triadic


class DecisionError(ValueError):
    pass


class TernaryStatus(IntEnum):
    REJECT = -1
    ABSTAIN = 0
    ACCEPT = 1


@dataclass(frozen=True, slots=True)
class Criterion:
    name: str
    score: Triadic
    weight: Triadic = Triadic(1)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or len(self.name.encode("utf-8")) > 128:
            raise DecisionError("criterion name must contain 1..128 UTF-8 bytes")

    @property
    def contribution(self) -> Triadic:
        return self.score * self.weight


@dataclass(frozen=True, slots=True)
class GateResult:
    status: TernaryStatus
    score: Triadic
    reject_below: Triadic
    accept_at: Triadic
    evidence_root: str
    certificate: str


def _triadic_payload(value: Triadic) -> dict[str, int]:
    return {"numerator": value.numerator, "power_of_three": value.exponent}


def _rational_payload(value: ExactRational) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _canonical_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def score(criteria: Iterable[Criterion]) -> tuple[Triadic, tuple[Criterion, ...], str]:
    ordered = tuple(criteria)
    if not ordered:
        raise DecisionError("at least one criterion is required")
    if len(ordered) > 256:
        raise DecisionError("criterion count exceeds 256")
    names = [item.name for item in ordered]
    if len(set(names)) != len(names):
        raise DecisionError("criterion names must be unique")
    total = Triadic(0)
    rows: list[dict[str, object]] = []
    for item in ordered:
        total = total + item.contribution
        rows.append(
            {
                "name": item.name,
                "score": _triadic_payload(item.score),
                "weight": _triadic_payload(item.weight),
                "contribution": _triadic_payload(item.contribution),
            }
        )
    return total, ordered, _canonical_hash({"domain": "pocket-criterion-v1", "criteria": rows})


def gate(
    criteria: Iterable[Criterion],
    *,
    reject_below: Triadic,
    accept_at: Triadic,
    model_root: str,
    request_root: str,
) -> GateResult:
    """Return reject/abstain/accept with a proof-carrying exact transcript."""
    if reject_below.compare(accept_at) >= 0:
        raise DecisionError("reject threshold must be below accept threshold")
    for name, root in (("model_root", model_root), ("request_root", request_root)):
        if len(root) != 64 or any(character not in "0123456789abcdef" for character in root):
            raise DecisionError(f"{name} must be lowercase SHA-256")
    total, _, evidence_root = score(criteria)
    if total.compare(reject_below) < 0:
        status = TernaryStatus.REJECT
    elif total.compare(accept_at) >= 0:
        status = TernaryStatus.ACCEPT
    else:
        status = TernaryStatus.ABSTAIN
    transcript: dict[str, object] = {
        "domain": "pocket-ternary-gate-v1",
        "status": int(status),
        "score": _triadic_payload(total),
        "reject_below": _triadic_payload(reject_below),
        "accept_at": _triadic_payload(accept_at),
        "model_root": model_root,
        "request_root": request_root,
        "evidence_root": evidence_root,
    }
    return GateResult(
        status, total, reject_below, accept_at, evidence_root, _canonical_hash(transcript)
    )


@dataclass(frozen=True, slots=True)
class Choice:
    key: str
    score: Triadic


@dataclass(frozen=True, slots=True)
class ChoiceResult:
    status: TernaryStatus
    choice: str | None
    margin: Triadic


def choose(options: Iterable[Choice], *, minimum_margin: Triadic) -> ChoiceResult:
    """Pick a unique best option or abstain; ties never depend on iteration order."""
    candidates = tuple(options)
    if not 2 <= len(candidates) <= 256:
        raise DecisionError("choice requires 2..256 options")
    if minimum_margin.numerator < 0:
        raise DecisionError("minimum margin must be non-negative")
    if any(not item.key or len(item.key.encode("utf-8")) > 128 for item in candidates):
        raise DecisionError("choice keys must contain 1..128 UTF-8 bytes")
    if len({item.key for item in candidates}) != len(candidates):
        raise DecisionError("choice keys must be unique")
    ranked = sorted(candidates, key=lambda item: item.key)
    best = ranked[0]
    for candidate in ranked[1:]:
        if candidate.score.compare(best.score) > 0:
            best = candidate
    runners = [item for item in ranked if item.key != best.key]
    runner = runners[0]
    for candidate in runners[1:]:
        if candidate.score.compare(runner.score) > 0:
            runner = candidate
    margin = best.score - runner.score
    tied = any(item.key != best.key and item.score.compare(best.score) == 0 for item in ranked)
    if tied or margin.compare(minimum_margin) < 0:
        return ChoiceResult(TernaryStatus.ABSTAIN, None, margin)
    return ChoiceResult(TernaryStatus.ACCEPT, best.key, margin)


@dataclass(frozen=True, slots=True)
class ScoreLevel:
    key: str
    support: Triadic

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key or len(self.key.encode("utf-8")) > 128:
            raise DecisionError("score level keys must contain 1..128 UTF-8 bytes")
        if self.support.numerator < 0:
            raise DecisionError("score level support must be non-negative")


@dataclass(frozen=True, slots=True)
class OrderedScoreResult:
    status: TernaryStatus
    level: str | None
    level_index: int | None
    expected_score: ExactRational
    confidence: ExactRational
    probabilities: tuple[ExactRational, ...]
    legend: tuple[str, ...]
    evidence_root: str
    certificate: str


def ordered_score(
    levels: Iterable[ScoreLevel],
    *,
    minimum_confidence: ExactRational,
    model_root: str,
    request_root: str,
) -> OrderedScoreResult:
    """Return an exact ordered score and abstain when its peak is ambiguous."""
    ordered = tuple(levels)
    if not 2 <= len(ordered) <= 64:
        raise DecisionError("ordered score requires 2..64 levels")
    if len({item.key for item in ordered}) != len(ordered):
        raise DecisionError("score level keys must be unique")
    if minimum_confidence.compare(ExactRational(0)) < 0 or minimum_confidence.compare(
        ExactRational(1)
    ) > 0:
        raise DecisionError("minimum confidence must be in the exact interval [0, 1]")
    for name, root in (("model_root", model_root), ("request_root", request_root)):
        if len(root) != 64 or any(character not in "0123456789abcdef" for character in root):
            raise DecisionError(f"{name} must be lowercase SHA-256")

    exponent = max(item.support.exponent for item in ordered)
    weights = tuple(item.support.align(exponent) for item in ordered)
    total = sum(weights)
    if total <= 0:
        raise DecisionError("ordered score requires positive total support")
    probabilities = tuple(ExactRational(weight, total) for weight in weights)
    expected = ExactRational(sum(index * weight for index, weight in enumerate(weights)), total)
    best_weight = max(weights)
    best_indices = [index for index, weight in enumerate(weights) if weight == best_weight]
    runner_weight = (
        best_weight
        if len(best_indices) > 1
        else max(
            (weight for index, weight in enumerate(weights) if index != best_indices[0]),
            default=best_weight,
        )
    )
    confidence = ExactRational(best_weight - runner_weight, total)
    accepted = len(best_indices) == 1 and confidence.compare(minimum_confidence) >= 0
    best_index = best_indices[0] if accepted else None
    rows = [
        {
            "index": index,
            "key": item.key,
            "support": _triadic_payload(item.support),
            "probability": _rational_payload(probabilities[index]),
        }
        for index, item in enumerate(ordered)
    ]
    evidence_root = _canonical_hash({"domain": "pocket-ordered-score-evidence-v1", "levels": rows})
    transcript: dict[str, object] = {
        "domain": "pocket-ordered-score-v1",
        "status": int(TernaryStatus.ACCEPT if accepted else TernaryStatus.ABSTAIN),
        "level_index": best_index,
        "expected_score": _rational_payload(expected),
        "confidence": _rational_payload(confidence),
        "minimum_confidence": _rational_payload(minimum_confidence),
        "model_root": model_root,
        "request_root": request_root,
        "evidence_root": evidence_root,
    }
    status = TernaryStatus.ACCEPT if accepted else TernaryStatus.ABSTAIN
    return OrderedScoreResult(
        status,
        None if best_index is None else ordered[best_index].key,
        best_index,
        expected,
        confidence,
        probabilities,
        tuple(item.key for item in ordered),
        evidence_root,
        _canonical_hash(transcript),
    )
