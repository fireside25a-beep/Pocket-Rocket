"""Loopback-compatible Lumus ARH architecture boundary.

Lumus ARH exposes two small lifecycle routes, ``POST /ask``
and ``POST /reset``.  This module keeps those routes independent of a UI and
keeps the worker history explicitly ephemeral.  A worker may propose a draft
and a routing recommendation, but it cannot write the permanent cache,
committed history, or any other process state.

The only model integration point is :class:`LocalModelTransport`.  The API
does not contain hosted-provider adapters and does not make network calls.
The WSGI app is suitable for a local development server and binds to loopback
by default when started with :func:`serve_loopback`.
"""
from __future__ import annotations

import copy
import json
import threading
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Literal, Protocol
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from .envelope import DeterministicEnvelope, EnvelopeCache


RoutingRecommendation = Literal["answer_directly", "full_pipeline", "cache_only"]
_ROUTING_VALUES = frozenset(("answer_directly", "full_pipeline", "cache_only"))


class LocalModelTransport(Protocol):
    """Minimal local-only generation contract.

    The production implementation wraps the pinned local ds4 runtime and must
    not perform hosted API calls. Returning a mapping is supported for
    local runtimes that already emit the Lumus worker schema; returning text is
    the ordinary path.
    """

    name: str

    def generate(self, prompt: str, *, max_new_tokens: int) -> str | Mapping[str, Any]: ...


@dataclass(frozen=True)
class EphemeralWorkerRecord:
    """The bounded worker/history schema defined for Lumus ARH."""

    routing_recommendation: RoutingRecommendation
    draft_answer: str
    ephemeral_context: tuple[str, ...]
    promotion_suggestion: str | None
    disabled: bool = False
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        # Keep this shape stable: it is both the worker contract and the
        # bounded history record.  No permanent-memory action is represented.
        return {
            "routing_recommendation": self.routing_recommendation,
            "draft_answer": self.draft_answer,
            "ephemeral_context": list(self.ephemeral_context),
            "promotion_suggestion": self.promotion_suggestion,
        }


@dataclass(frozen=True)
class EphemeralHistoryEntry:
    sequence: int
    question: str
    worker: EphemeralWorkerRecord

    def as_dict(self) -> dict[str, Any]:
        return {"sequence": self.sequence, "question": self.question, **self.worker.as_dict()}


