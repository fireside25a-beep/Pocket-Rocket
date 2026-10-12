#include "binary32.h"

#include <fenv.h>
#include <float.h>
#include <string.h>
#include <stdatomic.h>

#if defined(__i386__) || defined(__x86_64__)
#define NR_BINARY32_X87_TARGET 1
#else
#define NR_BINARY32_X87_TARGET 0
#endif

static atomic_int nr_binary32_mode_value = ATOMIC_VAR_INIT(NR_BINARY32_MODE_HARDWARE);

int nr_binary32_set_mode(nr_binary32_mode mode)
{
    if (mode != NR_BINARY32_MODE_EXACT && mode != NR_BINARY32_MODE_HARDWARE) {
        return 0;
    }
    atomic_store_explicit(&nr_binary32_mode_value, (int)mode, memory_order_relaxed);
    return 1;
}

nr_binary32_mode nr_binary32_get_mode(void)
{
    return (nr_binary32_mode)atomic_load_explicit(&nr_binary32_mode_value, memory_order_relaxed);
}

typedef struct binary32_parts {
    uint32_t sign;
    uint32_t exponent;
    uint32_t fraction;
} binary32_parts;

static binary32_parts split_bits(uint32_t bits)
{
    binary32_parts parts;
    parts.sign = bits >> 31U;
    parts.exponent = (bits >> 23U) & UINT32_C(0xff);
    parts.fraction = bits & UINT32_C(0x7fffff);
    return parts;
}

static int is_nan(binary32_parts parts)
{
    return parts.exponent == UINT32_C(0xff) && parts.fraction != 0U;
}

static int is_infinity(binary32_parts parts)
{
    return parts.exponent == UINT32_C(0xff) && parts.fraction == 0U;
}

static int is_zero(binary32_parts parts)
{
    return parts.exponent == 0U && parts.fraction == 0U;
}

static uint32_t pack_infinity(uint32_t sign)
{
    return (sign << 31U) | UINT32_C(0x7f800000);
}

static uint32_t pack_zero(uint32_t sign)
{
    return sign << 31U;
}

static uint64_t shift_right_jam(uint64_t value, unsigned int shift)
{
    uint64_t shifted;

    if (shift == 0U) {
        return value;
    }
    if (shift >= 64U) {
        return value == 0U ? 0U : UINT64_C(1);
    }
    shifted = value >> shift;
    if ((value << (64U - shift)) != 0U) {
        shifted |= UINT64_C(1);
    }
    return shifted;
}

static uint64_t round_shift_even(uint64_t value, unsigned int shift)
{
    uint64_t quotient;
    uint64_t remainder;
    uint64_t halfway;

    if (shift == 0U) {
        return value;
    }
    if (shift >= 64U) {
        if (shift > 64U || value < (UINT64_C(1) << 63U)) {
            return 0U;
        }
        return value > (UINT64_C(1) << 63U) ? 1U : 0U;
    }
    quotient = value >> shift;
    remainder = value & ((UINT64_C(1) << shift) - UINT64_C(1));
    halfway = UINT64_C(1) << (shift - 1U);
    if (remainder > halfway ||
        (remainder == halfway && (quotient & UINT64_C(1)) != 0U)) {
        ++quotient;
    }
    return quotient;
}

static uint32_t round_pack(uint32_t sign, uint64_t extended, int exponent)
{
    uint64_t rounded;

    if (extended == 0U) {
        return pack_zero(0U);
    }
    while (extended >= (UINT64_C(1) << 27U)) {
        extended = shift_right_jam(extended, 1U);
        ++exponent;
    }
    while (extended < (UINT64_C(1) << 26U)) {
        extended <<= 1U;
        --exponent;
    }
    if (exponent < -149) {
        unsigned int shift = (unsigned int)(-146 - exponent);
        rounded = round_shift_even(extended, shift);
        if (rounded >= (UINT64_C(1) << 23U)) {
            return (sign << 31U) | UINT32_C(0x00800000);
        }
        return (sign << 31U) | (uint32_t)rounded;
    }
    rounded = round_shift_even(extended, 3U);
    if (rounded >= (UINT64_C(1) << 24U)) {
        rounded >>= 1U;
        ++exponent;
    }
    if (exponent > 104) {
        return pack_infinity(sign);
    }
    return (sign << 31U) |
           ((uint32_t)(exponent + 150) << 23U) |
           ((uint32_t)rounded & UINT32_C(0x7fffff));
}

static void finite_parts(binary32_parts parts,
                         uint64_t *significand,
                         int *exponent)
{
    if (parts.exponent == 0U) {
        *significand = (uint64_t)parts.fraction;
        *exponent = -149;
    } else {
        *significand = UINT64_C(0x800000) | (uint64_t)parts.fraction;
        *exponent = (int)parts.exponent - 150;
    }
}

