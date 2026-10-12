#include "ternary_core.h"

#include <limits.h>
#include <string.h>

static unsigned int nr_popcount64(uint64_t value)
{
    unsigned int count = 0U;
    while (value != 0U) {
        value &= value - UINT64_C(1);
        ++count;
    }
    return count;
}

static int nr_mul_i64(int64_t left, int64_t right, int64_t *out)
{
    if (out == NULL) {
        return 0;
    }
    if (left == 0 || right == 0) {
        *out = 0;
        return 1;
    }
    if ((left == INT64_MIN && right == -1) ||
        (right == INT64_MIN && left == -1)) {
        return 0;
    }
    if (left > 0) {
        if ((right > 0 && left > INT64_MAX / right) ||
            (right < 0 && right < INT64_MIN / left)) {
            return 0;
        }
    } else if ((right > 0 && left < INT64_MIN / right) ||
               (right < 0 && left < INT64_MAX / right)) {
        return 0;
    }
    *out = left * right;
    return 1;
}

static int nr_add_i64(int64_t left, int64_t right, int64_t *out)
{
    if (out == NULL || (right > 0 && left > INT64_MAX - right) ||
        (right < 0 && left < INT64_MIN - right)) {
        return 0;
    }
    *out = left + right;
    return 1;
}

static int nr_scale_three(int64_t value, uint8_t power, int64_t *out)
{
    uint8_t index;
    int64_t scaled = value;
    for (index = 0U; index < power; ++index) {
        if (!nr_mul_i64(scaled, INT64_C(3), &scaled)) {
            return 0;
        }
    }
    *out = scaled;
    return 1;
}

nr_ternary_status nr_ternary_pack(const int8_t *trits,
                                  size_t count,
                                  nr_ternary_vector *out)
{
    size_t index;
    if (out == NULL || (trits == NULL && count != 0U)) {
        return NR_TERNARY_ERR_ARGUMENT;
    }
    memset(out, 0, sizeof(*out));
    if (count > NR_TERNARY_MAX_TRITS) {
        return NR_TERNARY_ERR_RANGE;
    }
    for (index = 0U; index < count; ++index) {
        size_t word = index / 64U;
        unsigned int bit = (unsigned int)(index % 64U);
        if (trits[index] == 1) {
            out->positive[word] |= UINT64_C(1) << bit;
        } else if (trits[index] == -1) {
            out->negative[word] |= UINT64_C(1) << bit;
        } else if (trits[index] != 0) {
            memset(out, 0, sizeof(*out));
            return NR_TERNARY_ERR_TRIT;
        }
    }
    out->count = count;
    return NR_TERNARY_OK;
}

nr_ternary_status nr_ternary_validate(const nr_ternary_vector *vector)
{
    size_t index;
    if (vector == NULL) {
        return NR_TERNARY_ERR_ARGUMENT;
    }
    if (vector->count > NR_TERNARY_MAX_TRITS) {
        return NR_TERNARY_ERR_RANGE;
    }
    for (index = 0U; index < NR_TERNARY_WORDS; ++index) {
        uint64_t used = UINT64_MAX;
        size_t word_start = index * 64U;
        if ((vector->positive[index] & vector->negative[index]) != 0U) {
            return NR_TERNARY_ERR_TRIT;
        }
        if (word_start >= vector->count) {
            used = 0U;
        } else if (vector->count - word_start < 64U) {
            used = (UINT64_C(1) << (vector->count - word_start)) - UINT64_C(1);
        }
        if (((vector->positive[index] | vector->negative[index]) & ~used) != 0U) {
            return NR_TERNARY_ERR_PADDING;
        }
    }
    return NR_TERNARY_OK;
}

nr_ternary_status nr_ternary_dot(const nr_ternary_vector *left,
                                 const nr_ternary_vector *right,
                                 int32_t *out)
{
    size_t index;
    int32_t dot = 0;
    nr_ternary_status status;
    if (left == NULL || right == NULL || out == NULL) {
        return NR_TERNARY_ERR_ARGUMENT;
    }
    *out = 0;
    status = nr_ternary_validate(left);
    if (status != NR_TERNARY_OK) {
        return status;
    }
    status = nr_ternary_validate(right);
    if (status != NR_TERNARY_OK) {
        return status;
    }
    if (left->count != right->count) {
        return NR_TERNARY_ERR_RANGE;
    }
    for (index = 0U; index < NR_TERNARY_WORDS; ++index) {
        unsigned int same = nr_popcount64(left->positive[index] & right->positive[index]);
        unsigned int opposite = nr_popcount64(left->positive[index] & right->negative[index]);
        same += nr_popcount64(left->negative[index] & right->negative[index]);
        opposite += nr_popcount64(left->negative[index] & right->positive[index]);
        dot += (int32_t)same - (int32_t)opposite;
    }
    *out = dot;
    return NR_TERNARY_OK;
}

nr_ternary_status nr_ternary_dot_sparse(const nr_ternary_vector *left,
                                        const nr_ternary_vector *right,
                                        int32_t *out)
{
    size_t word;
    int32_t dot = 0;
    nr_ternary_status status;
    if (left == NULL || right == NULL || out == NULL) return NR_TERNARY_ERR_ARGUMENT;
    *out = 0;
    status = nr_ternary_validate(left); if (status != NR_TERNARY_OK) return status;
    status = nr_ternary_validate(right); if (status != NR_TERNARY_OK) return status;
    if (left->count != right->count) return NR_TERNARY_ERR_RANGE;
    for (word = 0U; word < NR_TERNARY_WORDS; ++word) {
        uint64_t overlap = (left->positive[word] | left->negative[word]) &
                           (right->positive[word] | right->negative[word]);
        while (overlap != 0U) {
#if defined(__GNUC__) || defined(__clang__)
            unsigned int bit = (unsigned int)__builtin_ctzll((unsigned long long)overlap);
#else
            unsigned int bit = 0U; uint64_t probe = overlap;
            while ((probe & UINT64_C(1)) == 0U) { ++bit; probe >>= 1U; }
#endif
            uint64_t mask = UINT64_C(1) << bit;
            int same = ((left->positive[word] & right->positive[word] & mask) != 0U) ||
                       ((left->negative[word] & right->negative[word] & mask) != 0U);
            dot += same ? 1 : -1;
            overlap &= overlap - UINT64_C(1);
        }
    }
    *out = dot;
    return NR_TERNARY_OK;
}

