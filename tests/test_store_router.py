import tempfile
import unittest
from pathlib import Path

from neuro_inverse.router import HammingRouter
from neuro_inverse.store import ExpertStore


DEFS = [
    {"expert_id": "b", "description": "python code review", "payload": "review code"},
    {"expert_id": "a", "description": "python code review", "payload": "review code safely"},
    {"expert_id": "data", "description": "CSV data parsing", "payload": "parse data",
     "compatibility": {"domains": ["data"]}},
]


class StoreRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ExpertStore(Path(self.temp.name), cache_bytes=64)
        self.store.initialize(DEFS)

    def tearDown(self):
        self.temp.cleanup()

    def test_tie_break_is_id(self):
        routes = HammingRouter(self.store.records).route("python code review", top_k=2)
        self.assertEqual([r.expert.expert_id for r in routes], ["a", "b"])

    def test_repeatable(self):
        router = HammingRouter(self.store.records)
        expected = [(r.expert.expert_id, r.distance) for r in router.route("CSV parser")]
        for _ in range(100):
            self.assertEqual(expected, [(r.expert.expert_id, r.distance) for r in router.route("CSV parser")])

    def test_compatibility_filter(self):
        routes = HammingRouter(self.store.records).route("CSV", domain="code")
        self.assertNotIn("data", [r.expert.expert_id for r in routes])

    def test_payload_corruption_rejected(self):
        record = next(r for r in self.store.records if r.expert_id == "a")
        (self.store.root / record.payload_path).write_text("corrupt", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.load_payload(record)


if __name__ == "__main__":
    unittest.main()

