import json
import tempfile
import unittest
from pathlib import Path

from neuro_inverse.controller import RecursiveController
from neuro_inverse.envelope import (
    EXACT_BYTES_V1,
    TEXT_EQUIVALENCE_V1,
    CanonicalEnvelope,
    CommittedHistory,
    DeterministicCron,
    DeterministicEnvelope,
    EnvelopeCache,
    EphemeralWorkerPool,
    FailSafeLock,
    ScheduledJob,
    StressProfile,
    run_stress,
)
from neuro_inverse.store import ExpertStore


class EnvelopeTests(unittest.TestCase):
    def test_exact_identity_is_default_and_normalization_is_explicit(self):
        left = CanonicalEnvelope.create({"text": " Hello  world "})
        right = CanonicalEnvelope.create({"text": "hello world"})
        self.assertNotEqual(left.identity, right.identity)
        normalized_left = CanonicalEnvelope.create({"text": " Hello  world "}, policy=TEXT_EQUIVALENCE_V1)
        normalized_right = CanonicalEnvelope.create({"text": "hello world"}, policy=TEXT_EQUIVALENCE_V1)
        self.assertEqual(normalized_left.identity, normalized_right.identity)
        self.assertNotEqual(normalized_left.identity, left.identity)
        self.assertEqual(EXACT_BYTES_V1.name, "exact-v1")

    def test_cache_hit_conflict_and_immutable_persistent_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            cache_path = Path(temp) / "cache.jsonl"
            cache = EnvelopeCache(cache_path)
            engine = DeterministicEnvelope(cache=cache)
            worker_calls = []

            def worker(envelope):
                worker_calls.append(envelope.identity)
                return {"answer": envelope.payload["value"]}

            first = engine.execute({"conflict_key": "job", "value": "one"}, worker)
            self.assertEqual(first.status, "COMMITTED")
            equivalent = engine.execute({"conflict_key": "job", "value": "one"}, worker)
            self.assertEqual(equivalent.status, "CACHE_HIT")
            conflict = engine.execute({"conflict_key": "job", "value": "two"}, worker)
            self.assertEqual(conflict.status, "FAIL_SAFE_FALLBACK")
            restarted = DeterministicEnvelope(cache=EnvelopeCache(cache_path))
            locked = restarted.execute({"conflict_key": "job", "value": "three"}, worker)
            self.assertEqual(locked.status, "FAIL_SAFE_FALLBACK")
            self.assertEqual(len(worker_calls), 1)

    def test_disagreement_requires_explicit_judge(self):
        pool = EphemeralWorkerPool({
            "a": lambda _envelope: {"answer": "A"},
            "b": lambda _envelope: {"answer": "B"},
        })
        engine = DeterministicEnvelope()
        rejected = engine.execute({"job": "disagree"}, pool)
        self.assertEqual(rejected.status, "FAIL_SAFE_FALLBACK")
        judged = DeterministicEnvelope().execute(
            {"job": "disagree"}, pool,
            judge=lambda proposals: next(item for item in proposals if item.worker_id == "a"),
        )
        self.assertEqual(judged.status, "COMMITTED")

    def test_history_hash_excludes_wall_clock_but_chain_detects_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            first_path = Path(temp) / "first.jsonl"
            second_path = Path(temp) / "second.jsonl"
            first = CommittedHistory(first_path)
            second = CommittedHistory(second_path)
            first_record = first.append({"type": "commit", "value": "stable"})
            second_record = second.append({"type": "commit", "value": "stable"})
            self.assertEqual(first_record.record_hash, second_record.record_hash)
            self.assertEqual(len(first.verify()), 1)
            raw = json.loads(first_path.read_text(encoding="utf-8"))
            raw["event"]["value"] = "tampered"
            first_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                CommittedHistory(first_path)

    def test_cron_order_and_retry_budget(self):
        events = []
        attempts = {"a": 0}

        def a(attempt):
            events.append(("a", attempt))
            attempts["a"] += 1
            return attempt >= 1

        def b(attempt):
            events.append(("b", attempt))
            return True

        cron = DeterministicCron()
        cron.add(ScheduledJob("b", 0, b, priority=1))
        cron.add(ScheduledJob("a", 0, a, priority=0, retry_budget=1, retry_delay=1))
        result = cron.run_until(1)
        self.assertEqual([(item.job_id, item.attempt) for item in result], [("a", 0), ("b", 0), ("a", 1)])
        self.assertEqual(events, [("a", 0), ("b", 0), ("a", 1)])
        self.assertEqual(sum(not item.success for item in result), 1)

    def test_exact_stress_profiles_and_shock_boundary(self):
        profile_a = run_stress(StressProfile("A", 2, distinct_identities=2))
        profile_b = run_stress(StressProfile("B", 300, validation_retries=299))
        self.assertEqual((profile_a.scenario_count, profile_a.baseline_misses, profile_a.validation_retries, profile_a.outputs), (1000, 2, 0, 1000))
        self.assertEqual((profile_b.scenario_count, profile_b.baseline_misses, profile_b.validation_retries, profile_b.outputs), (1000, 1, 299, 1000))
        self.assertEqual((profile_a.shock_conflicts, profile_a.shock_lock_hits, profile_a.shock_boundary_index), (1, 1, 2))
        self.assertEqual((profile_b.shock_conflicts, profile_b.shock_lock_hits, profile_b.shock_boundary_index), (1, 1, 300))
        self.assertGreater(profile_a.elapsed_ms, 0.0)
        self.assertGreater(profile_b.elapsed_ms, 0.0)


class ControllerEnvelopeTests(unittest.TestCase):
    class Backend:
        name = "deterministic-test-backend"

        def __init__(self):
            self.calls = 0

        def generate(self, prompt: str, *, max_new_tokens: int) -> str:
            self.calls += 1
            return "committed answer"

    def test_recursive_controller_uses_committed_envelope_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = ExpertStore(root / "store")
            store.initialize([{"expert_id": "a", "description": "answer text", "payload": "answer guidance"}])
            backend = self.Backend()
            controller = RecursiveController(store, backend, root / "traces")
            engine = DeterministicEnvelope(history=CommittedHistory(root / "history.jsonl"))
            first = controller.run_enveloped("answer", envelope=engine, max_steps=1)
            second = controller.run_enveloped("answer", envelope=engine, max_steps=1)
            self.assertTrue(first.committed and second.committed)
            self.assertEqual(first.output, second.output)
            self.assertEqual(backend.calls, 1)


if __name__ == "__main__":
    unittest.main()
