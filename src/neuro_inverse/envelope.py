"""Deterministic control-plane envelope for proposal-only workers.

This module deliberately does not make an LLM deterministic.  It makes the
request identity, conflict handling, cache transitions, committed history,
and scheduled retries deterministic around an arbitrary proposal source.
Worker wall-clock latency is measured for observability and is never included
in cache identity or ordering decisions.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import numbers
import threading
import time
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


Status = Literal["CACHE_MISS", "CACHE_HIT", "COMMITTED", "FAIL_SAFE_FALLBACK"]


def _normalize(value: Any, *, normalize_text: bool) -> Any:
    """Convert supported JSON-like values to a canonical, immutable shape."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("canonical envelopes do not accept NaN or infinity")
        if value == 0.0:
            return 0
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, str):
        text = value
        if normalize_text:
            text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
            text = " ".join(text.split()).casefold()
        return text
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise TypeError("canonical envelope mapping keys must be strings")
            key = unicodedata.normalize("NFC", raw_key) if normalize_text else raw_key
            if key in normalized:
                raise ValueError(f"duplicate canonical envelope key: {key!r}")
            normalized[key] = _normalize(raw_value, normalize_text=normalize_text)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item, normalize_text=normalize_text) for item in value]
    raise TypeError(f"unsupported canonical envelope value: {type(value).__name__}")


@dataclass(frozen=True)
class NormalizationPolicy:
    """Explicit identity policy; ``exact-v1`` is the safe default."""

    name: str
    normalize_text: bool


EXACT_BYTES_V1 = NormalizationPolicy("exact-v1", False)
TEXT_EQUIVALENCE_V1 = NormalizationPolicy("text-equivalence-v1", True)


