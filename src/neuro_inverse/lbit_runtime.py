"""Deterministic Lbit control plane for a 256-expert top-k MoE.

This module turns :mod:`collapse_scheduler`'s immutable plan into an actual
page-selection boundary.  It is deliberately independent of a tensor
backend: a caller gets authenticated page IDs and can then load those pages
from SSD, RAM, or another verified store.  A malformed registry, a bad page
commitment, an incomplete certificate, or an invalid query never enables
silence: selection returns the stable all-expert reference set.

``Lbit`` is the project's name for a 256-bit classical routing value.  The
"oracle" here is a domain-separated SHA-256 commitment, and "coupling" is a
committed, all-or-nothing page dependency.  No probabilistic or quantum
semantics are used.


No quantum semantics are claimed: oracle/coupling terms name deterministic software
contracts only; all routing and omission logic executes on ordinary classical data."""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from types import MappingProxyType

from .collapse_scheduler import (
    CouplingEdge,
    LbitExpert,
    LbitPlan,
    OmissionCertificate,
    plan_collapse,
)


PAGE_DOMAIN = b"NeuroRoute/Lbit/page/v1\0"
QUERY_DOMAIN = b"NeuroRoute/Lbit/query/v1\0"
CACHE_DOMAIN = b"NeuroRoute/Lbit/cache-key/v1\0"
HISTORY_DOMAIN = b"NeuroRoute/Lbit/history/v1\0"
PAGE_BYTES = 32
EXPERT_COUNT = 256
DEFAULT_EXPERT_CACHE_BYTES = 1 * 1024**3
DEFAULT_PROCESS_BUDGET_BYTES = 14 * 1024**3 + 512 * 1024**2


def _hash_framed(domain: bytes, value: bytes) -> str:
    return hashlib.sha256(domain + len(value).to_bytes(8, "big") + value).hexdigest()


def _hex_digest(value: str, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be a 64-character SHA-256 hex digest")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be hexadecimal") from exc
    return value.lower()


