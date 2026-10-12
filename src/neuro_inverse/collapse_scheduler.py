"""Classical deterministic Lbit planning for recursive expert expansion.

The name ``collapse`` is a scheduling operation only.  There are no random
amplitudes, qubits, quantum states, or quantum-speedup claims: every score is
an exact integer or :class:`fractions.Fraction` calculation over 256-bit
Hamming distances. ``Lbit`` means the ordinary 256-bit routing primitive.

An optional coupling edge is an exact all-or-nothing page dependency. It is
called an ``entangling`` analogy only in the API documentation; closure is
ordinary deterministic union-find logic. Edge commitments use a
domain-separated SHA-256 oracle. The only cryptographic statement made here
is the conventional one-way assumption for SHA-256, not a proof of it. The
planner is a routing/page-load plan, not a model-quality or accuracy claim.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
import hashlib
from types import MappingProxyType


MAX_HAMMING_DISTANCE = 256
COMMITMENT_DOMAIN = b"NeuroRoute/Lbit/coupling-edge/v1\0"


def commitment_oracle(value: bytes | str) -> str:
    """Return a deterministic domain-separated SHA-256 commitment.

    This is a one-way commitment *assumption* interface, not a cryptographic
    proof or a source of entropy. Length framing prevents concatenation
    ambiguity, and the domain prevents cross-protocol hash reuse.
    """
    if isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, bytes):
        raw = value
    else:
        raise TypeError("commitment input must be bytes or str")
    framed = COMMITMENT_DOMAIN + len(raw).to_bytes(8, "big") + raw
    return hashlib.sha256(framed).hexdigest()


def _edge_payload(left: str, right: str) -> str:
    first, second = sorted((left, right))
    return f"{len(first)}:{first}|{len(second)}:{second}"


@dataclass(frozen=True)
class CouplingEdge:
    """A committed undirected coupling edge (the ``entangling`` analogy)."""

    left: str
    right: str
    commitment: str

    def __post_init__(self) -> None:
        if not isinstance(self.left, str) or not self.left:
            raise ValueError("coupling edge left ID must be non-empty")
        if not isinstance(self.right, str) or not self.right:
            raise ValueError("coupling edge right ID must be non-empty")
        if self.left == self.right:
            raise ValueError("coupling edge cannot connect an ID to itself")
        expected = commitment_oracle(_edge_payload(self.left, self.right))
        if self.commitment != expected:
            raise ValueError("coupling edge commitment mismatch")

    @classmethod
    def commit(cls, left: str, right: str) -> "CouplingEdge":
        return cls(left, right, commitment_oracle(_edge_payload(left, right)))


def _fraction(value: Fraction | int, name: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (Fraction, int)):
        raise TypeError(f"{name} must be an integer or Fraction")
    result = Fraction(value)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


@dataclass(frozen=True)
class LbitExpert:
    """A routed expert and its exact 256-bit Hamming distance."""

    stable_id: str
    distance: int
    coupling_group: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.stable_id, str) or not self.stable_id:
            raise ValueError("stable_id must be a non-empty string")
        if not isinstance(self.distance, int) or isinstance(self.distance, bool):
            raise TypeError("distance must be an integer")
        if not 0 <= self.distance <= MAX_HAMMING_DISTANCE:
            raise ValueError("distance must be between 0 and 256")
        if self.coupling_group is not None and (
            not isinstance(self.coupling_group, str) or not self.coupling_group
        ):
            raise ValueError("coupling_group must be a non-empty string or None")


@dataclass(frozen=True)
class OmissionCertificate:
    """A fail-closed bound proving that a set of experts may be omitted.

    ``bounds`` contains a non-negative exact bound for every expert.  A plan
    may stop only if the certificate is marked valid and the sum for the
    omitted IDs is at most ``tolerance``.  Missing IDs are rejected rather
    than treated as zero, so an incomplete certificate cannot silently enable
    sparse execution.
    """

    bounds: Mapping[str, Fraction | int]
    tolerance: Fraction | int
    valid: bool = True

    def __post_init__(self) -> None:
        normalized: dict[str, Fraction] = {}
        for stable_id, bound in self.bounds.items():
            if not isinstance(stable_id, str) or not stable_id:
                raise ValueError("certificate IDs must be non-empty strings")
            normalized[stable_id] = _fraction(bound, "certificate bound")
        if not isinstance(self.valid, bool):
            raise TypeError("valid must be boolean")
        object.__setattr__(self, "bounds", MappingProxyType(normalized))
        object.__setattr__(self, "tolerance", _fraction(self.tolerance, "tolerance"))

    def permits(self, omitted_ids: Iterable[str]) -> bool:
        omitted = tuple(omitted_ids)
        if not self.valid or any(stable_id not in self.bounds for stable_id in omitted):
            return False
        return sum((self.bounds[stable_id] for stable_id in omitted), Fraction(0)) <= self.tolerance

    def omitted_bound(self, omitted_ids: Iterable[str]) -> Fraction | None:
        omitted = tuple(omitted_ids)
        if any(stable_id not in self.bounds for stable_id in omitted):
            return None
        return sum((self.bounds[stable_id] for stable_id in omitted), Fraction(0))


@dataclass(frozen=True)
class LbitStep:
    """One monotonic recursive expansion state."""

    active_ids: tuple[str, ...]
    tail_mass: Fraction
    omitted_bound: Fraction | None
    stop_allowed: bool


@dataclass(frozen=True)
class LbitPlan:
    """Deterministic result of :func:`plan_collapse`."""

    active_ids: tuple[str, ...]
    ranked_ids: tuple[str, ...]
    weights: Mapping[str, Fraction]
    tail_mass: Fraction
    omitted_bound: Fraction | None
    stopped_by_certificate: bool
    used_all_expert_fallback: bool
    steps: tuple[LbitStep, ...]


def plan_collapse(
    experts: Iterable[LbitExpert],
    *,
    initial_active: int = 1,
    tail_mass_threshold: Fraction | int = Fraction(0),
    power: int = 1,
    certificate: OmissionCertificate | None = None,
    coupling_edges: Iterable[CouplingEdge] = (),
) -> LbitPlan:
    """Plan deterministic recursive expert/page expansion.

    Expert weights are ``1 / (1 + distance)**power``.  The normalized mass of
    omitted experts is exact rational arithmetic.  Ranking ties are resolved
    by stable ID. Selecting one member closes its coupling group or committed
    coupling component (the purely classical ``entangling`` analogy), and each
    closure is recorded as a monotonic step.

    Sparse stopping requires *both* the exact tail mass threshold and a valid
    omission certificate.  If either requirement never holds, all experts are
    returned, which is the fail-closed reference behavior.
    """
    entries = tuple(experts)
    if not entries:
        raise ValueError("at least one expert is required")
    if any(not isinstance(item, LbitExpert) for item in entries):
        raise TypeError("experts must contain LbitExpert values")
    ids = tuple(item.stable_id for item in entries)
    if len(set(ids)) != len(ids):
        raise ValueError("expert stable IDs must be unique")
    if not isinstance(initial_active, int) or isinstance(initial_active, bool) or initial_active < 1:
        raise ValueError("initial_active must be a positive integer")
    threshold = _fraction(tail_mass_threshold, "tail_mass_threshold")
    if threshold > 1:
        raise ValueError("tail_mass_threshold cannot exceed one")
    if not isinstance(power, int) or isinstance(power, bool) or power < 1:
        raise ValueError("power must be a positive integer")

    ranked = tuple(sorted(entries, key=lambda item: (item.distance, item.stable_id)))
    ranked_ids = tuple(item.stable_id for item in ranked)
    weights = MappingProxyType({
        item.stable_id: Fraction(1, (1 + item.distance) ** power) for item in ranked
    })
    total_weight = sum(weights.values(), Fraction(0))
    edge_values = tuple(coupling_edges)
    if any(not isinstance(edge, CouplingEdge) for edge in edge_values):
        raise TypeError("coupling_edges must contain CouplingEdge values")
    parent = {stable_id: stable_id for stable_id in ranked_ids}

    def find(stable_id: str) -> str:
        root = stable_id
        while parent[root] != root:
            root = parent[root]
        while parent[stable_id] != stable_id:
            next_id = parent[stable_id]
            parent[stable_id] = root
            stable_id = next_id
        return root

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            # Stable-ID root selection makes closure independent of input order.
            parent[max(left_root, right_root)] = min(left_root, right_root)

    group_members: dict[str, list[str]] = {}
    for item in ranked:
        if item.coupling_group is not None:
            group_members.setdefault(item.coupling_group, []).append(item.stable_id)
    for members in group_members.values():
        for left, right in zip(members, members[1:]):
            union(left, right)
    for edge in edge_values:
        if edge.left not in parent or edge.right not in parent:
            raise ValueError("coupling edge references an unknown expert")
        union(edge.left, edge.right)
    components: dict[str, tuple[str, ...]] = {}
    for stable_id in ranked_ids:
        root = find(stable_id)
        components[root] = tuple(
            candidate for candidate in ranked_ids if find(candidate) == root
        )

    def make_step(active: set[str]) -> LbitStep:
        ordered_active = tuple(stable_id for stable_id in ranked_ids if stable_id in active)
        omitted = tuple(stable_id for stable_id in ranked_ids if stable_id not in active)
        tail = sum((weights[stable_id] for stable_id in omitted), Fraction(0)) / total_weight
        bound = certificate.omitted_bound(omitted) if certificate is not None else None
        allowed = tail <= threshold and certificate is not None and certificate.permits(omitted)
        return LbitStep(ordered_active, tail, bound, allowed)

    active: set[str] = set()
    steps: list[LbitStep] = []
    cursor = 0
    while cursor < len(ranked_ids):
        stable_id = ranked_ids[cursor]
        cursor += 1
        if stable_id in active:
            continue
        active.add(stable_id)
        active.update(components[find(stable_id)])
        step = make_step(active)
        steps.append(step)
        if len(active) >= initial_active and step.stop_allowed and len(active) < len(ranked_ids):
            return LbitPlan(
                step.active_ids, ranked_ids, weights, step.tail_mass, step.omitted_bound,
                True, False, tuple(steps),
            )

    final = steps[-1]
    return LbitPlan(
        final.active_ids, ranked_ids, weights, final.tail_mass, final.omitted_bound,
        False, True, tuple(steps),
    )


# Backward-compatible descriptive aliases; Lbit is the canonical terminology.
CollapseExpert = LbitExpert
CollapsePlan = LbitPlan
CollapseStep = LbitStep

__all__ = [
    "COMMITMENT_DOMAIN", "CollapseExpert", "CollapsePlan", "CollapseStep",
    "CouplingEdge", "LbitExpert", "LbitPlan", "LbitStep", "MAX_HAMMING_DISTANCE",
    "OmissionCertificate", "commitment_oracle", "plan_collapse",
]