def canonical_json(value: Any, *, normalize_text: bool = False) -> str:
    """Serialize JSON-like data with explicit ordering and finite numbers."""
    normalized = _normalize(value, normalize_text=normalize_text)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_sha256(value: Any, *, normalize_text: bool = False) -> str:
    return hashlib.sha256(canonical_json(value, normalize_text=normalize_text).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CanonicalEnvelope:
    payload: Mapping[str, Any]
    canonical: str
    identity: str
    conflict_key: str
    normalization_policy: str

    @classmethod
    def create(
        cls, payload: Mapping[str, Any], *, conflict_key: str | None = None,
        policy: NormalizationPolicy = EXACT_BYTES_V1,
    ) -> "CanonicalEnvelope":
        if not isinstance(payload, Mapping):
            raise TypeError("envelope payload must be a mapping")
        if not isinstance(policy, NormalizationPolicy):
            raise TypeError("policy must be a NormalizationPolicy")
        normalized = _normalize(payload, normalize_text=policy.normalize_text)
        if not isinstance(normalized, dict):  # defensive; mappings normalize to dicts
            raise TypeError("envelope payload must normalize to a mapping")
        identity_document = {"normalization_policy": policy.name, "payload": normalized}
        canonical = json.dumps(identity_document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        identity = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        supplied = conflict_key if conflict_key is not None else normalized.get("conflict_key", identity)
        if not isinstance(supplied, str) or not supplied:
            raise ValueError("conflict_key must be a non-empty string")
        return cls(payload=normalized, canonical=canonical, identity=identity, conflict_key=supplied,
                   normalization_policy=policy.name)


@dataclass(frozen=True)
class Proposal:
    worker_id: str
    payload: Any
    payload_sha256: str
    elapsed_ms: float

    @classmethod
    def from_payload(cls, worker_id: str, payload: Any, elapsed_ms: float) -> "Proposal":
        if not isinstance(worker_id, str) or not worker_id:
            raise ValueError("worker_id must be a non-empty string")
        if not math.isfinite(elapsed_ms) or elapsed_ms < 0:
            raise ValueError("elapsed_ms must be finite and non-negative")
        # Proposal bytes are for audit identity only; unlike request identity,
        # output text is not case-folded or whitespace-collapsed.
        digest = canonical_sha256(payload, normalize_text=False)
        return cls(worker_id, copy.deepcopy(payload), digest, float(elapsed_ms))


Worker = Callable[[CanonicalEnvelope], Any]


@dataclass(frozen=True)
class WorkerFault:
    worker_id: str
    error_type: str
    error: str
    elapsed_ms: float


class EphemeralWorkerPool:
    """Run proposal workers in stable ID order; workers cannot commit state."""

    def __init__(self, workers: Mapping[str, Worker], *, max_workers: int | None = None) -> None:
        if not workers:
            raise ValueError("at least one proposal worker is required")
        if any(not isinstance(key, str) or not key for key in workers):
            raise ValueError("worker IDs must be non-empty strings")
        if max_workers is not None and max_workers < 1:
            raise ValueError("max_workers must be positive")
        self.workers = dict(workers)
        self.max_workers = max_workers
        self.calls = 0

    def propose(self, envelope: CanonicalEnvelope) -> tuple[Proposal, ...]:
        selected = sorted(self.workers)[: self.max_workers]
        proposals: list[Proposal] = []
        for worker_id in selected:
            started = time.perf_counter()
            self.calls += 1
            try:
                result = self.workers[worker_id](envelope)
                if isinstance(result, Proposal):
                    proposal = result
                    if proposal.worker_id != worker_id:
                        raise ValueError("worker returned a proposal owned by another worker")
                    proposals.append(proposal)
                else:
                    proposals.append(Proposal.from_payload(
                        worker_id, result, (time.perf_counter() - started) * 1000
                    ))
            except Exception:
                # A failed ephemeral worker is not a committed failure record;
                # the envelope simply has no proposal from that worker.
                continue
        return tuple(sorted(proposals, key=lambda item: (item.payload_sha256, item.worker_id)))


@dataclass(frozen=True)
class CacheEntry:
    envelope_identity: str
    conflict_key: str
    payload: Any
    proposal_sha256: str
    worker_id: str


@dataclass(frozen=True)
class FailSafeLock:
    conflict_key: str
    reason: str
    first_identity: str


class EnvelopeCache:
    """Immutable-entry cache with an irreversible fail-safe conflict lock."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._entries: dict[str, CacheEntry] = {}
        self._conflicts: dict[str, str] = {}
        self._locks: dict[str, FailSafeLock] = {}
        self._tail = "0" * 64
        self._next_index = 0
        self._io_lock = threading.Lock()
        if self.path is not None and self.path.exists():
            self._reload()

    def _append(self, event: Mapping[str, Any]) -> None:
        if self.path is None:
            return
        body = {"index": self._next_index, "previous_hash": self._tail, "event": _normalize(event, normalize_text=False)}
        record_hash = canonical_sha256(body, normalize_text=False)
        record = {**body, "record_hash": record_hash}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(record, normalize_text=False) + "\n")
            handle.flush()
            import os
            os.fsync(handle.fileno())
        self._tail, self._next_index = record_hash, self._next_index + 1

    def _reload(self) -> None:
        tail = "0" * 64
        expected_index = 0
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):  # type: ignore[union-attr]
            try:
                raw = json.loads(line)
                record_hash = raw.pop("record_hash")
                if raw["index"] != expected_index or raw["previous_hash"] != tail:
                    raise ValueError("cache journal link mismatch")
                if canonical_sha256(raw, normalize_text=False) != record_hash:
                    raise ValueError("cache journal hash mismatch")
                event = raw["event"]
                if event["type"] == "commit":
                    if event["conflict_key"] in self._locks:
                        raise ValueError("cache commit appears after fail-safe lock")
                    entry = CacheEntry(
                        event["envelope_identity"], event["conflict_key"], event["payload"],
                        event["proposal_sha256"], event["worker_id"],
                    )
                    if entry.envelope_identity in self._entries:
                        raise ValueError("duplicate cache identity")
                    if event["conflict_key"] in self._conflicts and self._conflicts[event["conflict_key"]] != entry.envelope_identity:
                        raise ValueError("cache conflict journal is inconsistent")
                    self._entries[entry.envelope_identity] = entry
                    self._conflicts[entry.conflict_key] = entry.envelope_identity
                elif event["type"] == "lock":
                    lock = FailSafeLock(event["conflict_key"], event["reason"], event["first_identity"])
                    if lock.conflict_key in self._locks and self._locks[lock.conflict_key] != lock:
                        raise ValueError("cache lock was overwritten")
                    self._locks[lock.conflict_key] = lock
                else:
                    raise ValueError("unknown cache journal event")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid cache journal at line {line_number}") from exc
            tail, expected_index = record_hash, expected_index + 1
        self._tail, self._next_index = tail, expected_index

    def lookup(self, envelope: CanonicalEnvelope) -> CacheEntry | FailSafeLock | None:
        if envelope.conflict_key in self._locks:
            return self._locks[envelope.conflict_key]
        identity = self._conflicts.get(envelope.conflict_key)
        if identity is not None and identity != envelope.identity:
            return self.lock_fallback(envelope, "conflict.intercept")
        return self._entries.get(envelope.identity)

    def commit(self, envelope: CanonicalEnvelope, proposal: Proposal) -> CacheEntry:
        locked = self._locks.get(envelope.conflict_key)
        if locked is not None:
            raise RuntimeError("FAIL_SAFE_FALLBACK cache lock is immutable")
        existing_identity = self._conflicts.get(envelope.conflict_key)
        if existing_identity is not None and existing_identity != envelope.identity:
            self.lock_fallback(envelope, "conflict.intercept")
            raise RuntimeError("conflict intercepted by FAIL_SAFE_FALLBACK")
        existing = self._entries.get(envelope.identity)
        if existing is not None:
            return existing
        entry = CacheEntry(
            envelope.identity, envelope.conflict_key, copy.deepcopy(proposal.payload),
            proposal.payload_sha256, proposal.worker_id,
        )
        with self._io_lock:
            self._append({
                "type": "commit", "envelope_identity": entry.envelope_identity,
                "conflict_key": entry.conflict_key, "payload": entry.payload,
                "proposal_sha256": entry.proposal_sha256, "worker_id": entry.worker_id,
            })
        self._entries[envelope.identity] = entry
        self._conflicts[envelope.conflict_key] = envelope.identity
        return entry

    def lock_fallback(self, envelope: CanonicalEnvelope, reason: str) -> FailSafeLock:
        existing = self._locks.get(envelope.conflict_key)
        if existing is not None:
            return existing
        lock = FailSafeLock(
            envelope.conflict_key, reason,
            self._conflicts.get(envelope.conflict_key, envelope.identity),
        )
        with self._io_lock:
            self._append({
                "type": "lock", "conflict_key": lock.conflict_key,
                "reason": lock.reason, "first_identity": lock.first_identity,
            })
        self._locks[envelope.conflict_key] = lock
        return lock

    @property
    def locks(self) -> tuple[FailSafeLock, ...]:
        return tuple(self._locks[key] for key in sorted(self._locks))


@dataclass(frozen=True)
class HistoryRecord:
    index: int
    previous_hash: str
    event: Mapping[str, Any]
    logical_time: int
    committed_at_ns: int
    record_hash: str


class CommittedHistory:
    """Append-only JSONL hash chain for committed envelope events."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._tail = "0" * 64
        self._next_index = 0
        if self.path.exists():
            self.verify()

    @staticmethod
    def _record_hash(record: Mapping[str, Any]) -> str:
        return hashlib.sha256(canonical_json(record, normalize_text=False).encode("utf-8")).hexdigest()

    def append(self, event: Mapping[str, Any]) -> HistoryRecord:
        if not isinstance(event, Mapping):
            raise TypeError("history event must be a mapping")
        normalized_event = _normalize(event, normalize_text=False)
        with self._lock:
            body = {
                "index": self._next_index,
                "previous_hash": self._tail,
                "event": normalized_event,
                "logical_time": self._next_index,
            }
            record_hash = self._record_hash(body)
            # Wall-clock time is observability only and is intentionally not
            # hashed, so replaying the same logical event sequence is stable.
            record = {**body, "committed_at_ns": time.time_ns(), "record_hash": record_hash}
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json(record, normalize_text=False) + "\n")
                handle.flush()
                import os
                os.fsync(handle.fileno())
            self._tail = record_hash
            self._next_index += 1
            return HistoryRecord(**record)

    def verify(self) -> tuple[HistoryRecord, ...]:
        tail = "0" * 64
        expected_index = 0
        records: list[HistoryRecord] = []
        if self.path.exists():
            for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
                try:
                    raw = json.loads(line)
                    record_hash = raw.pop("record_hash")
                    committed_at_ns = raw.pop("committed_at_ns")
                    if raw["index"] != expected_index or raw["logical_time"] != expected_index or raw["previous_hash"] != tail:
                        raise ValueError("history link mismatch")
                    if self._record_hash(raw) != record_hash:
                        raise ValueError("history record hash mismatch")
                    record = HistoryRecord(record_hash=record_hash, committed_at_ns=committed_at_ns, **raw)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(f"invalid committed history at line {line_number}") from exc
                records.append(record)
                tail, expected_index = record_hash, expected_index + 1
        self._tail, self._next_index = tail, expected_index
        return tuple(records)

    @property
    def tail(self) -> str:
        return self._tail


@dataclass(frozen=True)
class EnvelopeDecision:
    status: Status
    envelope_identity: str
    conflict_key: str
    payload: Any | None
    worker_id: str | None
    proposal_sha256: str | None
    elapsed_ms: float
    shock_boundary: bool = False


class DeterministicEnvelope:
    """Own cache/commit transitions around proposal-only workers."""

    def __init__(self, *, cache: EnvelopeCache | None = None, history: CommittedHistory | None = None) -> None:
        self.cache = cache or EnvelopeCache()
        self.history = history
        self.shock_boundaries: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def execute(
        self,
        payload: Mapping[str, Any],
        worker: Worker | EphemeralWorkerPool,
        *,
        validator: Callable[[Any], bool] | None = None,
        policy: NormalizationPolicy = EXACT_BYTES_V1,
        validation_retries: int = 0,
        judge: Callable[[tuple[Proposal, ...]], Proposal] | None = None,
        scenario_index: int | None = None,
        shock_boundary: int | None = None,
    ) -> EnvelopeDecision:
        if validation_retries < 0:
            raise ValueError("validation_retries must be non-negative")
        started = time.perf_counter()
        envelope = CanonicalEnvelope.create(payload, policy=policy)
        with self._lock:
            existing = self.cache.lookup(envelope)
            if isinstance(existing, FailSafeLock):
                elapsed = (time.perf_counter() - started) * 1000
                boundary = shock_boundary is not None and scenario_index == shock_boundary
                if boundary:
                    self.shock_boundaries.append({
                        "scenario_index": scenario_index,
                        "conflict_key": envelope.conflict_key,
                        "reason": existing.reason,
                    })
                return EnvelopeDecision(
                    "FAIL_SAFE_FALLBACK", envelope.identity, envelope.conflict_key, None,
                    None, None, elapsed, boundary,
                )
            if isinstance(existing, CacheEntry):
                elapsed = (time.perf_counter() - started) * 1000
                return EnvelopeDecision(
                    "CACHE_HIT", envelope.identity, envelope.conflict_key,
                    copy.deepcopy(existing.payload), existing.worker_id, existing.proposal_sha256, elapsed,
                )

            proposal: Proposal | None = None
            for _attempt in range(validation_retries + 1):
                proposals = worker.propose(envelope) if isinstance(worker, EphemeralWorkerPool) else self._one(worker, envelope)
                if proposals:
                    hashes = {item.payload_sha256 for item in proposals}
                    if len(hashes) > 1:
                        if judge is None:
                            self.cache.lock_fallback(envelope, "proposal.disagreement")
                            proposals = ()
                            candidate = None
                            break
                        else:
                            candidate = judge(proposals)
                            if candidate not in proposals:
                                raise ValueError("judge selected a proposal not returned by a worker")
                            proposals = (candidate,)
                    candidate = proposals[0] if proposals else None
                else:
                    candidate = None
                if candidate is not None:
                    if validator is None or validator(candidate.payload):
                        proposal = candidate
                        break
            if proposal is None:
                lock = self.cache.lock_fallback(envelope, "proposal.none" if validator is None else "proposal.contract")
                elapsed = (time.perf_counter() - started) * 1000
                return EnvelopeDecision("FAIL_SAFE_FALLBACK", envelope.identity, lock.conflict_key, None, None, None, elapsed)
            try:
                entry = self.cache.commit(envelope, proposal)
            except RuntimeError:
                lock = self.cache.lock_fallback(envelope, "conflict.intercept")
                elapsed = (time.perf_counter() - started) * 1000
                return EnvelopeDecision("FAIL_SAFE_FALLBACK", envelope.identity, lock.conflict_key, None, None, None, elapsed)
            if self.history is not None:
                self.history.append({
                    "type": "envelope.commit", "envelope_identity": envelope.identity,
                    "conflict_key": envelope.conflict_key, "proposal_sha256": proposal.payload_sha256,
                    "worker_id": proposal.worker_id,
                })
            elapsed = (time.perf_counter() - started) * 1000
            return EnvelopeDecision(
                "COMMITTED", envelope.identity, envelope.conflict_key,
                copy.deepcopy(entry.payload), entry.worker_id, entry.proposal_sha256, elapsed,
            )

    @staticmethod
    def _one(worker: Worker, envelope: CanonicalEnvelope) -> tuple[Proposal, ...]:
        started = time.perf_counter()
        try:
            result = worker(envelope)
        except Exception:
            return ()
        if isinstance(result, Proposal):
            return (result,)
        return (Proposal.from_payload(getattr(worker, "worker_id", "worker"), result, (time.perf_counter() - started) * 1000),)


@dataclass(frozen=True)
class ScheduledJob:
    job_id: str
    due_tick: int
    action: Callable[[int], bool]
    priority: int = 0
    retry_budget: int = 0
    retry_delay: int = 1
    interval: int | None = None
    attempt: int = 0
    sequence: int = 0


@dataclass(frozen=True)
class JobEvent:
    job_id: str
    tick: int
    attempt: int
    success: bool
    retry_scheduled: bool
    elapsed_ms: float


class DeterministicCron:
    """Logical-tick scheduler with stable ordering and bounded retries."""

    def __init__(self) -> None:
        self._jobs: list[ScheduledJob] = []
        self._sequence = 0
        self.events: list[JobEvent] = []

    def add(self, job: ScheduledJob) -> None:
        if not job.job_id or job.due_tick < 0 or job.retry_budget < 0 or job.retry_delay < 1:
            raise ValueError("invalid scheduled job")
        if job.interval is not None and job.interval < 1:
            raise ValueError("interval must be positive")
        self._jobs.append(ScheduledJob(**{**job.__dict__, "sequence": self._sequence}))
        self._sequence += 1

    def run_until(self, tick: int) -> tuple[JobEvent, ...]:
        if tick < 0:
            raise ValueError("tick must be non-negative")
        emitted: list[JobEvent] = []
        while True:
            due = [job for job in self._jobs if job.due_tick <= tick]
            if not due:
                break
            job = min(due, key=lambda item: (item.due_tick, item.priority, item.job_id, item.sequence))
            self._jobs.remove(job)
            started = time.perf_counter()
            try:
                success = bool(job.action(job.attempt))
            except Exception:
                success = False
            elapsed = (time.perf_counter() - started) * 1000
            retry = not success and job.attempt < job.retry_budget
            event = JobEvent(job.job_id, job.due_tick, job.attempt, success, retry, elapsed)
            self.events.append(event)
            emitted.append(event)
            if success and job.interval is not None:
                self.add(ScheduledJob(
                    job.job_id, job.due_tick + job.interval, job.action,
                    job.priority, job.retry_budget, job.retry_delay, job.interval,
                ))
            elif retry:
                self.add(ScheduledJob(
                    job.job_id, job.due_tick + job.retry_delay * (job.attempt + 1), job.action,
                    job.priority, job.retry_budget, job.retry_delay, job.interval, job.attempt + 1,
                ))
        return tuple(emitted)


@dataclass(frozen=True)
class StressProfile:
    name: str
    M: int
    scenarios: int = 1000
    distinct_identities: int = 1
    validation_retries: int = 0


@dataclass(frozen=True)
class StressReport:
    profile: str
    M: int
    scenario_count: int
    baseline_misses: int
    normalized_hits: int
    validation_retries: int
    outputs: int
    worker_calls: int
    shock_conflicts: int
    shock_lock_hits: int
    shock_boundary_index: int
    elapsed_ms: float


def _equivalent_text(index: int) -> str:
    variants = (
        "  deterministic   envelope  ", "DETERMINISTIC ENVELOPE", "deterministic\n\tenvelope",
        "dEtErMiNiStIc   EnVeLoPe", "deterministic\r\nenvelope",
    )
    return variants[index % len(variants)]


def run_stress(profile: StressProfile) -> StressReport:
    """Run exactly N scenarios: one miss and N-1 normalized cache hits.

    The shock probe is accounted for separately so the N-count remains exact.
    M=2 and M=300 are intentionally separate profiles; no interpolation or
    claim that the two profiles have equal latency is made.
    """
    if profile.M < 1 or profile.scenarios != 1000 or profile.distinct_identities < 1:
        raise ValueError("stress profiles require M >= 1 and exactly 1000 scenarios")
    started = time.perf_counter()
    worker_calls = 0

    def worker(envelope: CanonicalEnvelope) -> Mapping[str, Any]:
        nonlocal worker_calls
        worker_calls += 1
        return {"answer": "deterministic envelope", "identity": envelope.identity}

    engine = DeterministicEnvelope()
    baseline_misses = normalized_hits = outputs = 0
    rejected = 0

    def validator(_payload: Any) -> bool:
        nonlocal rejected
        if rejected < profile.validation_retries:
            rejected += 1
            return False
        return True

    for index in range(profile.scenarios):
        decision = engine.execute(
            {
                "conflict_key": f"stress-baseline-{index % profile.distinct_identities}",
                "text": _equivalent_text(index),
            },
            worker,
            policy=TEXT_EQUIVALENCE_V1,
            validator=validator if index == 0 and profile.validation_retries else None,
            validation_retries=profile.validation_retries if index == 0 else 0,
            scenario_index=index,
        )
        if decision.status == "COMMITTED":
            baseline_misses += 1
            outputs += 1
        elif decision.status == "CACHE_HIT":
            normalized_hits += 1
            outputs += 1
        else:
            raise AssertionError(f"unexpected stress status: {decision.status}")

    stress_worker_calls = worker_calls
    engine.execute({"conflict_key": "shock-boundary", "value": "baseline"}, worker)
    shock = engine.execute(
        {"conflict_key": "shock-boundary", "value": "changed"}, worker,
        scenario_index=profile.M, shock_boundary=profile.M,
    )
    lock_hit = engine.execute(
        {"conflict_key": "shock-boundary", "value": "changed-again"}, worker,
        scenario_index=profile.M + 1, shock_boundary=profile.M,
    )
    if shock.status != "FAIL_SAFE_FALLBACK" or lock_hit.status != "FAIL_SAFE_FALLBACK":
        raise AssertionError("shock boundary did not remain fail-safe locked")
    return StressReport(
        profile.name, profile.M, profile.scenarios, baseline_misses, normalized_hits,
        rejected, outputs, stress_worker_calls, 1, 1, profile.M,
        (time.perf_counter() - started) * 1000,
    )


def run_stress_profiles() -> tuple[StressReport, StressReport]:
    return (
        run_stress(StressProfile("M=2", 2, distinct_identities=2)),
        run_stress(StressProfile("M=300", 300, validation_retries=299)),
    )
