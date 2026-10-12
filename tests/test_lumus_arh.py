import io
import json
import unittest
from wsgiref.util import setup_testing_defaults

from neuro_inverse.lumus_arh import (
    EphemeralHistoryStore,
    EphemeralWorkerRecord,
    LumusARHService,
    LumusARHWSGI,
)


class LumusARHTests(unittest.TestCase):
    def test_history_is_bounded_and_reset_is_complete(self):
        store = EphemeralHistoryStore(max_entries=2, max_bytes=4096)
        record = EphemeralWorkerRecord("full_pipeline", "a", ("a",), None)
        store.append("one", record)
        store.append("two", record)
        store.append("three", record)
        self.assertEqual([item.question for item in store.snapshot()], ["two", "three"])
        self.assertLessEqual(store.bytes_used, 4096)
        store.reset()
        self.assertEqual(store.snapshot(), ())
        self.assertEqual(store.bytes_used, 0)

    def test_disabled_and_error_force_full_pipeline_without_promotion(self):
        calls = []

        def worker(question, history):
            calls.append((question, history))
            return {
                "routing_recommendation": "cache_only",
                "draft_answer": "local draft",
                "ephemeral_context": ["temporary note"],
                "promotion_suggestion": "remember this",
                "disabled": True,
            }

        service = LumusARHService(worker=worker)
        status, response = service.ask({"question": "hello"})
        self.assertEqual(status, 200)
        self.assertEqual(response["routing_recommendation"], "full_pipeline")
        self.assertEqual(response["promotion_suggestion"], "remember this")
        self.assertEqual(len(service.history), 1)
        self.assertEqual(calls[0][1], ())
        # The suggestion remains an opaque ephemeral field; there is no
        # permanent-memory collection to mutate.
        self.assertFalse(hasattr(service, "permanent_memory"))

    def test_worker_failure_fails_closed_and_does_not_enter_history(self):
        def worker(_question, _history):
            raise RuntimeError("local transport unavailable")

        service = LumusARHService(worker=worker)
        status, response = service.ask({"question": "hello"})
        self.assertEqual(status, 503)
        self.assertEqual(response["status"], "FAIL_SAFE_FALLBACK")
        self.assertEqual(response["routing_recommendation"], "full_pipeline")
        self.assertEqual(len(service.history), 0)

    def test_reset_clears_cache_and_ephemeral_context(self):
        calls = []

        def worker(question, history):
            calls.append(history)
            return {"draft_answer": "answer", "routing_recommendation": "answer_directly"}

        service = LumusARHService(worker=worker)
        self.assertEqual(service.ask({"question": "hello"})[0], 200)
        self.assertEqual(len(service.history), 1)
        status, response = service.reset({})
        self.assertEqual((status, response), (200, {"status": "RESET", "history_size": 0}))
        self.assertEqual(len(service.history), 0)
        self.assertEqual(service.ask({"question": "hello"})[0], 200)
        self.assertEqual(calls[1], ())

    def test_wsgi_routes_have_canonical_json_and_loopback_surface(self):
        class Transport:
            name = "test-local"

            def generate(self, prompt, *, max_new_tokens):
                self.seen = (prompt, max_new_tokens)
                return "deterministic answer"

        app = LumusARHWSGI(LumusARHService(transport=Transport()))

        def request(path, payload, method="POST"):
            body = json.dumps(payload, ensure_ascii=False).encode()
            environ = {}
            setup_testing_defaults(environ)
            environ.update({"REQUEST_METHOD": method, "PATH_INFO": path,
                            "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)})
            result = {}
            chunks = app(environ, lambda status, headers: result.update(status=status, headers=headers))
            return result, b"".join(chunks)

        meta, body = request("/ask", {"question": "hi"})
        self.assertEqual(meta["status"], "200 OK")
        self.assertEqual(json.loads(body)["answer"], "deterministic answer")
        self.assertEqual(body, b"{" + b'"answer":"deterministic answer","draft_answer":"deterministic answer",'
                         b'"ephemeral_context":[],"history_size":1,"promotion_suggestion":null,'
                         b'"request_identity":"' + body.split(b'"request_identity":"', 1)[1].split(b'"', 1)[0] +
                         b'","routing_recommendation":"full_pipeline","status":"COMMITTED"}')
        meta, body = request("/not-found", {})
        self.assertEqual(meta["status"], "404 Not Found")
        self.assertEqual(json.loads(body)["status"], "ERROR")
        meta, body = request("/reset", {})
        self.assertEqual(meta["status"], "200 OK")
        self.assertEqual(json.loads(body), {"history_size": 0, "status": "RESET"})


if __name__ == "__main__":
    unittest.main()