uint32_t nr_binary32_from_int32_reference(int32_t value)
{
    uint32_t sign = value < 0 ? UINT32_C(1) : UINT32_C(0);
    uint64_t magnitude = value < 0 ? (uint64_t)(-(int64_t)value) : (uint64_t)value;
    unsigned int msb = 0U;
    uint64_t tmp;
    uint64_t significand;
    unsigned int shift;
    uint64_t remainder;
    uint64_t halfway;
    uint32_t exponent;

    if (magnitude == 0U) {
        return 0U;
    }
    tmp = magnitude;
    while ((tmp >>= 1U) != 0U) {
        ++msb;
    }
    exponent = (uint32_t)(msb + 127U);
    if (msb <= 23U) {
        significand = magnitude << (23U - msb);
    } else {
        shift = msb - 23U;
        significand = magnitude >> shift;
        remainder = magnitude & ((UINT64_C(1) << shift) - UINT64_C(1));
        halfway = UINT64_C(1) << (shift - 1U);
        if (remainder > halfway || (remainder == halfway && (significand & UINT64_C(1)) != 0U)) {
            ++significand;
            if (significand == UINT64_C(0x1000000)) {
                significand >>= 1U;
                ++exponent;
            }
        }
    }
    return (sign << 31U) | (exponent << 23U) | ((uint32_t)significand & UINT32_C(0x7fffff));
}

uint32_t nr_binary32_add_reference(uint32_t left, uint32_t right)
{
    binary32_parts lhs = split_bits(left);
    binary32_parts rhs = split_bits(right);
    uint64_t left_significand;
    uint64_t right_significand;
    uint64_t left_extended;
    uint64_t right_extended;
    uint64_t extended;
    int left_exponent;
    int right_exponent;
    int exponent;
    uint32_t sign;

    if (is_nan(lhs) || is_nan(rhs)) {
        return NR_BINARY32_CANONICAL_NAN;
    }
    if (is_infinity(lhs)) {
        if (is_infinity(rhs) && lhs.sign != rhs.sign) {
            return NR_BINARY32_CANONICAL_NAN;
        }
        return pack_infinity(lhs.sign);
    }
    if (is_infinity(rhs)) {
        return pack_infinity(rhs.sign);
    }
    if (is_zero(lhs) && is_zero(rhs)) {
        return pack_zero(lhs.sign & rhs.sign);
    }
    if (is_zero(lhs)) {
        return right;
    }
    if (is_zero(rhs)) {
        return left;
    }
    finite_parts(lhs, &left_significand, &left_exponent);
    finite_parts(rhs, &right_significand, &right_exponent);
    exponent = left_exponent > right_exponent ? left_exponent : right_exponent;
    left_extended = shift_right_jam(left_significand << 3U,
                                    (unsigned int)(exponent - left_exponent));
    right_extended = shift_right_jam(right_significand << 3U,
                                     (unsigned int)(exponent - right_exponent));
    if (lhs.sign == rhs.sign) {
        extended = left_extended + right_extended;
        sign = lhs.sign;
    } else if (left_extended > right_extended) {
        extended = left_extended - right_extended;
        sign = lhs.sign;
    } else if (right_extended > left_extended) {
        extended = right_extended - left_extended;
        sign = rhs.sign;
    } else {
        return pack_zero(0U);
    }
    return round_pack(sign, extended, exponent);
}

uint32_t nr_binary32_mul_reference(uint32_t left, uint32_t right)
{
    binary32_parts lhs = split_bits(left);
    binary32_parts rhs = split_bits(right);
    uint64_t left_significand;
    uint64_t right_significand;
    uint64_t extended;
    int left_exponent;
    int right_exponent;
    int exponent;
    uint32_t sign = lhs.sign ^ rhs.sign;

    if (is_nan(lhs) || is_nan(rhs)) {
        return NR_BINARY32_CANONICAL_NAN;
    }
    if ((is_infinity(lhs) && is_zero(rhs)) ||
        (is_infinity(rhs) && is_zero(lhs))) {
        return NR_BINARY32_CANONICAL_NAN;
    }
    if (is_infinity(lhs) || is_infinity(rhs)) {
        return pack_infinity(sign);
    }
    if (is_zero(lhs) || is_zero(rhs)) {
        return pack_zero(sign);
    }
    finite_parts(lhs, &left_significand, &left_exponent);
    finite_parts(rhs, &right_significand, &right_exponent);
    extended = (left_significand * right_significand) << 3U;
    exponent = left_exponent + right_exponent;
    return round_pack(sign, extended, exponent);
}