nr_ternary_status nr_triadic_make(int64_t numerator,
                                  uint8_t exponent,
                                  nr_triadic *out)
{
    if (out == NULL) {
        return NR_TERNARY_ERR_ARGUMENT;
    }
    out->numerator = 0;
    out->exponent = 0U;
    if (exponent > NR_TRIADIC_MAX_EXPONENT) {
        return NR_TERNARY_ERR_RANGE;
    }
    if (numerator == 0) {
        return NR_TERNARY_OK;
    }
    while (exponent != 0U && numerator % INT64_C(3) == 0) {
        numerator /= INT64_C(3);
        --exponent;
    }
    out->numerator = numerator;
    out->exponent = exponent;
    return NR_TERNARY_OK;
}

nr_ternary_status nr_triadic_add(nr_triadic left,
                                 nr_triadic right,
                                 nr_triadic *out)
{
    uint8_t exponent;
    int64_t lhs;
    int64_t rhs;
    int64_t sum;
    if (out == NULL || left.exponent > NR_TRIADIC_MAX_EXPONENT ||
        right.exponent > NR_TRIADIC_MAX_EXPONENT) {
        return NR_TERNARY_ERR_ARGUMENT;
    }
    exponent = left.exponent > right.exponent ? left.exponent : right.exponent;
    if (!nr_scale_three(left.numerator, (uint8_t)(exponent - left.exponent), &lhs) ||
        !nr_scale_three(right.numerator, (uint8_t)(exponent - right.exponent), &rhs) ||
        !nr_add_i64(lhs, rhs, &sum)) {
        return NR_TERNARY_ERR_OVERFLOW;
    }
    return nr_triadic_make(sum, exponent, out);
}

nr_ternary_status nr_triadic_mul(nr_triadic left,
                                 nr_triadic right,
                                 nr_triadic *out)
{
    int64_t product;
    unsigned int exponent = (unsigned int)left.exponent + (unsigned int)right.exponent;
    if (out == NULL || exponent > NR_TRIADIC_MAX_EXPONENT) {
        return NR_TERNARY_ERR_RANGE;
    }
    if (!nr_mul_i64(left.numerator, right.numerator, &product)) {
        return NR_TERNARY_ERR_OVERFLOW;
    }
    return nr_triadic_make(product, (uint8_t)exponent, out);
}

nr_ternary_status nr_triadic_compare(nr_triadic left,
                                     nr_triadic right,
                                     int *out)
{
    uint8_t exponent;
    int64_t lhs;
    int64_t rhs;
    if (out == NULL || left.exponent > NR_TRIADIC_MAX_EXPONENT ||
        right.exponent > NR_TRIADIC_MAX_EXPONENT) {
        return NR_TERNARY_ERR_ARGUMENT;
    }
    *out = 0;
    exponent = left.exponent > right.exponent ? left.exponent : right.exponent;
    if (!nr_scale_three(left.numerator, (uint8_t)(exponent - left.exponent), &lhs) ||
        !nr_scale_three(right.numerator, (uint8_t)(exponent - right.exponent), &rhs)) {
        return NR_TERNARY_ERR_OVERFLOW;
    }
    *out = (lhs > rhs) - (lhs < rhs);
    return NR_TERNARY_OK;
}

nr_ternary_status nr_triadic_gate(nr_triadic evidence,
                                  nr_triadic reject_below,
                                  nr_triadic accept_at,
                                  nr_gate_status *out)
{
    int order;
    nr_ternary_status status;
    if (out == NULL) {
        return NR_TERNARY_ERR_ARGUMENT;
    }
    *out = NR_GATE_REJECT;
    status = nr_triadic_compare(reject_below, accept_at, &order);
    if (status != NR_TERNARY_OK) {
        return status;
    }
    if (order >= 0) {
        return NR_TERNARY_ERR_RANGE;
    }
    status = nr_triadic_compare(evidence, reject_below, &order);
    if (status != NR_TERNARY_OK) {
        return status;
    }
    if (order < 0) {
        *out = NR_GATE_REJECT;
        return NR_TERNARY_OK;
    }
    status = nr_triadic_compare(evidence, accept_at, &order);
    if (status != NR_TERNARY_OK) {
        return status;
    }
    *out = order >= 0 ? NR_GATE_ACCEPT : NR_GATE_ABSTAIN;
    return NR_TERNARY_OK;
}

const char *nr_ternary_status_string(nr_ternary_status status)
{
    switch (status) {
    case NR_TERNARY_OK: return "ok";
    case NR_TERNARY_ERR_ARGUMENT: return "invalid argument";
    case NR_TERNARY_ERR_TRIT: return "invalid trit or overlapping sign planes";
    case NR_TERNARY_ERR_PADDING: return "noncanonical ternary padding";
    case NR_TERNARY_ERR_OVERFLOW: return "exact arithmetic overflow";
    case NR_TERNARY_ERR_RANGE: return "value outside configured bounds";
    default: return "unknown ternary status";
    }
}
