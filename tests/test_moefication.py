import unittest

import numpy as np

from neuro_inverse.binary_router import BinaryExpertRouter
from neuro_inverse.moefication import (
    contribution_bound_coefficient, dense_swiglu, equal_expert_slices, expert_key, expert_swiglu,
    precision_delta_bound_coefficient, silu, sparse_swiglu,
)


class MoEficationTests(unittest.TestCase):
    def test_silu_is_finite_for_large_negative_values(self):
        values = silu(np.array([-1000.0, 1000.0], dtype=np.float32))
        self.assertTrue(np.isfinite(values).all())
        self.assertLessEqual(values[0], 0.0)
        self.assertGreater(values[1], 0.0)

    def test_all_experts_exactly_reconstruct_dense(self):
        rng = np.random.default_rng(11)
        x = rng.normal(size=(5, 16)).astype(np.float32)
        gate = rng.normal(size=(48, 16)).astype(np.float32)
        up = rng.normal(size=(48, 16)).astype(np.float32)
        down = rng.normal(size=(16, 48)).astype(np.float32)
        experts = equal_expert_slices(48, 8)
        dense = dense_swiglu(x, gate, up, down)
        rebuilt = sparse_swiglu(x, gate, up, down, experts, tuple(range(8)))
        self.assertTrue(np.allclose(dense, rebuilt, rtol=2e-5, atol=2e-5))

    def test_256_bit_route_is_repeatable(self):
        rng = np.random.default_rng(13)
        gate = rng.normal(size=(32, 12)).astype(np.float32)
        up = rng.normal(size=(32, 12)).astype(np.float32)
        down = rng.normal(size=(12, 32)).astype(np.float32)
        experts = equal_expert_slices(32, 4)
        keys = np.stack([expert_key(gate, up, down, expert) for expert in experts])
        router = BinaryExpertRouter.from_keys(keys)
        hidden = rng.normal(size=12).astype(np.float32)
        expected = router.rank(hidden)
        self.assertEqual(256, len(router.centroids[0]) * 8)
        for _ in range(100):
            self.assertEqual(expected, router.rank(hidden))

    def test_contribution_bound_is_a_real_certificate(self):
        rng = np.random.default_rng(17)
        gate = rng.normal(size=(24, 10)).astype(np.float32)
        up = rng.normal(size=(24, 10)).astype(np.float32)
        down = rng.normal(size=(10, 24)).astype(np.float32)
        expert = equal_expert_slices(24, 1)[0]
        coefficient = contribution_bound_coefficient(gate, up, down)
        for _ in range(100):
            x = rng.normal(size=(1, 10)).astype(np.float32)
            actual = np.linalg.norm(expert_swiglu(x, gate, up, down, expert))
            self.assertLessEqual(actual, coefficient * np.linalg.norm(x) ** 2 * (1 + 1e-12))

    def test_precision_delta_bound_is_a_real_certificate(self):
        rng = np.random.default_rng(19)
        low = [rng.normal(size=shape).astype(np.float32) for shape in ((20, 9), (20, 9), (9, 20))]
        high = [item + rng.normal(scale=0.05, size=item.shape).astype(np.float32) for item in low]
        coefficient = precision_delta_bound_coefficient(*low, *high)
        expert = equal_expert_slices(20, 1)[0]
        for _ in range(100):
            x = rng.normal(size=(1, 9)).astype(np.float32)
            actual = np.linalg.norm(
                expert_swiglu(x, *high, expert) - expert_swiglu(x, *low, expert)
            )
            self.assertLessEqual(actual, coefficient * np.linalg.norm(x) ** 2 * (1 + 1e-12))


if __name__ == "__main__":
    unittest.main()
