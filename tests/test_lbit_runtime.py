import unittest
from fractions import Fraction

from neuro_inverse.collapse_scheduler import CouplingEdge, OmissionCertificate
from neuro_inverse.lbit_runtime import LbitMoEControlPlane, LbitPage


def make_pages(size=256, payload_size=1024):
    pages = tuple(
        LbitPage.commit(
            f"e{index:03d}",
            index.to_bytes(32, "big"),
            bytes([index & 255]) * payload_size,
            Fraction(0),
        )
        for index in range(size)
    )
    return pages


class LbitRuntimeTests(unittest.TestCase):
    def test_256_expert_top6_recursive_plan_and_cache_are_repeatable(self):
        pages = make_pages()
        certificate = OmissionCertificate({page.stable_id: 0 for page in pages}, 1)
        control = LbitMoEControlPlane(
            pages,
            certificate=certificate,
            top_k=6,
            tail_mass_threshold=Fraction(1),
            cache_entries=2,
        )
        query = (0).to_bytes(32, "big")
        first = control.select(query, history=b"tick-7")
        second = control.select(query, history=b"tick-7")
        self.assertEqual(256, control.expert_count)
        self.assertEqual(6, len(first.active_ids))
        self.assertEqual(first.active_ids, second.active_ids)
        self.assertEqual(first.cache_key, second.cache_key)
        self.assertEqual(first.history_key, second.history_key)
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertTrue(first.resident_admitted)
        self.assertLessEqual(first.resident_bytes, 1 << 30)
        self.assertLessEqual(control.cache_size, control.cache_capacity)

    def test_committed_coupling_closure_can_expand_beyond_top6(self):
        pages = make_pages()
        certificate = OmissionCertificate({page.stable_id: 0 for page in pages}, 1)
        edges = tuple(CouplingEdge.commit("e000", f"e{index:03d}") for index in range(1, 8))
        control = LbitMoEControlPlane(
            pages,
            coupling_edges=edges,
            certificate=certificate,
            top_k=6,
            tail_mass_threshold=Fraction(1),
        )
        selected = control.select(bytes(32))
        self.assertEqual(8, len(selected.active_ids))
        self.assertEqual(8, len(selected.active_ids))
        self.assertEqual({f"e{index:03d}" for index in range(8)}, set(selected.active_ids))

    def test_tamper_fails_closed_to_all_256(self):
        pages = make_pages()
        certificate = OmissionCertificate({page.stable_id: 0 for page in pages}, 1)
        control = LbitMoEControlPlane(pages, certificate=certificate, tail_mass_threshold=1)
        # Internal mutation models a registry/storage change after startup.
        control._pages["e000"] = LbitPage.commit("e000", bytes([255]) * 32, b"tampered", 0)
        result = control.select(bytes(32))
        self.assertTrue(result.used_all_expert_fallback)
        self.assertEqual("registry_integrity", result.fail_closed_reason)
        self.assertEqual(256, len(result.active_ids))

    def test_certificate_missing_falls_back_and_budget_rejects_overcommit(self):
        pages = make_pages(payload_size=2 * 1024 * 1024)
        no_certificate = LbitMoEControlPlane(pages, tail_mass_threshold=1)
        result = no_certificate.select(bytes(32))
        self.assertTrue(result.used_all_expert_fallback)
        self.assertEqual("missing_certificate", result.fail_closed_reason)
        # A 6MiB expert budget cannot admit the recursively selected set.
        bounded = LbitMoEControlPlane(
            pages,
            certificate=OmissionCertificate({page.stable_id: 0 for page in pages}, 1),
            tail_mass_threshold=1,
            resident_budget_bytes=6 * 1024 * 1024,
        )
        result = bounded.select(bytes(32))
        self.assertTrue(result.used_all_expert_fallback)
        self.assertEqual("resident_budget", result.fail_closed_reason)
        self.assertFalse(result.resident_admitted)
        self.assertEqual(256, len(result.active_ids))

    def test_certificate_must_match_page_committed_bounds(self):
        pages = make_pages()
        mismatched = {page.stable_id: 0 for page in pages}
        mismatched["e255"] = 1
        control = LbitMoEControlPlane(
            pages,
            certificate=OmissionCertificate(mismatched, 1),
            tail_mass_threshold=1,
        )
        result = control.select(bytes(32))
        self.assertTrue(result.used_all_expert_fallback)
        self.assertEqual("certificate_integrity", result.fail_closed_reason)
        self.assertEqual(256, len(result.active_ids))


if __name__ == "__main__":
    unittest.main()