static uint32_t canonicalize_candidate(uint32_t candidate)
{
    binary32_parts parts = split_bits(candidate);
    return is_nan(parts) ? NR_BINARY32_CANONICAL_NAN : candidate;
}

static uint32_t hardware_binary32(uint32_t left, uint32_t right, int multiply)
{
    float left_value;
    float right_value;
    float result;
    uint32_t bits;

    memcpy(&left_value, &left, sizeof(left_value));
    memcpy(&right_value, &right, sizeof(right_value));
    result = multiply != 0 ? left_value * right_value : left_value + right_value;
    memcpy(&bits, &result, sizeof(bits));
    return canonicalize_candidate(bits);
}

#if NR_BINARY32_X87_TARGET
static uint32_t x87_binary32(uint32_t left, uint32_t right, int multiply)
{
    float left_value;
    float right_value;
    float result;

    memcpy(&left_value, &left, sizeof(left_value));
    memcpy(&right_value, &right, sizeof(right_value));
    if (multiply != 0) {
        __asm__ volatile(
            "flds %1\n\t"
            "fmuls %2\n\t"
            "fstps %0\n\t"
            : "=m"(result)
            : "m"(left_value), "m"(right_value)
            : "memory");
    } else {
        __asm__ volatile(
            "flds %1\n\t"
            "fadds %2\n\t"
            "fstps %0\n\t"
            : "=m"(result)
            : "m"(left_value), "m"(right_value)
            : "memory");
    }
    memcpy(&left, &result, sizeof(left));
    return canonicalize_candidate(left);
}

typedef struct x87_vector {
    uint32_t left;
    uint32_t right;
    uint32_t expected_add;
    uint32_t expected_mul;
} x87_vector;

static const x87_vector x87_vectors[] = {
    {UINT32_C(0x00000000), UINT32_C(0x80000000), UINT32_C(0x00000000), UINT32_C(0x80000000)},
    {UINT32_C(0x80000000), UINT32_C(0x80000000), UINT32_C(0x80000000), UINT32_C(0x00000000)},
    {UINT32_C(0x3f800000), UINT32_C(0x33800000), UINT32_C(0x3f800000), UINT32_C(0x33800000)},
    {UINT32_C(0x3f800000), UINT32_C(0x34400000), UINT32_C(0x3f800002), UINT32_C(0x34400000)},
    {UINT32_C(0x7f7fffff), UINT32_C(0x7f7fffff), UINT32_C(0x7f800000), UINT32_C(0x7f800000)},
    {UINT32_C(0x00800000), UINT32_C(0x807fffff), UINT32_C(0x00000001), UINT32_C(0x80000000)},
    {UINT32_C(0x00000001), UINT32_C(0x00000001), UINT32_C(0x00000002), UINT32_C(0x00000000)},
    {UINT32_C(0x7f800000), UINT32_C(0xff800000), UINT32_C(0x7fc00000), UINT32_C(0xff800000)},
    {UINT32_C(0x7f800000), UINT32_C(0x00000000), UINT32_C(0x7f800000), UINT32_C(0x7fc00000)},
    {UINT32_C(0x7fa12345), UINT32_C(0x3f800000), UINT32_C(0x7fc00000), UINT32_C(0x7fc00000)}
};
#endif

const char *nr_binary32_x87_gate_reason(void)
{
#if NR_BINARY32_X87_TARGET
    size_t index;

    if (sizeof(float) != 4U || FLT_RADIX != 2 || FLT_MANT_DIG != 24) {
        return "x87 rejected: host float is not IEEE binary32";
    }
    if (fegetround() != FE_TONEAREST) {
        return "x87 rejected: host rounding mode is not round-to-nearest";
    }
    for (index = 0U; index < sizeof(x87_vectors) / sizeof(x87_vectors[0]); ++index) {
        const x87_vector *vector = &x87_vectors[index];
        if (x87_binary32(vector->left, vector->right, 0) != vector->expected_add ||
            x87_binary32(vector->left, vector->right, 1) != vector->expected_mul) {
            return "x87 rejected: candidate differs from a canonical edge vector";
        }
    }
    return "x87 accepted: edge vectors match canonical binary32 reference";
#else
    return "x87 rejected: target is not i386 or x86-64";
#endif
}

int nr_binary32_x87_conformance_gate(void)
{
    return strncmp(nr_binary32_x87_gate_reason(), "x87 accepted:", 13U) == 0;
}

static uint32_t exact_mode_reference(uint32_t left, uint32_t right, int multiply,
                                     nr_binary32_stats *stats);

