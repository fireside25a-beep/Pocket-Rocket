from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .backends import GenerationBackend
from .spatial_pool import GoldenHammingRouter
from .store import ExpertStore

if TYPE_CHECKING:
    from .envelope import DeterministicEnvelope


@dataclass(frozen=True)
class StepTrace:
    step: int
    expert_ids: tuple[str, ...]
    distances: tuple[int, ...]
    candidate_sha256: str
    contract_ok: bool
    failures: tuple[str, ...]
    elapsed_ms: float


@dataclass(frozen=True)
class RunResult:
    output: str
    committed: bool
    steps: tuple[StepTrace, ...]


class RecursiveController:
    def __init__(self, store: ExpertStore, backend: GenerationBackend, trace_dir: Path) -> None:
        self.store = store
        self.backend = backend
        self.trace_dir = trace_dir

    def run(self, request: str, *, max_steps: int = 3, top_k: int = 3,
            max_new_tokens: int = 256, domain: str | None = None,
            task_kind: str | None = None) -> RunResult:
        if not 1 <= max_steps <= 16:
            raise ValueError("max_steps must be between 1 and 16")
        router = GoldenHammingRouter(self.store.records)
        previous = ""
        traces: list[StepTrace] = []
        output = ""
        committed = False
        for step in range(max_steps):
            started = time.perf_counter()
            route_text = request if not previous else f"{request}\nCurrent candidate:\n{previous}"
            routes = router.route(route_text, top_k=top_k, domain=domain, task_kind=task_kind)
            if not routes:
                raise RuntimeError("No compatible experts")
            payloads = [self.store.load_payload(route.expert) for route in routes]
            prompt = self._prompt(request, previous, payloads, step, max_steps)
            output = self.backend.generate(prompt, max_new_tokens=max_new_tokens)
            failures: list[str] = []
            for route in routes:
                ok, current = route.expert.contract.verify(output)
                if not ok:
                    failures.extend(f"{route.expert.expert_id}:{item}" for item in current)
            stable = bool(previous) and self._normalized(previous) == self._normalized(output)
            committed = not failures and (stable or step == max_steps - 1)
            traces.append(StepTrace(
                step=step,
                expert_ids=tuple(route.expert.expert_id for route in routes),
                distances=tuple(route.distance for route in routes),
                candidate_sha256=hashlib.sha256(output.encode("utf-8")).hexdigest(),
                contract_ok=not failures,
                failures=tuple(failures),
                elapsed_ms=(time.perf_counter() - started) * 1000,
            ))
            if committed:
                break
            previous = output
        result = RunResult(output=output, committed=committed, steps=tuple(traces))
        self._write_trace(request, result)
        return result

    def run_enveloped(
        self,
        request: str,
        *,
        envelope: "DeterministicEnvelope",
        max_steps: int = 3,
        top_k: int = 3,
        max_new_tokens: int = 256,
        domain: str | None = None,
        task_kind: str | None = None,
    ) -> RunResult:
        """Run through the deterministic envelope; generation remains a proposal.

        A cache hit rehydrates the previously committed result.  An
        uncommitted or fail-safe result is deliberately not exposed as a
        successful ``RunResult``.
        """
        from .envelope import CanonicalEnvelope

        request_payload = {
            "kind": "recursive-controller.run",
            "request": request,
            "max_steps": max_steps,
            "top_k": top_k,
            "max_new_tokens": max_new_tokens,
            "domain": domain,
            "task_kind": task_kind,
        }

        def propose(_envelope: CanonicalEnvelope) -> dict[str, Any]:
            result = self.run(
                request, max_steps=max_steps, top_k=top_k,
                max_new_tokens=max_new_tokens, domain=domain, task_kind=task_kind,
            )
            return {
                "output": result.output,
                "committed": result.committed,
                "steps": [asdict(step) for step in result.steps],
            }

        decision = envelope.execute(
            request_payload, propose,
            validator=lambda payload: isinstance(payload, dict) and bool(payload.get("committed")),
        )
        if decision.status not in {"COMMITTED", "CACHE_HIT"} or not isinstance(decision.payload, dict):
            return RunResult(output="", committed=False, steps=())
        steps = tuple(StepTrace(**item) for item in decision.payload.get("steps", ()))
        return RunResult(
            output=str(decision.payload.get("output", "")),
            committed=True,
            steps=steps,
        )

    @staticmethod
    def _normalized(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _prompt(request: str, previous: str, payloads: list[str], step: int, max_steps: int) -> str:
        guidance = "\n\n".join(f"CAPABILITY {i+1}:\n{p}" for i, p in enumerate(payloads))
        previous_block = previous or "No previous candidate. Produce the first candidate."
        return (
            "You are the proposal component inside a bounded, contract-checked recursive runtime.\n"
            "Follow the selected capability guidance. Do not claim that routing proves factual truth.\n\n"
            f"USER REQUEST:\n{request}\n\nSELECTED CAPABILITIES:\n{guidance}\n\n"
            f"PREVIOUS CANDIDATE:\n{previous_block}\n\n"
            f"REFINEMENT STEP: {step + 1}/{max_steps}\n"
            "Return only the improved answer. Preserve correct content and repair defects."
        )

    def _write_trace(self, request: str, result: RunResult) -> None:
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        run_id = hashlib.sha256((request + str(time.time_ns())).encode()).hexdigest()[:16]
        path = self.trace_dir / f"{run_id}.jsonl"
        header = {"type": "run", "request_sha256": hashlib.sha256(request.encode()).hexdigest(),
                  "backend": self.backend.name, "committed": result.committed}
        lines = [json.dumps(header, sort_keys=True)]
        lines.extend(json.dumps({"type": "step", **asdict(step)}, sort_keys=True) for step in result.steps)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
