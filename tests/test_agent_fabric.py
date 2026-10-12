from __future__ import annotations

import contextlib
import hashlib
import io
import json
import unittest

from neuro_inverse.agent_fabric import (
    CELL_COUNT, CODE_BYTES, FABRIC_ROOT, FabricLimits,
    RecursiveFabricRuntime, classify_consensus, hamming1024, hypervector1024,
    fabric_cells, plan_as_dict, plan_recursive, route_cells,
    verify_run_certificate, _build_fabric, _fabric_root,
)
from neuro_inverse.cli import main
from neuro_inverse.ternary_exact import ExactRational, Trit


class AgentFabricTests(unittest.TestCase):
    def test_fabric_is_total_unique_and_reproducible(self) -> None:
        fabric = fabric_cells()
        self.assertEqual(1024, CELL_COUNT)
        self.assertEqual(CELL_COUNT, len(fabric))
        self.assertEqual(list(range(CELL_COUNT)), [cell.cell_id for cell in fabric])
        self.assertEqual(CELL_COUNT, len({cell.code for cell in fabric}))
        self.assertEqual(64, len(FABRIC_ROOT))
        self.assertEqual(FABRIC_ROOT, _fabric_root(_build_fabric()))
        self.assertTrue(all(len(cell.code) == CODE_BYTES for cell in fabric))

    def test_hypervector_has_exact_width_similarity_and_validation(self) -> None:
        first = hypervector1024("verify parser bounds and parser invariants")
        second = hypervector1024("verify parser bounds and parser safety invariants")
        unrelated = hypervector1024("compose a sonata for brass instruments")
        self.assertEqual(first, hypervector1024("VERIFY parser bounds and parser invariants!"))
        self.assertLess(hamming1024(first, second), hamming1024(first, unrelated))
        with self.assertRaises(ValueError):
            hypervector1024("!!!")
        with self.assertRaises(ValueError):
            hamming1024(b"short", first)

    def test_routing_is_stable_bounded_and_role_scoped(self) -> None:
        routes = route_cells("audit memory bounds", role="critic", count=5)
        self.assertEqual(routes, route_cells("audit memory bounds", role="critic", count=5))
        self.assertEqual(5, len(routes))
        self.assertTrue(all(route.cell.role == "critic" for route in routes))
        self.assertEqual(sorted((route.distance, route.cell.cell_id) for route in routes),
                         [(route.distance, route.cell.cell_id) for route in routes])
        excluded = {routes[0].cell.cell_id}
        self.assertNotIn(routes[0].cell.cell_id,
                         {item.cell.cell_id for item in route_cells(
                             "audit memory bounds", role="critic", count=5, excluded=excluded
                         )})

    def test_consensus_exercises_all_three_real_states(self) -> None:
        accepted = classify_consensus(["same evidence", "same evidence", "same evidence"])
        self.assertIs(accepted.status, Trit.POSITIVE)
        abstained = classify_consensus(
            ["alpha red proof", "beta blue proof", "gamma green proof"],
            reject_below=ExactRational(0), accept_at=ExactRational(1),
        )
        self.assertIs(abstained.status, Trit.UNKNOWN)
        rejected = classify_consensus(
            ["alpha red proof", "beta blue proof", "gamma green proof"],
            reject_below=ExactRational(3, 4), accept_at=ExactRational(4, 5),
        )
        self.assertIs(rejected.status, Trit.NEGATIVE)
        self.assertEqual(3, len(rejected.distances))
        with self.assertRaises(ValueError):
            classify_consensus(["one response"])
        with self.assertRaises(ValueError):
            classify_consensus(["one", "two"], accept_at=ExactRational(2))

    def test_plan_is_budgeted_recursive_and_certified(self) -> None:
        limits = FabricLimits(max_depth=3, max_nodes=8, quorum=3, max_new_tokens=64)
        rounds = plan_recursive("design a secure page cache", limits)
        self.assertEqual([0, 1, 2], [item.depth for item in rounds])
        self.assertLessEqual(sum(len(item.cells) for item in rounds), limits.max_nodes)
        self.assertEqual(len({cell.cell.cell_id for item in rounds for cell in item.cells}),
                         sum(len(item.cells) for item in rounds))
        payload = plan_as_dict("design a secure page cache", limits)
        self.assertEqual(64, len(payload["plan_certificate"]))
        self.assertEqual(CELL_COUNT, payload["fabric_cells"])
        with self.assertRaises(ValueError):
            FabricLimits(max_depth=1, max_nodes=6, quorum=5, max_new_tokens=1024)

    def test_every_limit_boundary_fails_closed(self) -> None:
        invalid = (
            {"max_depth": -1}, {"max_depth": 7},
            {"max_nodes": 1}, {"max_nodes": 65},
            {"quorum": 1}, {"quorum": 6},
            {"max_new_tokens": 0}, {"max_new_tokens": 2049},
            {"max_model_calls": 1}, {"max_model_calls": 129},
        )
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                FabricLimits(**fields)

    def test_cli_plan_is_connected_without_a_model_or_test_double(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, main([
                "agent-plan", "audit signed bounds", "--max-depth", "1",
                "--max-nodes", "6", "--quorum", "3", "--max-new-tokens", "32",
            ]))
        payload = json.loads(output.getvalue())
        self.assertEqual(1024, payload["fabric_cells"])
        self.assertEqual(2, len(payload["rounds"]))

    def test_executor_rejects_alternate_or_simulated_transports(self) -> None:
        with self.assertRaises(TypeError):
            RecursiveFabricRuntime(object())  # type: ignore[arg-type]

    def test_run_certificate_verifier_rejects_tampering(self) -> None:
        answer = "bounded evidence"
        transcript = {
            "domain": "pocket-recursive-proof-fabric-v1",
            "fabric_root": FABRIC_ROOT,
            "answer_root": hashlib.sha256(answer.encode()).hexdigest(),
        }
        canonical = json.dumps(transcript, sort_keys=True, separators=(",", ":")).encode()
        certificate = hashlib.sha256(canonical).hexdigest()
        self.assertTrue(verify_run_certificate(transcript, answer, certificate))
        self.assertFalse(verify_run_certificate(transcript, answer + "!", certificate))
        malformed = dict(transcript)
        malformed["unserializable"] = object()
        self.assertFalse(verify_run_certificate(malformed, answer, certificate))


if __name__ == "__main__":
    unittest.main()
