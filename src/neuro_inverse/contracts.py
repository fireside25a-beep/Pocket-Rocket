from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Contract:
    input_kinds: tuple[str, ...] = ("text",)
    output_kind: str = "text"
    permissions: tuple[str, ...] = ()
    max_output_chars: int = 16000
    forbidden_fragments: tuple[str, ...] = ()
    required_fragments: tuple[str, ...] = ()

    def verify(self, output: str) -> tuple[bool, tuple[str, ...]]:
        failures: list[str] = []
        if not isinstance(output, str) or not output.strip():
            failures.append("output.empty")
        if len(output) > self.max_output_chars:
            failures.append("output.too_large")
        folded = output.casefold()
        for fragment in self.forbidden_fragments:
            if fragment.casefold() in folded:
                failures.append(f"output.forbidden:{fragment}")
        for fragment in self.required_fragments:
            if fragment.casefold() not in folded:
                failures.append(f"output.missing:{fragment}")
        return not failures, tuple(failures)


@dataclass(frozen=True)
class Compatibility:
    domains: tuple[str, ...] = field(default_factory=tuple)
    task_kinds: tuple[str, ...] = field(default_factory=tuple)

    def allows(self, domain: str | None, task_kind: str | None) -> bool:
        domain_ok = not self.domains or domain in self.domains
        task_ok = not self.task_kinds or task_kind in self.task_kinds
        return domain_ok and task_ok

