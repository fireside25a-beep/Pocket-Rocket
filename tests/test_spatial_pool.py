import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from neuro_inverse.codes import simhash256
from neuro_inverse.router import HammingRouter
from neuro_inverse.spatial_pool import (
    GoldenHashIndex,
    GoldenHammingRouter,
    golden_bucket,
    splitmix64,
)
from neuro_inverse.store import ExpertStore


class _Compatible:
    def allows(self, domain, task_kind):
        return True


class SpatialPoolTests(unittest.TestCase):
    def test_splitmix_and_bucket_are_stable(self):
        self.assertEqual(0xE220A8397B1DCDAF, splitmix64(0))
        code = bytes(range(32))
        self.assertGreaterEqual(golden_bucket(code), 0)
        self.assertLess(golden_bucket(code), 512)
        self.assertEqual(golden_bucket(code), golden_bucket(code))

    def test_primary_hash_collision_requires_full_coordinate_match(self):
        by_bucket = {}
        pair = None
        for index in range(10000):
            code = hashlib.sha256(f"spatial-{index}".encode()).digest()
            bucket = golden_bucket(code)
            previous = by_bucket.setdefault(bucket, code)
            if previous != code:
                pair = previous, code
                break
        self.assertIsNotNone(pair)
        first, second = pair
        records = [
            SimpleNamespace(expert_id="first", code=first, compatibility=_Compatible()),
            SimpleNamespace(expert_id="second", code=second, compatibility=_Compatible()),
        ]
        index = GoldenHashIndex(records)
        self.assertEqual(("first",), tuple(item.expert_id for item in index.lookup_exact(first)))
        self.assertEqual(("second",), tuple(item.expert_id for item in index.lookup_exact(second)))

    def test_5000_indexed_routes_equal_linear_hamming_routes(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ExpertStore(Path(temp))
            store.initialize([
                {"expert_id": f"expert-{index:02d}", "description": f"domain task feature {index}", "payload": "x"}
                for index in range(24)
            ])
            linear = HammingRouter(store.records)
            indexed = GoldenHammingRouter(store.records)
            for index in range(5000):
                text = f"query {index % 97} feature {index * 17}"
                expected = [(route.expert.expert_id, route.distance) for route in linear.route(text, top_k=8)]
                actual = [(route.expert.expert_id, route.distance) for route in indexed.route(text, top_k=8)]
                self.assertEqual(expected, actual)
            self.assertEqual(
                [(route.expert.expert_id, route.distance) for route in linear.route("stable", top_k=8)],
                [(route.expert.expert_id, route.distance) for route in indexed.route("stable", top_k=8)],
            )

    def test_compatibility_filter_matches_linear_router(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ExpertStore(Path(temp))
            store.initialize([
                {"expert_id": "code", "description": "code", "payload": "x", "compatibility": {"domains": ["code"]}},
                {"expert_id": "data", "description": "data", "payload": "x", "compatibility": {"domains": ["data"]}},
            ])
            linear = HammingRouter(store.records).route("data", domain="code", top_k=2)
            indexed = GoldenHammingRouter(store.records).route("data", domain="code", top_k=2)
            self.assertEqual(
                [(item.expert.expert_id, item.distance) for item in linear],
                [(item.expert.expert_id, item.distance) for item in indexed],
            )


if __name__ == "__main__":
    unittest.main()
