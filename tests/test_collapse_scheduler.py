import unittest
from fractions import Fraction

from neuro_inverse.collapse_scheduler import (
    CollapseExpert,
    CouplingEdge,
    OmissionCertificate,
    commitment_oracle,
    plan_collapse,
)


class CollapseSchedulerTests(unittest.TestCase):
    def test_repeatable_exact_fraction_weights_and_threshold(self):
        experts = (
            CollapseExpert("near", 0),
            CollapseExpert("far", 1),
        )
        certificate = OmissionCertificate({"far": 0}, Fraction(0))
        first = plan_collapse(
            experts, tail_mass_threshold=Fraction(1, 3), certificate=certificate
        )
        second = plan_collapse(
            experts, tail_mass_threshold=Fraction(1, 3), certificate=certificate
        )
        self.assertEqual(first, second)
        self.assertEqual(Fraction(1), first.weights["near"])
        self.assertEqual(Fraction(1, 2), first.weights["far"])
        self.assertEqual(Fraction(1, 3), first.tail_mass)
        self.assertTrue(first.stopped_by_certificate)
        self.assertFalse(first.used_all_expert_fallback)

        below = plan_collapse(
            experts, tail_mass_threshold=Fraction(332, 1000), certificate=certificate
        )
        self.assertEqual(("near", "far"), below.active_ids)
        self.assertTrue(below.used_all_expert_fallback)

    def test_active_set_growth_is_monotonic(self):
        experts = tuple(CollapseExpert(f"e{index}", index) for index in range(4))
        plan = plan_collapse(
            experts, tail_mass_threshold=Fraction(0),
            certificate=OmissionCertificate({f"e{index}": 1 for index in range(4)}, 0),
        )
        previous = set()
        for step in plan.steps:
            current = set(step.active_ids)
            self.assertTrue(previous <= current)
            previous = current
        self.assertEqual(set(item.stable_id for item in experts), set(plan.active_ids))

    def test_coupling_group_closes_exactly(self):
        experts = (
            CollapseExpert("a", 0, "entangled-page"),
            CollapseExpert("b", 10, "entangled-page"),
            CollapseExpert("c", 20),
        )
        plan = plan_collapse(
            experts, tail_mass_threshold=Fraction(1), initial_active=1,
            certificate=OmissionCertificate({"c": 0}, 0),
        )
        self.assertEqual(("a", "b"), plan.active_ids)
        self.assertEqual(("a", "b"), plan.steps[0].active_ids)

    def test_committed_coupling_edge_closes_transitively(self):
        experts = (
            CollapseExpert("a", 0),
            CollapseExpert("b", 10),
            CollapseExpert("c", 20),
        )
        edge_ab = CouplingEdge.commit("a", "b")
        edge_bc = CouplingEdge.commit("b", "c")
        self.assertEqual(commitment_oracle(b"x"), commitment_oracle(b"x"))
        with self.assertRaises(ValueError):
            CouplingEdge("a", "b", "0" * 64)
        plan = plan_collapse(
            experts, tail_mass_threshold=Fraction(1),
            certificate=OmissionCertificate({}, 0),
            coupling_edges=(edge_ab, edge_bc),
        )
        self.assertEqual(("a", "b", "c"), plan.active_ids)
        self.assertTrue(plan.used_all_expert_fallback)

    def test_missing_or_invalid_certificate_falls_back_to_all_experts(self):
        experts = tuple(CollapseExpert(f"e{index}", index) for index in range(3))
        without = plan_collapse(experts, tail_mass_threshold=Fraction(1))
        self.assertEqual(tuple(item.stable_id for item in experts), without.active_ids)
        self.assertTrue(without.used_all_expert_fallback)
        invalid = plan_collapse(
            experts, tail_mass_threshold=Fraction(1),
            certificate=OmissionCertificate({item.stable_id: 0 for item in experts}, 0, valid=False),
        )
        self.assertEqual(without.active_ids, invalid.active_ids)
        self.assertTrue(invalid.used_all_expert_fallback)

    def test_validation_rejects_non_256_bit_distance_or_inexact_threshold(self):
        with self.assertRaises(ValueError):
            CollapseExpert("bad", 257)
        with self.assertRaises(TypeError):
            plan_collapse((CollapseExpert("ok", 0),), tail_mass_threshold=0.5)


if __name__ == "__main__":
    unittest.main()
