# Pocket Rocket 0.3 implementation ledger

| Surface | Production consumer | Direct verification |
| --- | --- | --- |
| `hypervector1024`, `hamming1024` | cell construction, routing, response consensus | width, canonicalization, locality, malformed input |
| `fabric_cells` | `route_cells` | all 1,024 IDs present, unique codes, committed root |
| `route_cells` | planner and recursive runtime | deterministic order, role scope, exclusion |
| `FabricLimits` | CLI planner and executor | depth/node/quorum/token bounds, combined prompt budget |
| `classify_consensus` | recursive runtime | reject, abstain, accept, exact threshold validation |
| `plan_recursive`, `plan_as_dict` | `agent-plan`, `agent-run` | total-node budget, deterministic certificate, CLI JSON |
| `RecursiveFabricRuntime` | `agent-run` | DS4-only type lock; full inference pending real model |
| `verify_run_certificate` | package API | valid commitment, answer tamper, unserializable transcript |
| `runtime_surface_audit.py` | `make test`, `make surface-audit` | rejects simulated/incomplete/orphaned 0.3 production paths |

No model double, canned responder, disconnected demo endpoint, placeholder, or
alternate hosted inference path was added. Planning is a real deterministic
production operation; model-backed execution deliberately refuses to run until
the pinned DS4 binary and exact model are present.
