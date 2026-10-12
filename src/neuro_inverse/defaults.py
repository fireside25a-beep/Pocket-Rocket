DEFAULT_EXPERTS = [
    {
        "expert_id": "code.review.v1",
        "description": "review debug secure deterministic code Python C C++ API tests invariants",
        "payload": "Inspect interfaces, invariants, error paths, resource limits, security, and tests. Preserve public behavior unless change is explicitly requested.",
        "compatibility": {"domains": ["code"], "task_kinds": ["review", "build"]},
    },
    {
        "expert_id": "data.transform.v1",
        "description": "CSV JSON schema parsing deterministic data transformation validation",
        "payload": "Define input/output schemas. Reject malformed records explicitly. Preserve ordering where specified and neutralize spreadsheet formulas when exporting CSV.",
        "compatibility": {"domains": ["data"], "task_kinds": ["build", "review"]},
    },
    {
        "expert_id": "reason.verify.v1",
        "description": "reasoning verification assumptions evidence uncertainty contradiction",
        "payload": "Separate evidence, inference, and uncertainty. Prefer external or machine-checkable verification over self-agreement. State unresolved limitations.",
    },
    {
        "expert_id": "system.performance.v1",
        "description": "GPU VRAM RAM SSD NVMe caching profiling latency throughput benchmark",
        "payload": "Measure before optimizing. Report cold and warm behavior, peak memory, I/O bytes, latency distribution, throughput, hardware, and exact commands.",
    },
    {
        "expert_id": "contract.safety.v1",
        "description": "contract permissions preconditions postconditions rollback safe execution",
        "payload": "Treat proposals as uncommitted until schemas, permissions, preconditions, postconditions, limits, and rollback behavior pass deterministic checks.",
    },
]