def _fraction(value: Fraction | int, name: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (Fraction, int)):
        raise TypeError(f"{name} must be an integer or Fraction")
    result = Fraction(value)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _canonical_page_payload(
    stable_id: str,
    code: bytes,
    payload_sha256: str,
    payload_size: int,
    bound: Fraction,
    coupling_group: str | None,
) -> bytes:
    # JSON with sorted keys is only used after all values have been validated;
    # it gives the commitment a stable cross-language representation.
    return json.dumps(
        {
            "bound_denominator": bound.denominator,
            "bound_numerator": bound.numerator,
            "code": code.hex(),
            "coupling_group": coupling_group,
            "payload_sha256": payload_sha256,
            "payload_size": payload_size,
            "stable_id": stable_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@dataclass(frozen=True)
class LbitPage:
    """Authenticated metadata for one expert's pageable payload."""

    stable_id: str
    code: bytes
    payload_sha256: str
    omission_bound: Fraction | int
    commitment: str
    coupling_group: str | None = None
    payload_size: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.stable_id, str) or not self.stable_id:
            raise ValueError("stable_id must be a non-empty string")
        if not isinstance(self.code, bytes) or len(self.code) != PAGE_BYTES:
            raise ValueError("Lbit page code must contain exactly 32 bytes")
        digest = _hex_digest(self.payload_sha256, "payload_sha256")
        bound = _fraction(self.omission_bound, "omission_bound")
        if not isinstance(self.payload_size, int) or isinstance(self.payload_size, bool) or self.payload_size < 0:
            raise ValueError("payload_size must be a non-negative integer")
        if self.coupling_group is not None and (
            not isinstance(self.coupling_group, str) or not self.coupling_group
        ):
            raise ValueError("coupling_group must be a non-empty string or None")
        expected = page_commitment(
            self.stable_id, self.code, digest, self.payload_size, bound, self.coupling_group
        )
        if self.commitment != expected:
            raise ValueError("Lbit page commitment mismatch")
        object.__setattr__(self, "payload_sha256", digest)
        object.__setattr__(self, "omission_bound", bound)
        object.__setattr__(self, "commitment", self.commitment.lower())

    @classmethod
    def commit(
        cls,
        stable_id: str,
        code: bytes,
        payload: bytes,
        omission_bound: Fraction | int,
        coupling_group: str | None = None,
    ) -> "LbitPage":
        digest = hashlib.sha256(payload).hexdigest()
        bound = _fraction(omission_bound, "omission_bound")
        return cls(
            stable_id,
            code,
            digest,
            bound,
            page_commitment(stable_id, code, digest, len(payload), bound, coupling_group),
            coupling_group,
            len(payload),
        )

    def verify_payload(self, payload: bytes) -> bool:
        """Verify the external page bytes against the authenticated digest."""
        return isinstance(payload, bytes) and hashlib.sha256(payload).hexdigest() == self.payload_sha256


def page_commitment(
    stable_id: str,
    code: bytes,
    payload_sha256: str,
    payload_size: int,
    omission_bound: Fraction | int,
    coupling_group: str | None = None,
) -> str:
    """Create the domain-separated commitment stored in :class:`LbitPage`."""
    if not isinstance(stable_id, str) or not stable_id:
        raise ValueError("stable_id must be a non-empty string")
    if not isinstance(code, bytes) or len(code) != PAGE_BYTES:
        raise ValueError("Lbit page code must contain exactly 32 bytes")
    digest = _hex_digest(payload_sha256, "payload_sha256")
    bound = _fraction(omission_bound, "omission_bound")
    if not isinstance(payload_size, int) or isinstance(payload_size, bool) or payload_size < 0:
        raise ValueError("payload_size must be a non-negative integer")
    if coupling_group is not None and (not isinstance(coupling_group, str) or not coupling_group):
        raise ValueError("coupling_group must be a non-empty string or None")
    return _hash_framed(
        PAGE_DOMAIN,
        _canonical_page_payload(stable_id, code, digest, payload_size, bound, coupling_group),
    )


def query_commitment(query: bytes) -> str:
    """Commit a 256-bit query without conflating it with edge/page hashes."""
    if not isinstance(query, bytes) or len(query) != PAGE_BYTES:
        raise ValueError("query must contain exactly 32 bytes")
    return _hash_framed(QUERY_DOMAIN, query)


@dataclass(frozen=True)
class LbitSelection:
    """Stable page selection plus its audit/cache identities."""

    active_ids: tuple[str, ...]
    ranked_ids: tuple[str, ...]
    plan: LbitPlan | None
    query_commitment: str
    cache_key: str
    history_key: str
    used_all_expert_fallback: bool
    cache_hit: bool
    fail_closed_reason: str | None
    resident_bytes: int
    resident_admitted: bool


class LbitMoEControlPlane:
    """Bounded deterministic selector for a 256-expert, top-6 MoE.

    The selector only returns page IDs.  Page loading and neural evaluation
    remain separate, which keeps the control plane cheap and makes its
    fail-closed behavior testable without loading the model engine.
    """

    def __init__(
        self,
        pages: Iterable[LbitPage],
        *,
        coupling_edges: Iterable[CouplingEdge] = (),
        certificate: OmissionCertificate | None = None,
        top_k: int = 6,
        tail_mass_threshold: Fraction | int = 0,
        power: int = 1,
        cache_entries: int = 256,
        resident_budget_bytes: int = DEFAULT_EXPERT_CACHE_BYTES,
        fixed_resident_bytes: int = 0,
        process_budget_bytes: int = DEFAULT_PROCESS_BUDGET_BYTES,
        require_256: bool = True,
    ) -> None:
        page_values = tuple(pages)
        if any(not isinstance(page, LbitPage) for page in page_values):
            raise TypeError("pages must contain LbitPage values")
        by_id = {page.stable_id: page for page in page_values}
        if len(by_id) != len(page_values):
            raise ValueError("page stable IDs must be unique")
        if require_256 and len(page_values) != EXPERT_COUNT:
            raise ValueError("LbitMoEControlPlane requires exactly 256 expert pages")
        if not page_values:
            raise ValueError("at least one Lbit page is required")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= len(page_values):
            raise ValueError("top_k must be between one and the expert count")
        if not isinstance(cache_entries, int) or isinstance(cache_entries, bool) or cache_entries < 0:
            raise ValueError("cache_entries must be non-negative")
        if not isinstance(resident_budget_bytes, int) or isinstance(resident_budget_bytes, bool) or resident_budget_bytes < 1:
            raise ValueError("resident_budget_bytes must be a positive integer")
        if not isinstance(fixed_resident_bytes, int) or isinstance(fixed_resident_bytes, bool) or fixed_resident_bytes < 0:
            raise ValueError("fixed_resident_bytes must be a non-negative integer")
        if not isinstance(process_budget_bytes, int) or isinstance(process_budget_bytes, bool) or process_budget_bytes < 1:
            raise ValueError("process_budget_bytes must be a positive integer")
        if fixed_resident_bytes > process_budget_bytes:
            raise ValueError("fixed_resident_bytes cannot exceed process_budget_bytes")
        if not isinstance(power, int) or isinstance(power, bool) or power < 1:
            raise ValueError("power must be a positive integer")
        # Validate exact types/ranges once; scheduler repeats the arithmetic
        # per query, while this check prevents malformed configuration drift.
        threshold = _fraction(tail_mass_threshold, "tail_mass_threshold")
        if threshold > 1:
            raise ValueError("tail_mass_threshold cannot exceed one")
        edge_values = tuple(coupling_edges)
        if any(not isinstance(edge, CouplingEdge) for edge in edge_values):
            raise TypeError("coupling_edges must contain CouplingEdge values")
        unknown = {edge.left for edge in edge_values} | {edge.right for edge in edge_values}
        if not unknown <= set(by_id):
            raise ValueError("coupling edge references an unknown page")
        if certificate is not None and not isinstance(certificate, OmissionCertificate):
            raise TypeError("certificate must be an OmissionCertificate or None")
        certificate_integrity = certificate is not None and certificate.valid
        if certificate_integrity:
            certificate_integrity = set(certificate.bounds) == set(by_id) and all(
                certificate.bounds[stable_id] == by_id[stable_id].omission_bound
                for stable_id in by_id
            )
        self._pages = dict(by_id)
        self._expected_ids = tuple(sorted(by_id))
        self._expected_page_commitments = tuple(
            (page.stable_id, page.commitment) for page in (by_id[item] for item in self._expected_ids)
        )
        self._registry_commitment = self._compute_registry_commitment(self._pages)
        self._edges = edge_values
        self._certificate = certificate
        self._certificate_integrity = certificate_integrity
        self._top_k = top_k
        self._threshold = threshold
        self._power = power
        self._cache_entries = cache_entries
        self._resident_budget_bytes = resident_budget_bytes
        self._fixed_resident_bytes = fixed_resident_bytes
        self._process_budget_bytes = process_budget_bytes
        self._cache: OrderedDict[str, LbitSelection] = OrderedDict()

    @staticmethod
    def _compute_registry_commitment(pages: Mapping[str, LbitPage]) -> str:
        payload = "|".join(
            f"{stable_id}:{pages[stable_id].commitment}" for stable_id in sorted(pages)
        ).encode("utf-8")
        return _hash_framed(PAGE_DOMAIN + b"registry\0", payload)

    def _integrity_ok(self) -> bool:
        if tuple(sorted(self._pages)) != self._expected_ids:
            return False
        if tuple((key, self._pages[key].commitment) for key in self._expected_ids) != self._expected_page_commitments:
            return False
        return self._compute_registry_commitment(self._pages) == self._registry_commitment

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    @property
    def cache_capacity(self) -> int:
        return self._cache_entries

    @property
    def resident_budget_bytes(self) -> int:
        """Maximum decoded expert-page bytes admitted for one selection."""
        return self._resident_budget_bytes

    @property
    def fixed_resident_bytes(self) -> int:
        """Bytes reserved for non-routed weights/runtime (for example DS4)."""
        return self._fixed_resident_bytes

    @property
    def process_budget_bytes(self) -> int:
        """Hard process target; admission includes fixed plus expert bytes."""
        return self._process_budget_bytes

    @property
    def expert_count(self) -> int:
        return len(self._expected_ids)

    def clear_cache(self) -> None:
        self._cache.clear()

    def _keys(self, query: bytes, history: bytes, reason: str | None) -> tuple[str, str, str]:
        q = query_commitment(query)
        registry = self._registry_commitment
        config = f"{self._top_k}|{self._threshold.numerator}/{self._threshold.denominator}|{self._power}|{reason or ''}".encode()
        cache = _hash_framed(CACHE_DOMAIN, q.encode() + registry.encode() + config + history)
        history_key = _hash_framed(HISTORY_DOMAIN, history + cache.encode())
        return q, cache, history_key

    def _fallback(self, query: bytes, history: bytes, reason: str) -> LbitSelection:
        q, cache, history_key = self._keys(query, history, reason)
        return LbitSelection(
            self._expected_ids,
            self._expected_ids,
            None,
            q,
            cache,
            history_key,
            True,
            False,
            reason,
            sum(self._pages[item].payload_size for item in self._expected_ids if item in self._pages),
            False,
        )

    def select(self, query: bytes, *, history: bytes = b"") -> LbitSelection:
        """Select pages, recursively expanding until the certificate permits stop.

        ``history`` is caller-supplied authenticated context (for example a
        previous deterministic envelope key); it is included in both cache and
        history identities.  The LRU stores at most ``cache_entries`` plans.
        """
        if not isinstance(history, bytes):
            raise TypeError("history must be bytes")
        if len(history) > 4096:
            raise ValueError("history is too large")
        try:
            q = query_commitment(query)
        except (TypeError, ValueError):
            # Query syntax errors are not allowed to turn into an accidental
            # sparse call.  The caller still gets the full stable reference set.
            if isinstance(query, bytes):
                return self._fallback(query if len(query) == PAGE_BYTES else bytes(PAGE_BYTES), history, "invalid_query")
            raise
        if not self._integrity_ok():
            return self._fallback(query, history, "registry_integrity")
        if self._certificate is None:
            return self._fallback(query, history, "missing_certificate")
        if not self._certificate_integrity:
            return self._fallback(query, history, "certificate_integrity")
        cache_key = self._keys(query, history, None)[1]
        if cache_key in self._cache:
            cached = self._cache.pop(cache_key)
            value = LbitSelection(
                cached.active_ids, cached.ranked_ids, cached.plan,
                cached.query_commitment, cached.cache_key, cached.history_key,
                cached.used_all_expert_fallback, True, cached.fail_closed_reason,
                cached.resident_bytes, cached.resident_admitted,
            )
            self._cache[cache_key] = value
            return value

        query_int = int.from_bytes(query, "big")
        experts = tuple(
            LbitExpert(
                page.stable_id,
                (query_int ^ int.from_bytes(page.code, "big")).bit_count(),
                page.coupling_group,
            )
            for page in self._pages.values()
        )
        # Constructor validation binds every certificate bound to the same
        # value committed in its page metadata before sparse execution.
        plan = plan_collapse(
            experts,
            initial_active=self._top_k,
            tail_mass_threshold=self._threshold,
            power=self._power,
            certificate=self._certificate,
            coupling_edges=self._edges,
        )
        q, cache, history_key = self._keys(query, history, None)
        value = LbitSelection(
            plan.active_ids,
            plan.ranked_ids,
            plan,
            q,
            cache,
            history_key,
            plan.used_all_expert_fallback,
            False,
            None,
            sum(self._pages[item].payload_size for item in plan.active_ids),
            sum(self._pages[item].payload_size for item in plan.active_ids) <= self._resident_budget_bytes
            and self._fixed_resident_bytes + sum(self._pages[item].payload_size for item in plan.active_ids)
            <= self._process_budget_bytes,
        )
        if not value.resident_admitted:
            # The selector never silently truncates a model to satisfy RAM.
            # Return the full reference set and make the admission failure
            # explicit to the page loader/caller.
            value = self._fallback(query, history, "resident_budget")
        if self._cache_entries:
            self._cache[cache] = value
            while len(self._cache) > self._cache_entries:
                self._cache.popitem(last=False)
        return value


__all__ = [
    "CACHE_DOMAIN", "EXPERT_COUNT", "HISTORY_DOMAIN", "LbitMoEControlPlane",
    "LbitPage", "LbitSelection", "PAGE_BYTES", "PAGE_DOMAIN", "QUERY_DOMAIN",
    "page_commitment", "query_commitment",
]
