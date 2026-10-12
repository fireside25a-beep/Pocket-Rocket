"""Exact ternary arithmetic and packed sign-plane vectors.

The production types in this module never construct a Python ``float``.  A
triadic value is the exact rational ``numerator / 3**exponent`` and is reduced
canonically.  Ternary vectors use the actual alphabet {-1, 0, +1}; their fast
dot product operates directly on positive and negative bit planes.

General surreal numbers form a proper class and cannot be materialised by a
program.  Finite computation only needs the exact rational fragment used by
the model.  ``ExactRational`` therefore represents that computable fragment
without claiming that a finite process contains the surreal universe.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from math import gcd
from typing import Iterable, Iterator


class TernaryError(ValueError):
    """Raised when a ternary value is malformed or non-canonical."""


class Trit(IntEnum):
    NEGATIVE = -1
    UNKNOWN = 0
    POSITIVE = 1


def _require_plain_int(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    return value


@dataclass(frozen=True, slots=True)
class ExactRational:
    """Canonical, unbounded exact rational used at decision boundaries."""

    numerator: int
    denominator: int = 1

    def __post_init__(self) -> None:
        numerator = _require_plain_int(self.numerator, "numerator")
        denominator = _require_plain_int(self.denominator, "denominator")
        if denominator == 0:
            raise ZeroDivisionError("exact-rational denominator is zero")
        if denominator < 0:
            numerator = -numerator
            denominator = -denominator
        divisor = gcd(abs(numerator), denominator)
        object.__setattr__(self, "numerator", numerator // divisor)
        object.__setattr__(self, "denominator", denominator // divisor)

    def __add__(self, other: object) -> "ExactRational":
        if not isinstance(other, ExactRational):
            return NotImplemented
        return ExactRational(
            self.numerator * other.denominator + other.numerator * self.denominator,
            self.denominator * other.denominator,
        )

    def __sub__(self, other: object) -> "ExactRational":
        if not isinstance(other, ExactRational):
            return NotImplemented
        return ExactRational(
            self.numerator * other.denominator - other.numerator * self.denominator,
            self.denominator * other.denominator,
        )

    def __mul__(self, other: object) -> "ExactRational":
        if not isinstance(other, ExactRational):
            return NotImplemented
        return ExactRational(self.numerator * other.numerator, self.denominator * other.denominator)

    def compare(self, other: "ExactRational") -> int:
        delta = self.numerator * other.denominator - other.numerator * self.denominator
        return (delta > 0) - (delta < 0)

    def as_pair(self) -> tuple[int, int]:
        return self.numerator, self.denominator


@dataclass(frozen=True, slots=True)
class Triadic:
    """Canonical exact value ``numerator / 3**exponent``."""

    numerator: int
    exponent: int = 0

    def __post_init__(self) -> None:
        numerator = _require_plain_int(self.numerator, "numerator")
        exponent = _require_plain_int(self.exponent, "exponent")
        if exponent < 0:
            raise TernaryError("triadic exponent must be non-negative")
        if numerator == 0:
            exponent = 0
        else:
            while exponent and numerator % 3 == 0:
                numerator //= 3
                exponent -= 1
        object.__setattr__(self, "numerator", numerator)
        object.__setattr__(self, "exponent", exponent)

    @property
    def denominator(self) -> int:
        return 3**self.exponent

    def as_rational(self) -> ExactRational:
        return ExactRational(self.numerator, self.denominator)

    def align(self, exponent: int) -> int:
        exponent = _require_plain_int(exponent, "exponent")
        if exponent < self.exponent:
            raise TernaryError("cannot align a triadic value to a coarser exponent")
        return self.numerator * (3 ** (exponent - self.exponent))

    def __add__(self, other: object) -> "Triadic":
        if not isinstance(other, Triadic):
            return NotImplemented
        exponent = max(self.exponent, other.exponent)
        return Triadic(self.align(exponent) + other.align(exponent), exponent)

    def __sub__(self, other: object) -> "Triadic":
        if not isinstance(other, Triadic):
            return NotImplemented
        exponent = max(self.exponent, other.exponent)
        return Triadic(self.align(exponent) - other.align(exponent), exponent)

    def __mul__(self, other: object) -> "Triadic":
        if not isinstance(other, Triadic):
            return NotImplemented
        return Triadic(self.numerator * other.numerator, self.exponent + other.exponent)

    def compare(self, other: "Triadic") -> int:
        exponent = max(self.exponent, other.exponent)
        delta = self.align(exponent) - other.align(exponent)
        return (delta > 0) - (delta < 0)

    def __lt__(self, other: "Triadic") -> bool:
        return self.compare(other) < 0

    def __le__(self, other: "Triadic") -> bool:
        return self.compare(other) <= 0


@dataclass(frozen=True, slots=True)
class Dyadic:
    """Exact dyadic ``numerator / 2**exponent`` for I/O/accounting scales."""

    numerator: int
    exponent: int = 0

    def __post_init__(self) -> None:
        numerator = _require_plain_int(self.numerator, "numerator")
        exponent = _require_plain_int(self.exponent, "exponent")
        if exponent < 0:
            raise ValueError("dyadic exponent must be non-negative")
        if numerator == 0:
            exponent = 0
        else:
            while exponent and numerator % 2 == 0:
                numerator //= 2
                exponent -= 1
        object.__setattr__(self, "numerator", numerator)
        object.__setattr__(self, "exponent", exponent)

    def as_rational(self) -> ExactRational:
        return ExactRational(self.numerator, 2**self.exponent)


@dataclass(frozen=True, slots=True)
class TernaryVector:
    """A bounded vector encoded directly as disjoint sign bit planes."""

    positive: int
    negative: int
    count: int

    def __post_init__(self) -> None:
        positive = _require_plain_int(self.positive, "positive")
        negative = _require_plain_int(self.negative, "negative")
        count = _require_plain_int(self.count, "count")
        if positive < 0 or negative < 0 or count < 0:
            raise TernaryError("negative sign-plane field")
        mask = (1 << count) - 1 if count else 0
        if positive & negative:
            raise TernaryError("positive and negative planes overlap")
        if (positive | negative) & ~mask:
            raise TernaryError("non-zero ternary padding")

    @classmethod
    def from_trits(cls, values: Iterable[int]) -> "TernaryVector":
        positive = 0
        negative = 0
        count = 0
        for count, value in enumerate(values, start=1):
            trit = _require_plain_int(value, f"trit[{count - 1}]")
            if trit == 1:
                positive |= 1 << (count - 1)
            elif trit == -1:
                negative |= 1 << (count - 1)
            elif trit != 0:
                raise TernaryError(f"trit[{count - 1}] is outside -1, 0, +1")
        return cls(positive, negative, count)

    @classmethod
    def quantize_integers(cls, values: Iterable[int], threshold: int) -> "TernaryVector":
        """Deterministically ternarize signed integers without floating point."""
        threshold = _require_plain_int(threshold, "threshold")
        if threshold < 1:
            raise TernaryError("threshold must be positive")
        trits = []
        for index, value in enumerate(values):
            value = _require_plain_int(value, f"value[{index}]")
            trits.append(1 if value >= threshold else -1 if value <= -threshold else 0)
        return cls.from_trits(trits)

    def __len__(self) -> int:
        return self.count

    def __iter__(self) -> Iterator[int]:
        for index in range(self.count):
            bit = 1 << index
            yield 1 if self.positive & bit else -1 if self.negative & bit else 0

    def dot(self, other: "TernaryVector") -> int:
        if self.count != other.count:
            raise TernaryError("ternary dot-product lengths differ")
        same = (self.positive & other.positive).bit_count()
        same += (self.negative & other.negative).bit_count()
        opposite = (self.positive & other.negative).bit_count()
        opposite += (self.negative & other.positive).bit_count()
        return same - opposite

    def scaled_dot(self, other: "TernaryVector", scale: Triadic) -> Triadic:
        return Triadic(self.dot(other) * scale.numerator, scale.exponent)

    def pack(self) -> bytes:
        """Pack four trits per byte using canonical codes 0, 1, 2."""
        output = bytearray((self.count + 3) // 4)
        for index, trit in enumerate(self):
            code = trit + 1
            output[index // 4] |= code << (2 * (index % 4))
        return bytes(output)

    @classmethod
    def unpack(cls, packed: bytes, count: int) -> "TernaryVector":
        count = _require_plain_int(count, "count")
        if count < 0 or len(packed) != (count + 3) // 4:
            raise TernaryError("packed ternary length mismatch")
        trits: list[int] = []
        for index in range(count):
            code = (packed[index // 4] >> (2 * (index % 4))) & 3
            if code == 3:
                raise TernaryError("reserved ternary symbol 3")
            trits.append(code - 1)
        used = count % 4
        if packed and used and packed[-1] >> (2 * used):
            raise TernaryError("non-canonical ternary tail padding")
        return cls.from_trits(trits)
