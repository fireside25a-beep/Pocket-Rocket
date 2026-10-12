from __future__ import annotations

import unittest

from neuro_inverse.ternary_exact import (
    Dyadic,
    ExactRational,
    TernaryError,
    TernaryVector,
    Triadic,
)
from neuro_inverse.typed_decision import (
    Choice,
    Criterion,
    DecisionError,
    ScoreLevel,
    TernaryStatus,
    choose,
    gate,
    ordered_score,
)


ZERO_ROOT = "0" * 64
ONE_ROOT = "1" * 64


class ExactArithmeticTests(unittest.TestCase):
    def test_triadic_is_canonical_and_exact(self) -> None:
        self.assertEqual(Triadic(2, 1), Triadic(18, 3))
        self.assertEqual(Triadic(7, 2), Triadic(1, 1) + Triadic(4, 2))
        self.assertEqual(Triadic(-2, 3), Triadic(2, 1) * Triadic(-1, 2))
        self.assertLess(Triadic(1, 2), Triadic(1, 1))

    def test_rational_and_dyadic_are_reduced(self) -> None:
        self.assertEqual((1, 2), ExactRational(18, 36).as_pair())
        self.assertEqual(ExactRational(3, 8), Dyadic(6, 4).as_rational())
        self.assertEqual(ExactRational(5, 6), ExactRational(1, 2) + ExactRational(1, 3))

    def test_sign_plane_dot_matches_scalar(self) -> None:
        left_values = [-1, 0, 1, 1, -1, 0, 1, -1, 1]
        right_values = [1, 0, 1, -1, -1, 1, 0, -1, 1]
        left = TernaryVector.from_trits(left_values)
        right = TernaryVector.from_trits(right_values)
        expected = sum(a * b for a, b in zip(left_values, right_values, strict=True))
        self.assertEqual(expected, left.dot(right))
        self.assertEqual(Triadic(expected * 2, 3), left.scaled_dot(right, Triadic(2, 3)))

    def test_pack_roundtrip_and_reserved_symbol(self) -> None:
        vector = TernaryVector.from_trits([-1, 0, 1, 0, 1, -1, -1])
        self.assertEqual(vector, TernaryVector.unpack(vector.pack(), len(vector)))
        with self.assertRaisesRegex(TernaryError, "reserved"):
            TernaryVector.unpack(b"\x03", 1)
        with self.assertRaisesRegex(TernaryError, "padding"):
            TernaryVector.unpack(b"\x41", 1)

    def test_integer_quantization_has_real_zero_state(self) -> None:
        vector = TernaryVector.quantize_integers([-9, -2, 0, 2, 9], threshold=3)
        self.assertEqual((-1, 0, 0, 0, 1), tuple(vector))


class TypedDecisionTests(unittest.TestCase):
    def _run(self, score_value: Triadic):
        return gate(
            [Criterion("safety", score_value)],
            reject_below=Triadic(-1, 1),
            accept_at=Triadic(1, 1),
            model_root=ZERO_ROOT,
            request_root=ONE_ROOT,
        )

    def test_gate_has_three_semantic_states(self) -> None:
        self.assertEqual(TernaryStatus.REJECT, self._run(Triadic(-2, 1)).status)
        self.assertEqual(TernaryStatus.ABSTAIN, self._run(Triadic(0)).status)
        self.assertEqual(TernaryStatus.ACCEPT, self._run(Triadic(1, 1)).status)

    def test_certificate_is_deterministic_and_evidence_sensitive(self) -> None:
        first = self._run(Triadic(2, 1))
        second = self._run(Triadic(2, 1))
        changed = self._run(Triadic(3, 1))
        self.assertEqual(first.certificate, second.certificate)
        self.assertNotEqual(first.certificate, changed.certificate)

    def test_choice_abstains_on_tie_or_small_margin(self) -> None:
        tied = choose([Choice("a", Triadic(1)), Choice("b", Triadic(1))], minimum_margin=Triadic(0))
        narrow = choose(
            [Choice("a", Triadic(4, 1)), Choice("b", Triadic(3, 1))],
            minimum_margin=Triadic(2, 1),
        )
        selected = choose(
            [Choice("a", Triadic(5, 1)), Choice("b", Triadic(2, 1))],
            minimum_margin=Triadic(2, 1),
        )
        self.assertEqual(TernaryStatus.ABSTAIN, tied.status)
        self.assertEqual(TernaryStatus.ABSTAIN, narrow.status)
        self.assertEqual("a", selected.choice)

    def test_invalid_gate_threshold_order_fails(self) -> None:
        with self.assertRaises(DecisionError):
            gate(
                [Criterion("x", Triadic(0))],
                reject_below=Triadic(1),
                accept_at=Triadic(1),
                model_root=ZERO_ROOT,
                request_root=ONE_ROOT,
            )

    def test_ordered_score_returns_exact_distribution_and_confidence(self) -> None:
        result = ordered_score(
            [
                ScoreLevel("low", Triadic(1)),
                ScoreLevel("medium", Triadic(2)),
                ScoreLevel("high", Triadic(6)),
            ],
            minimum_confidence=ExactRational(1, 3),
            model_root=ZERO_ROOT,
            request_root=ONE_ROOT,
        )
        self.assertEqual(TernaryStatus.ACCEPT, result.status)
        self.assertEqual("high", result.level)
        self.assertEqual(2, result.level_index)
        self.assertEqual(ExactRational(14, 9), result.expected_score)
        self.assertEqual(ExactRational(4, 9), result.confidence)
        self.assertEqual(
            (ExactRational(1, 9), ExactRational(2, 9), ExactRational(2, 3)),
            result.probabilities,
        )
        self.assertEqual(64, len(result.certificate))

    def test_ordered_score_abstains_on_tie_or_confidence_gate(self) -> None:
        tied = ordered_score(
            [ScoreLevel("low", Triadic(2)), ScoreLevel("high", Triadic(2))],
            minimum_confidence=ExactRational(0),
            model_root=ZERO_ROOT,
            request_root=ONE_ROOT,
        )
        guarded = ordered_score(
            [ScoreLevel("low", Triadic(4)), ScoreLevel("high", Triadic(5))],
            minimum_confidence=ExactRational(1, 2),
            model_root=ZERO_ROOT,
            request_root=ONE_ROOT,
        )
        self.assertEqual(TernaryStatus.ABSTAIN, tied.status)
        self.assertIsNone(tied.level)
        self.assertEqual(ExactRational(0), tied.confidence)
        self.assertEqual(TernaryStatus.ABSTAIN, guarded.status)
        with self.assertRaises(DecisionError):
            ScoreLevel("negative", Triadic(-1))


if __name__ == "__main__":
    unittest.main()