class EphemeralHistoryStore:
    """Thread-safe FIFO history with hard record and byte limits.

    This store intentionally has no path, serialization, or promotion method.
    ``reset`` drops all entries and starts the logical sequence at zero.  The
    byte accounting uses the same canonical JSON representation as the
    deterministic envelope, so eviction decisions do not depend on hash-map
    ordering or wall-clock time.
    """

    def __init__(self, *, max_entries: int = 32, max_bytes: int = 256 * 1024) -> None:
        if max_entries < 1 or max_bytes < 256:
            raise ValueError("history limits must be positive")
        self.max_entries = int(max_entries)
        self.max_bytes = int(max_bytes)
        self._entries: deque[EphemeralHistoryEntry] = deque()
        self._bytes = 0
        self._next_sequence = 0
        self._lock = threading.RLock()

    @staticmethod
    def _encoded(entry: EphemeralHistoryEntry) -> bytes:
        return json.dumps(entry.as_dict(), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")

    def append(self, question: str, worker: EphemeralWorkerRecord) -> EphemeralHistoryEntry:
        if not isinstance(question, str) or not question:
            raise ValueError("question must be a non-empty string")
        if not isinstance(worker, EphemeralWorkerRecord):
            raise TypeError("worker must be an EphemeralWorkerRecord")
        with self._lock:
            entry = EphemeralHistoryEntry(self._next_sequence, question, copy.deepcopy(worker))
            encoded_size = len(self._encoded(entry))
            self._next_sequence += 1
            # An entry larger than the complete budget cannot be retained.  It
            # is still a valid response, but does not silently exceed a bound.
            if encoded_size > self.max_bytes:
                return entry
            while self._entries and (len(self._entries) >= self.max_entries or
                                     self._bytes + encoded_size > self.max_bytes):
                old = self._entries.popleft()
                self._bytes -= len(self._encoded(old))
            self._entries.append(entry)
            self._bytes += encoded_size
            return entry

    def snapshot(self) -> tuple[EphemeralHistoryEntry, ...]:
        with self._lock:
            return tuple(copy.deepcopy(tuple(self._entries)))

    def context(self) -> tuple[str, ...]:
        """Return only bounded draft context, oldest to newest."""
        with self._lock:
            return tuple(item.worker.draft_answer for item in self._entries if item.worker.draft_answer)

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()
            self._bytes = 0
            self._next_sequence = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def bytes_used(self) -> int:
        with self._lock:
            return self._bytes


def _string(value: Any, *, field: str, max_chars: int, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{field} must not be empty")
    if len(value) > max_chars:
        raise ValueError(f"{field} is too large")
    return value


def _worker_record(raw: Any, *, fallback_context: tuple[str, ...]) -> EphemeralWorkerRecord:
    """Validate/normalize the worker result and force unsafe routes closed."""
    if isinstance(raw, str):
        raw = {"draft_answer": raw}
    if not isinstance(raw, Mapping):
        raise ValueError("local worker must return text or a JSON object")
    recommendation = raw.get("routing_recommendation", "full_pipeline")
    if recommendation not in _ROUTING_VALUES:
        recommendation = "full_pipeline"
    disabled = bool(raw.get("disabled", False))
    error_value = raw.get("error")
    error = None if error_value in (None, "") else _string(error_value, field="error", max_chars=1024)
    if disabled or error is not None:
        recommendation = "full_pipeline"
    draft = _string(raw.get("draft_answer", ""), field="draft_answer", max_chars=32_000)
    context_value = raw.get("ephemeral_context", fallback_context)
    if isinstance(context_value, str):
        context_value = (context_value,)
    if not isinstance(context_value, (list, tuple)):
        raise ValueError("ephemeral_context must be a string sequence")
    context: list[str] = []
    for item in context_value:
        context.append(_string(item, field="ephemeral_context item", max_chars=8_192))
    if len(context) > 64:
        raise ValueError("ephemeral_context has too many entries")
    suggestion = raw.get("promotion_suggestion")
    if suggestion is not None:
        suggestion = _string(suggestion, field="promotion_suggestion", max_chars=2_048)
    return EphemeralWorkerRecord(recommendation, draft, tuple(context), suggestion, disabled, error)


class LumusARHService:
    """Stateful local service behind the two pre-React routes."""

    def __init__(
        self,
        *,
        transport: LocalModelTransport | None = None,
        worker: Callable[[str, tuple[EphemeralHistoryEntry, ...]], Any] | None = None,
        max_history_entries: int = 32,
        max_history_bytes: int = 256 * 1024,
        max_question_chars: int = 16_000,
        max_new_tokens: int = 2_048,
    ) -> None:
        if (transport is None) == (worker is None):
            raise ValueError("provide exactly one local transport or worker")
        if max_question_chars < 1 or not 1 <= max_new_tokens <= 32_768:
            raise ValueError("invalid request limits")
        self.transport = transport
        self.worker = worker
        self.max_question_chars = max_question_chars
        self.max_new_tokens = max_new_tokens
        self.history = EphemeralHistoryStore(max_entries=max_history_entries, max_bytes=max_history_bytes)
        self._envelope = DeterministicEnvelope(cache=EnvelopeCache())
        self._lock = threading.RLock()

    def _prompt(self, question: str, history: tuple[EphemeralHistoryEntry, ...]) -> str:
        context = [item.as_dict() for item in history]
        encoded = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return (
            "You are a local proposal worker inside the Lumus ARH deterministic envelope.\n"
            "Use the bounded ephemeral context as context only. Never promote memory.\n"
            "Return the answer to the user.\n\n"
            f"EPHEMERAL_CONTEXT_JSON:\n{encoded}\n\nUSER_REQUEST:\n{question}"
        )

    def _propose(self, question: str, history: tuple[EphemeralHistoryEntry, ...]) -> dict[str, Any]:
        if self.worker is not None:
            return self.worker(question, history)
        assert self.transport is not None
        return self.transport.generate(self._prompt(question, history), max_new_tokens=self.max_new_tokens)

    def ask(self, payload: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        if not isinstance(payload, Mapping):
            return self._error(HTTPStatus.BAD_REQUEST, "request must be a JSON object")
        raw_question = payload.get("question", payload.get("text"))
        try:
            question = _string(raw_question, field="question", max_chars=self.max_question_chars, allow_empty=False)
        except ValueError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        with self._lock:
            history = self.history.snapshot()
            envelope_payload = {
                "kind": "lumus.ask.v1", "question": question,
                "history": [item.as_dict() for item in history],
                "max_new_tokens": self.max_new_tokens,
            }
            def valid_proposal(value: Any) -> bool:
                try:
                    _worker_record(value, fallback_context=tuple(item.worker.draft_answer for item in history))
                except (TypeError, ValueError):
                    return False
                return True

            decision = self._envelope.execute(
                envelope_payload,
                lambda _envelope: self._propose(question, history),
                validator=valid_proposal,
            )
            if decision.status in ("COMMITTED", "CACHE_HIT"):
                try:
                    record = _worker_record(decision.payload, fallback_context=tuple(item.worker.draft_answer for item in history))
                except (TypeError, ValueError) as exc:
                    # A malformed local proposal is never exposed as a success.
                    return self._error(HTTPStatus.SERVICE_UNAVAILABLE, f"worker contract failure: {exc}")
                if decision.status == "COMMITTED":
                    self.history.append(question, record)
                response = {
                    "answer": record.draft_answer,
                    "status": decision.status,
                    "request_identity": decision.envelope_identity,
                    **record.as_dict(),
                    "history_size": len(self.history),
                }
                return HTTPStatus.OK, response
            response = {
                "answer": "",
                "status": "FAIL_SAFE_FALLBACK",
                "request_identity": decision.envelope_identity,
                "routing_recommendation": "full_pipeline",
                "draft_answer": "",
                "ephemeral_context": [],
                "promotion_suggestion": None,
                "history_size": len(self.history),
            }
            return HTTPStatus.SERVICE_UNAVAILABLE, response

    def reset(self, payload: Mapping[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        if payload not in (None, {}):
            return self._error(HTTPStatus.BAD_REQUEST, "reset accepts an empty JSON object")
        with self._lock:
            self.history.reset()
            self._envelope = DeterministicEnvelope(cache=EnvelopeCache())
        return HTTPStatus.OK, {"status": "RESET", "history_size": 0}

    @staticmethod
    def _error(status: int | HTTPStatus, message: str) -> tuple[int, dict[str, Any]]:
        return int(status), {"status": "ERROR", "error": message}


class LumusARHWSGI:
    """Minimal WSGI app implementing only the local lifecycle routes."""

    def __init__(self, service: LumusARHService, *, max_body_bytes: int = 1 << 20) -> None:
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self.service = service
        self.max_body_bytes = max_body_bytes

    @staticmethod
    def _json_bytes(payload: Mapping[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

    def _response(self, start_response: Callable[..., Any], status: int, payload: Mapping[str, Any]) -> list[bytes]:
        body = self._json_bytes(payload)
        phrase = HTTPStatus(status).phrase if status in HTTPStatus._value2member_map_ else "Response"
        start_response(f"{status} {phrase}", [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body))), ("Cache-Control", "no-store")])
        return [body]

    def __call__(self, environ: Mapping[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "")
        path = environ.get("PATH_INFO", "")
        if method != "POST" or path not in ("/ask", "/reset"):
            return self._response(start_response, HTTPStatus.NOT_FOUND, {"status": "ERROR", "error": "route not found"})
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            length = -1
        if length < 0 or length > self.max_body_bytes:
            return self._response(start_response, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"status": "ERROR", "error": "request body too large"})
        stream = environ.get("wsgi.input")
        raw = stream.read(length) if stream is not None else b""
        try:
            value = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._response(start_response, HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "invalid JSON"})
        if path == "/ask":
            status, response = self.service.ask(value)
        else:
            status, response = self.service.reset(value)
        return self._response(start_response, status, response)


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, *_args: Any) -> None:
        return


def serve_loopback(service: LumusARHService, *, host: str = "127.0.0.1", port: int = 8000) -> WSGIServer:
    """Create (but do not start) a loopback-only server for ``/ask``/``/reset``."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Lumus ARH is loopback-only")
    return make_server(host, port, LumusARHWSGI(service), handler_class=_QuietHandler)


__all__ = [
    "EphemeralHistoryEntry", "EphemeralHistoryStore", "EphemeralWorkerRecord",
    "LocalModelTransport", "LumusARHService", "LumusARHWSGI", "RoutingRecommendation",
    "serve_loopback",
]
