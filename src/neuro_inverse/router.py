from __future__ import annotations

from dataclasses import dataclass

from .codes import hamming256, simhash256
from .store import ExpertRecord


@dataclass(frozen=True)
class Route:
    expert: ExpertRecord
    distance: int


class HammingRouter:
    def __init__(self, records: tuple[ExpertRecord, ...]) -> None:
        self.records = records

    def route(self, text: str, *, top_k: int = 3, domain: str | None = None,
              task_kind: str | None = None) -> tuple[Route, ...]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        query = simhash256(text)
        candidates = (
            record for record in self.records
            if record.compatibility.allows(domain, task_kind)
        )
        ranked = sorted(
            (Route(record, hamming256(query, record.code)) for record in candidates),
            key=lambda route: (route.distance, route.expert.expert_id),
        )
        return tuple(ranked[:top_k])

