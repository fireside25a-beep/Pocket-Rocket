"""Canonical records describing a bounded execution topology.

The record is descriptive: the executor still enforces every budget independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Sequence


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    topology: str
    request_root: str
    evidence: tuple[str, ...]
    alternatives: tuple[str, ...]
    max_depth: int
    max_nodes: int
    max_model_calls: int

    def payload(self) -> dict[str, object]:
        return {
            "topology": self.topology,
            "request_root": self.request_root,
            "evidence": list(self.evidence),
            "alternatives": list(self.alternatives),
            "limits": {
                "max_depth": self.max_depth,
                "max_nodes": self.max_nodes,
                "max_model_calls": self.max_model_calls,
            },
        }

    @property
    def certificate(self) -> str:
        encoded = json.dumps(self.payload(), sort_keys=True, separators=(",", ":")).encode()
        return sha256(encoded).hexdigest()


def make_execution_plan(goal: str, *, max_depth: int, max_nodes: int,
                        max_model_calls: int, planned_depths: Sequence[int]) -> ExecutionPlan:
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("goal must be non-empty")
    topology = "local_only" if max_depth == 0 else "recursive_fabric"
    alternatives = ("single_model",) if topology == "recursive_fabric" else ("recursive_fabric",)
    evidence = (
        f"planned_levels={len(tuple(planned_depths))}",
        f"max_depth={max_depth}",
        f"max_nodes={max_nodes}",
        f"max_model_calls={max_model_calls}",
    )
    return ExecutionPlan(
        topology=topology,
        request_root=sha256(goal.encode("utf-8")).hexdigest(),
        evidence=evidence,
        alternatives=alternatives,
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_model_calls=max_model_calls,
    )