static uint32_t x87_reference_fallback(uint32_t left,
                                       uint32_t right,
                                       int multiply,
                                       nr_binary32_stats *stats)
{
    if (stats != NULL) {
        if (multiply != 0) {
            ++stats->mul_calls;
        } else {
            ++stats->add_calls;
        }
        ++stats->reference_fallbacks;
    }
    return multiply != 0 ? nr_binary32_mul_reference(left, right)
                         : nr_binary32_add_reference(left, right);
}

uint32_t nr_binary32_add_x87_fast(uint32_t left,
                                  uint32_t right,
                                  nr_binary32_stats *stats)
{
    if (nr_binary32_get_mode() == NR_BINARY32_MODE_EXACT) {
        return exact_mode_reference(left, right, 0, stats);
    }
    if (!nr_binary32_x87_conformance_gate()) {
        return x87_reference_fallback(left, right, 0, stats);
    }
#if NR_BINARY32_X87_TARGET
    return nr_binary32_add_checked(left, right,
                                   x87_binary32(left, right, 0), stats);
#else
    return x87_reference_fallback(left, right, 0, stats);
#endif
}

uint32_t nr_binary32_mul_x87_fast(uint32_t left,
                                  uint32_t right,
                                  nr_binary32_stats *stats)
{
    if (nr_binary32_get_mode() == NR_BINARY32_MODE_EXACT) {
        return exact_mode_reference(left, right, 1, stats);
    }
    if (!nr_binary32_x87_conformance_gate()) {
        return x87_reference_fallback(left, right, 1, stats);
    }
#if NR_BINARY32_X87_TARGET
    return nr_binary32_mul_checked(left, right,
                                   x87_binary32(left, right, 1), stats);
#else
    return x87_reference_fallback(left, right, 1, stats);
#endif
}

uint32_t nr_binary32_add_checked(uint32_t left,
                                 uint32_t right,
                                 uint32_t candidate,
                                 nr_binary32_stats *stats)
{
    uint32_t reference = nr_binary32_add_reference(left, right);
    uint32_t normalized_candidate = canonicalize_candidate(candidate);

    if (stats != NULL) {
        ++stats->add_calls;
        ++stats->hardware_candidates;
        if (normalized_candidate != reference) {
            ++stats->candidate_mismatches;
            ++stats->reference_fallbacks;
        }
    }
    return reference;
}

uint32_t nr_binary32_mul_checked(uint32_t left,
                                 uint32_t right,
                                 uint32_t candidate,
                                 nr_binary32_stats *stats)
{
    uint32_t reference = nr_binary32_mul_reference(left, right);
    uint32_t normalized_candidate = canonicalize_candidate(candidate);

    if (stats != NULL) {
        ++stats->mul_calls;
        ++stats->hardware_candidates;
        if (normalized_candidate != reference) {
            ++stats->candidate_mismatches;
            ++stats->reference_fallbacks;
        }
    }
    return reference;
}

static uint32_t exact_mode_reference(uint32_t left, uint32_t right, int multiply,
                                     nr_binary32_stats *stats)
{
    if (stats != NULL) {
        stats->mode = NR_BINARY32_MODE_EXACT;
        ++stats->exact_mode_calls;
        if (multiply != 0) { ++stats->mul_calls; } else { ++stats->add_calls; }
    }
    return multiply != 0 ? nr_binary32_mul_reference(left, right)
                         : nr_binary32_add_reference(left, right);
}

uint32_t nr_binary32_add_fast(uint32_t left,
                              uint32_t right,
                              nr_binary32_stats *stats)
{
    if (nr_binary32_get_mode() == NR_BINARY32_MODE_EXACT) {
        return exact_mode_reference(left, right, 0, stats);
    }
    if (stats != NULL) { stats->mode = NR_BINARY32_MODE_HARDWARE; }
    return nr_binary32_add_checked(left, right,
                                   hardware_binary32(left, right, 0), stats);
}

uint32_t nr_binary32_mul_fast(uint32_t left,
                              uint32_t right,
                              nr_binary32_stats *stats)
{
    if (nr_binary32_get_mode() == NR_BINARY32_MODE_EXACT) {
        return exact_mode_reference(left, right, 1, stats);
    }
    if (stats != NULL) { stats->mode = NR_BINARY32_MODE_HARDWARE; }
    return nr_binary32_mul_checked(left, right,
                                   hardware_binary32(left, right, 1), stats);
}

void nr_binary32_stats_reset(nr_binary32_stats *stats)
{
    if (stats != NULL) {
        memset(stats, 0, sizeof(*stats));
        stats->mode = nr_binary32_get_mode();
    }
}
