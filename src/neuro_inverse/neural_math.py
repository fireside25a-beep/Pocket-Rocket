"""Deterministic reference neural math over binary32 bit patterns.

This module is deliberately an integer/bit-pattern boundary.  It does not
convert through host ``float`` or NumPy.  Every reduction is in the order
documented by its function and every elementary arithmetic operation is
delegated to :mod:`neuro_inverse.binary32`.

The exponential is a fixed range-reduced Taylor approximation (seven terms)
with binary32 rounding after every multiply/add.  It is deterministic and
bounded, but is not advertised as correctly-rounded transcendental math.
Backends may only replace it after bit-for-bit conformance against this
reference path.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Sequence

from .binary32 import (
    CANONICAL_NAN,
    NEGATIVE_INFINITY,
    POSITIVE_INFINITY,
    add_bits,
    divide_bits,
    dot_product_bits,
    is_infinite,
    is_nan,
    is_zero,
    multiply_bits,
    sqrt_bits,
)


ZERO = 0x00000000
ONE = 0x3F800000
HALF = 0x3F000000
NEG_ONE = 0xBF800000
LN2 = 0x3F317218             # nearest binary32 ln(2)
NEG_LN2 = 0xBF317218
INV_LN2 = 0x3FB8AA3B         # nearest binary32 1/ln(2)
DEFAULT_EPSILON = 0x3727C5AC # nearest binary32 1e-5

# 1/k!, k=0..7, represented as binary32 constants.  Keeping these constants
# in the source makes the approximation and its rounding contract auditable.
_EXP_COEFFICIENTS = (
    0x3F800000,  # 1
    0x3F800000,  # 1
    0x3F000000,  # 1/2
    0x3E2AAAAB,  # 1/6
    0x3D2AAAAB,  # 1/24
    0x3C088889,  # 1/120
    0x3AB60B61,  # 1/720
    0x39500D01,  # 1/5040
)


def _validate_bits(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("neural-math values must be unsigned binary32 bit patterns")
    return value


def _finite_fraction(value: int) -> Fraction:
    """Decode finite binary32 without using host floating point."""

    value = _validate_bits(value)
    sign = value >> 31
    exponent = (value >> 23) & 0xFF
    fraction = value & 0x7FFFFF
    if exponent == 0:
        magnitude = Fraction(fraction, 1 << 149)
    else:
        significand = (1 << 23) | fraction
        shift = exponent - 150
        magnitude = Fraction(significand << shift, 1) if shift >= 0 else Fraction(significand, 1 << -shift)
    return -magnitude if sign else magnitude


def _ordered_compare(left: int, right: int) -> int:
    """Numeric comparison for non-NaN binary32, with stable zero handling."""

    left, right = _validate_bits(left), _validate_bits(right)
    if is_zero(left) and is_zero(right):
        return 0
    if is_infinite(left) or is_infinite(right):
        if left == right:
            return 0
        return -1 if left == NEGATIVE_INFINITY or right == POSITIVE_INFINITY else 1
    lf, rf = _finite_fraction(left), _finite_fraction(right)
    return (lf > rf) - (lf < rf)


def _round_nearest_integer(value: Fraction) -> int:
    """Round an exact rational to nearest integer, ties to even."""

    if value.denominator <= 0:
        raise ValueError("invalid rational")
    sign = -1 if value < 0 else 1
    magnitude = abs(value)
    quotient, remainder = divmod(magnitude.numerator, magnitude.denominator)
    twice = remainder * 2
    if twice > magnitude.denominator or (twice == magnitude.denominator and quotient & 1):
        quotient += 1
    return sign * quotient


def _power_of_two_bits(exponent: int) -> int:
    """Return an exact binary32 encoding for 2**exponent when representable."""

    if exponent > 127:
        return POSITIVE_INFINITY
    if exponent < -149:
        return ZERO
    if exponent >= -126:
        return (exponent + 127) << 23
    return 1 << (exponent + 149)


def exp_bits(value: int) -> int:
    """Deterministic binary32 exponential approximation.

    Inputs above ``+88`` overflow the binary32 result and inputs below ``-104``
    underflow to zero.  In the finite interior, ``x = n*ln(2) + r`` where
    ``n`` is exact nearest-even integer reduction, followed by a seven-term
    Horner polynomial.  Every polynomial operation rounds through the exact
    binary32 reference primitive.
    """

    value = _validate_bits(value)
    if is_nan(value):
        return CANONICAL_NAN
    if value == POSITIVE_INFINITY:
        return POSITIVE_INFINITY
    if value == NEGATIVE_INFINITY:
        return ZERO
    x = _finite_fraction(value)
    # These bounds are mathematical safe guards, not host-float operations.
    if x > Fraction(89):
        return POSITIVE_INFINITY
    if x < Fraction(-104):
        return ZERO
    # Reduction is by ln(2), not by its reciprocal.  (The reciprocal is kept
    # as a documented constant for implementations that choose a multiply
    # based reducer, but this exact Fraction division avoids a host rounding
    # decision at the integer boundary.)
    n = _round_nearest_integer(x / _finite_fraction(LN2))
    # n is in a small range after the bounds above, so the integer-to-binary32
    # conversion is exact for this reduction step.
    n_ln2 = multiply_bits(_power_of_two_bits(0), ZERO)  # initialized as +0
    if n:
        # Build n*ln2 with binary32 arithmetic.  The integer itself is small.
        magnitude = abs(n)
        # The range is < 160, so this loop is bounded.  Using repeated
        # addition makes the reduction itself obey the same binary32 rounding
        # contract as the polynomial below.
        n_ln2 = ZERO
        for _ in range(magnitude):
            n_ln2 = add_bits(n_ln2, LN2)
        if n < 0:
            n_ln2 ^= 0x80000000
    remainder = add_bits(value, n_ln2 ^ 0x80000000 if n_ln2 != ZERO else ZERO)
    # Horner evaluation, c7*r + c6 ... c0, fixed left-to-right operation order.
    polynomial = _EXP_COEFFICIENTS[-1]
    for coefficient in reversed(_EXP_COEFFICIENTS[:-1]):
        polynomial = add_bits(multiply_bits(polynomial, remainder), coefficient)
    scale = _power_of_two_bits(n)
    return multiply_bits(polynomial, scale)


def sigmoid_bits(value: int) -> int:
    """Stable deterministic logistic sigmoid over binary32 bit patterns."""

    value = _validate_bits(value)
    if is_nan(value):
        return CANONICAL_NAN
    if value == POSITIVE_INFINITY:
        return ONE
    if value == NEGATIVE_INFINITY:
        return ZERO
    if _ordered_compare(value, ZERO) < 0:
        e = exp_bits(value)
        return divide_bits(e, add_bits(ONE, e))
    e = exp_bits(value ^ 0x80000000)
    return divide_bits(ONE, add_bits(ONE, e))


def silu_bits(value: int) -> int:
    """Compute SiLU(x)=x*sigmoid(x), including explicit infinity behavior."""

    value = _validate_bits(value)
    if is_nan(value):
        return CANONICAL_NAN
    if value == NEGATIVE_INFINITY:
        # The mathematical limit is -0; IEEE inf*0 would otherwise be invalid.
        return 0x80000000
    if value == POSITIVE_INFINITY:
        return POSITIVE_INFINITY
    return multiply_bits(value, sigmoid_bits(value))


def rmsnorm_bits(
    values: Sequence[int],
    weights: Sequence[int] | None = None,
    *,
    epsilon: int = DEFAULT_EPSILON,
) -> list[int]:
    """Fixed-order RMSNorm.

    ``sum(x*x)`` and the final weighted outputs are accumulated in input
    order; ``weights`` defaults to an all-one vector.  Empty vectors and shape
    mismatches are rejected rather than manufacturing a numerical result.
    """

    values = [_validate_bits(v) for v in values]
    if not values:
        raise ValueError("RMSNorm requires at least one value")
    epsilon = _validate_bits(epsilon)
    if is_nan(epsilon) or is_infinite(epsilon) or _ordered_compare(epsilon, ZERO) < 0:
        raise ValueError("RMSNorm epsilon must be finite and non-negative")
    if weights is None:
        weights = [ONE] * len(values)
    else:
        weights = [_validate_bits(v) for v in weights]
        if len(weights) != len(values):
            raise ValueError("RMSNorm values and weights must have equal length")
    sum_squares = ZERO
    for value in values:
        sum_squares = add_bits(sum_squares, multiply_bits(value, value))
    count_bits = _power_of_two_bits(0)
    # Encode small positive integer counts exactly via repeated addition; this
    # avoids a host-float conversion while retaining the fixed reference path.
    count_bits = ZERO
    for _ in values:
        count_bits = add_bits(count_bits, ONE)
    mean_square = divide_bits(sum_squares, count_bits)
    rms = sqrt_bits(add_bits(mean_square, epsilon))
    return [multiply_bits(divide_bits(value, rms), weight) for value, weight in zip(values, weights)]


def softmax_bits(logits: Sequence[int], mask: Sequence[bool] | None = None) -> list[int]:
    """Stable deterministic softmax with ``True`` mask entries retained.

    Masked entries return +0.  NaN in an unmasked entry poisons the complete
    row.  If several entries are +infinity, probability is divided equally
    among those entries; an all-masked row returns all zeros.
    """

    logits = [_validate_bits(v) for v in logits]
    if not logits:
        raise ValueError("softmax requires at least one logit")
    keep = [True] * len(logits) if mask is None else list(mask)
    if len(keep) != len(logits) or any(not isinstance(v, bool) for v in keep):
        raise ValueError("softmax mask must be a bool sequence matching logits")
    active = [index for index, enabled in enumerate(keep) if enabled]
    result = [ZERO] * len(logits)
    if not active:
        return result
    if any(is_nan(logits[index]) for index in active):
        return [CANONICAL_NAN if enabled else ZERO for enabled in keep]
    positive_infinities = [index for index in active if logits[index] == POSITIVE_INFINITY]
    if positive_infinities:
        count = ZERO
        for _ in positive_infinities:
            count = add_bits(count, ONE)
        share = divide_bits(ONE, count)
        for index in positive_infinities:
            result[index] = share
        return result
    maximum = logits[active[0]]
    for index in active[1:]:
        if _ordered_compare(logits[index], maximum) > 0:
            maximum = logits[index]
    if maximum == NEGATIVE_INFINITY:
        # No finite logit exists.  A uniform distribution is the explicit
        # reference convention for this otherwise undefined softmax row.
        count = ZERO
        for _ in active:
            count = add_bits(count, ONE)
        share = divide_bits(ONE, count)
        for index in active:
            result[index] = share
        return result
    numerators: list[int] = []
    total = ZERO
    for index in active:
        delta = add_bits(logits[index], maximum ^ 0x80000000)
        numerator = exp_bits(delta)
        numerators.append(numerator)
        total = add_bits(total, numerator)
    if is_zero(total) or is_nan(total):
        return [CANONICAL_NAN if is_nan(total) and enabled else ZERO for enabled in keep]
    for index, numerator in zip(active, numerators):
        result[index] = divide_bits(numerator, total)
    return result


def attention_bits(
    query: Sequence[int],
    keys: Sequence[Sequence[int]],
    values: Sequence[Sequence[int]],
    *,
    mask: Sequence[bool] | None = None,
    scale: bool = True,
) -> list[int]:
    """Single-query scaled dot-product attention with deterministic masking.

    Scores use left-to-right :func:`dot_product_bits`; scaling is by
    ``1/sqrt(d)`` when enabled.  Values are combined in key order, and masked
    keys contribute exact +0.  All rows must be rectangular and non-empty.
    """

    query = [_validate_bits(v) for v in query]
    if not query:
        raise ValueError("attention query must be non-empty")
    key_rows = [list(row) for row in keys]
    value_rows = [list(row) for row in values]
    if not key_rows or len(key_rows) != len(value_rows):
        raise ValueError("attention requires equally many non-empty key/value rows")
    if any(len(row) != len(query) for row in key_rows):
        raise ValueError("attention key width must equal query width")
    value_width = len(value_rows[0])
    if value_width == 0 or any(len(row) != value_width for row in value_rows):
        raise ValueError("attention values must be rectangular and non-empty")
    if any(_validate_bits(v) != v for row in key_rows + value_rows for v in row):
        raise ValueError("invalid attention bit pattern")
    scores = [dot_product_bits(query, [_validate_bits(v) for v in row]) for row in key_rows]
    if scale:
        # Compute sqrt(d) from exact binary32 count bits.
        count = ZERO
        for _ in query:
            count = add_bits(count, ONE)
        root = sqrt_bits(count)
        scores = [divide_bits(score, root) for score in scores]
    weights = softmax_bits(scores, mask)
    output: list[int] = []
    for column in range(value_width):
        accumulated = ZERO
        for weight, row in zip(weights, value_rows):
            accumulated = add_bits(accumulated, multiply_bits(weight, _validate_bits(row[column])))
        output.append(accumulated)
    return output


__all__ = [
    "DEFAULT_EPSILON", "attention_bits", "exp_bits", "rmsnorm_bits",
    "sigmoid_bits", "silu_bits", "softmax_bits",
]
