"""Dependency-light exact IEEE-754 binary32 arithmetic.

The reference path operates on 32-bit encodings and :class:`fractions.Fraction`
values only.  It does not use host floating-point arithmetic or NumPy as an
oracle.  Results use a canonical quiet NaN so conformance comparisons are
stable even when inputs contain different NaN payloads.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import isqrt
from typing import Callable, Literal


MASK32 = 0xFFFFFFFF
SIGN_MASK = 0x80000000
EXP_MASK = 0x7F800000
FRACTION_MASK = 0x007FFFFF
CANONICAL_NAN = 0x7FC00000
POSITIVE_INFINITY = 0x7F800000
NEGATIVE_INFINITY = 0xFF800000
MIN_SUBNORMAL = 0x00000001
MIN_NORMAL = 0x00800000
MAX_FINITE = 0x7F7FFFFF


def _bits(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MASK32:
        raise ValueError("binary32 bits must be an unsigned 32-bit integer")
    return value


def _parts(value: int) -> tuple[int, int, int]:
    value = _bits(value)
    return (value >> 31, (value >> 23) & 0xFF, value & FRACTION_MASK)


def is_nan(value: int) -> bool:
    _sign, exponent, fraction = _parts(value)
    return exponent == 0xFF and fraction != 0


def is_infinite(value: int) -> bool:
    _sign, exponent, fraction = _parts(value)
    return exponent == 0xFF and fraction == 0


def is_zero(value: int) -> bool:
    _sign, exponent, fraction = _parts(value)
    return exponent == 0 and fraction == 0


def _finite_fraction(value: int) -> Fraction:
    sign, exponent, fraction = _parts(value)
    if exponent == 0:
        magnitude = Fraction(fraction, 1 << 149)
    else:
        significand = (1 << 23) | fraction
        shift = exponent - 150
        magnitude = Fraction(significand << shift, 1) if shift >= 0 else Fraction(significand, 1 << -shift)
    return -magnitude if sign else magnitude


def _round_even(numerator: int, denominator: int) -> int:
    """Round a non-negative rational to an integer, ties to even."""

    if numerator < 0 or denominator <= 0:
        raise ValueError("round_even expects a non-negative numerator and positive denominator")
    quotient, remainder = divmod(numerator, denominator)
    doubled = remainder << 1
    if doubled > denominator or (doubled == denominator and quotient & 1):
        quotient += 1
    return quotient


def _floor_log2(value: Fraction) -> int:
    if value <= 0:
        raise ValueError("log2 is only defined for positive values")
    numerator, denominator = value.numerator, value.denominator
    exponent = numerator.bit_length() - denominator.bit_length()
    if exponent >= 0:
        if numerator < denominator << exponent:
            exponent -= 1
        while numerator >= denominator << (exponent + 1):
            exponent += 1
    else:
        if numerator << -exponent < denominator:
            exponent -= 1
        while numerator << (-(exponent + 1)) >= denominator:
            exponent += 1
    return exponent


def _round_fraction(magnitude: Fraction, sign: int) -> int:
    """Encode a positive exact value as binary32 with gradual underflow."""

    if magnitude < 0 or sign not in (0, 1):
        raise ValueError("magnitude must be non-negative and sign must be one bit")
    if magnitude == 0:
        return sign << 31

    exponent = _floor_log2(magnitude)
    if exponent < -126:
        # Subnormal quantum is 2^-149.  Rounding exactly at half a quantum
        # selects zero because zero has an even significand.
        scaled = magnitude * (1 << 149)
        significand = _round_even(scaled.numerator, scaled.denominator)
        if significand == 0:
            return sign << 31
        if significand >= 1 << 23:
            return (sign << 31) | MIN_NORMAL
        return (sign << 31) | significand

    # A normal binary32 value has a 24-bit significand including its hidden
    # leading bit.  Round the exact significand before assembling fields.
    shift = exponent - 23
    scaled = magnitude / (1 << shift) if shift >= 0 else magnitude * (1 << -shift)
    significand = _round_even(scaled.numerator, scaled.denominator)
    if significand >= 1 << 24:
        significand >>= 1
        exponent += 1
    if exponent > 127:
        return (sign << 31) | POSITIVE_INFINITY
    if exponent < -126:
        # Only reachable after a carry/edge adjustment, but retain gradual
        # underflow as an explicit safety net.
        return _round_fraction(magnitude, sign) if exponent == -126 else sign << 31
    return (sign << 31) | ((exponent + 127) << 23) | (significand - (1 << 23))


def add_bits(left: int, right: int) -> int:
    """Return exact-reference binary32 ``left + right``."""

    left, right = _bits(left), _bits(right)
    sign_left, exponent_left, fraction_left = _parts(left)
    sign_right, exponent_right, fraction_right = _parts(right)
    if is_nan(left) or is_nan(right):
        return CANONICAL_NAN
    if is_infinite(left) or is_infinite(right):
        if is_infinite(left) and is_infinite(right) and sign_left != sign_right:
            return CANONICAL_NAN
        return left if is_infinite(left) else right
    exact = _finite_fraction(left) + _finite_fraction(right)
    if exact == 0:
        # IEEE round-to-nearest gives +0 for cancellation and mixed zeros;
        # adding two negative zeros preserves -0.
        sign = 1 if sign_left == sign_right == 1 else 0
        return sign << 31
    return _round_fraction(abs(exact), 1 if exact < 0 else 0)


def multiply_bits(left: int, right: int) -> int:
    """Return exact-reference binary32 ``left * right``."""

    left, right = _bits(left), _bits(right)
    sign_left, _exponent_left, _fraction_left = _parts(left)
    sign_right, _exponent_right, _fraction_right = _parts(right)
    sign = sign_left ^ sign_right
    if is_nan(left) or is_nan(right):
        return CANONICAL_NAN
    if (is_infinite(left) and is_zero(right)) or (is_infinite(right) and is_zero(left)):
        return CANONICAL_NAN
    if is_infinite(left) or is_infinite(right):
        return sign << 31 | POSITIVE_INFINITY
    if is_zero(left) or is_zero(right):
        return sign << 31
    exact = _finite_fraction(left) * _finite_fraction(right)
    return _round_fraction(abs(exact), sign)


def divide_bits(left: int, right: int) -> int:
    """Return exact-reference binary32 ``left / right``."""

    left, right = _bits(left), _bits(right)
    sign_left, _exponent_left, _fraction_left = _parts(left)
    sign_right, _exponent_right, _fraction_right = _parts(right)
    sign = sign_left ^ sign_right
    if is_nan(left) or is_nan(right):
        return CANONICAL_NAN
    if is_infinite(left) and is_infinite(right):
        return CANONICAL_NAN
    if is_zero(left) and is_zero(right):
        return CANONICAL_NAN
    if is_infinite(left):
        return (sign << 31) | POSITIVE_INFINITY
    if is_infinite(right):
        return sign << 31
    if is_zero(right):
        return (sign << 31) | POSITIVE_INFINITY
    if is_zero(left):
        return sign << 31
    exact = _finite_fraction(left) / _finite_fraction(right)
    return _round_fraction(abs(exact), sign)


def _round_sqrt_ratio(numerator: int, denominator: int) -> int:
    """Round ``sqrt(numerator / denominator)`` to an integer, ties to even."""

    if numerator < 0 or denominator <= 0:
        raise ValueError("sqrt ratio requires a non-negative numerator and positive denominator")
    if numerator == 0:
        return 0
    floor_root = isqrt(numerator * denominator) // denominator
    # Compare the exact square root with floor_root + 1/2 without a float.
    left = numerator << 2
    right = (2 * floor_root + 1) ** 2 * denominator
    if left > right or (left == right and floor_root & 1):
        return floor_root + 1
    return floor_root


def _scaled_square_ratio(magnitude: Fraction, shift: int) -> tuple[int, int]:
    """Return the integer ratio for ``magnitude / (2**shift)**2``."""

    numerator, denominator = magnitude.numerator, magnitude.denominator
    if shift >= 0:
        denominator <<= 2 * shift
    else:
        numerator <<= -2 * shift
    return numerator, denominator


def sqrt_bits(value: int) -> int:
    """Return exact-reference binary32 ``sqrt(value)`` without host floats."""

    value = _bits(value)
    sign, _exponent, _fraction = _parts(value)
    if is_nan(value):
        return CANONICAL_NAN
    if is_zero(value):
        # IEEE sqrt preserves the sign of zero.
        return value
    if sign:
        return CANONICAL_NAN
    if is_infinite(value):
        return POSITIVE_INFINITY

    magnitude = _finite_fraction(value)
    exponent = _floor_log2(magnitude) // 2
    if exponent < -126:
        numerator, denominator = _scaled_square_ratio(magnitude, -149)
        significand = _round_sqrt_ratio(numerator, denominator)
        if significand >= 1 << 23:
            return MIN_NORMAL
        return significand

    shift = exponent - 23
    numerator, denominator = _scaled_square_ratio(magnitude, shift)
    significand = _round_sqrt_ratio(numerator, denominator)
    if significand >= 1 << 24:
        significand >>= 1
        exponent += 1
    if exponent > 127:
        return POSITIVE_INFINITY
    if exponent < -126:
        # Defensive edge path; positive binary32 inputs have a normal square
        # root except for zero, but retain the same gradual-underflow contract.
        numerator, denominator = _scaled_square_ratio(magnitude, -149)
        return _round_sqrt_ratio(numerator, denominator)
    return ((exponent + 127) << 23) | (significand - (1 << 23))


def dot_product_bits(
    left: list[int] | tuple[int, ...],
    right: list[int] | tuple[int, ...],
    *,
    pairwise: bool = False,
) -> int:
    """Compute a fixed binary32 dot product using reference multiply/add only.

    The default is deterministic left-to-right accumulation.  ``pairwise`` is
    a deliberately distinct balanced tree and may produce a different rounded
    result; it is never silently substituted for the default.
    """

    if len(left) != len(right):
        raise ValueError("dot-product operands must have equal length")
    products = [multiply_bits(a, b) for a, b in zip(left, right)]
    if not products:
        return 0
    if not pairwise:
        result = 0
        for product in products:
            result = add_bits(result, product)
        return result
    while len(products) > 1:
        products = [
            add_bits(products[index], products[index + 1])
            for index in range(0, len(products) - 1, 2)
        ] + (products[-1:] if len(products) & 1 else [])
    return products[0]


Binary32Candidate = Callable[[int, int], int]
UnaryBinary32Candidate = Callable[[int], int]
Operation = Literal["add", "multiply", "divide"]
UnaryOperation = Literal["sqrt"]


@dataclass(frozen=True)
class CandidateResult:
    operation: Operation | UnaryOperation
    reference_bits: int
    result_bits: int
    candidate_bits: int | None
    hardware_accepted: bool
    mismatch: bool


def evaluate_candidate(
    operation: Operation,
    left: int,
    right: int,
    candidate: Binary32Candidate | None,
) -> CandidateResult:
    """Accept a hardware candidate only after exact bitwise agreement."""

    if operation == "add":
        reference = add_bits(left, right)
    elif operation == "multiply":
        reference = multiply_bits(left, right)
    elif operation == "divide":
        reference = divide_bits(left, right)
    else:
        raise ValueError(f"unsupported binary32 operation: {operation!r}")
    if candidate is None:
        return CandidateResult(operation, reference, reference, None, False, False)
    candidate_bits: int | None
    try:
        candidate_bits = _bits(candidate(_bits(left), _bits(right)))
    except Exception:
        candidate_bits = None
    if candidate_bits == reference:
        return CandidateResult(operation, reference, candidate_bits, candidate_bits, True, False)
    return CandidateResult(operation, reference, reference, candidate_bits, False, True)


def evaluate_unary_candidate(
    operation: UnaryOperation,
    value: int,
    candidate: UnaryBinary32Candidate | None,
) -> CandidateResult:
    """Accept a unary hardware candidate only after exact bitwise agreement."""

    if operation != "sqrt":
        raise ValueError(f"unsupported binary32 unary operation: {operation!r}")
    reference = sqrt_bits(value)
    if candidate is None:
        return CandidateResult(operation, reference, reference, None, False, False)
    candidate_bits: int | None
    try:
        candidate_bits = _bits(candidate(_bits(value)))
    except Exception:
        candidate_bits = None
    if candidate_bits == reference:
        return CandidateResult(operation, reference, candidate_bits, candidate_bits, True, False)
    return CandidateResult(operation, reference, reference, candidate_bits, False, True)


__all__ = [
    "CANONICAL_NAN", "CandidateResult", "MAX_FINITE", "MIN_NORMAL",
    "MIN_SUBNORMAL", "NEGATIVE_INFINITY", "POSITIVE_INFINITY", "add_bits",
    "divide_bits", "dot_product_bits", "evaluate_candidate",
    "evaluate_unary_candidate", "is_infinite", "is_nan", "is_zero",
    "multiply_bits", "sqrt_bits",
]
