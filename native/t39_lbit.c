#include "t39_lbit.h"

#include <stddef.h>

#define NR_T39_RADIX UINT64_C(3)
#define NR_T39_CODE_LIMIT UINT64_C(4052555153018976267)

static int nr_t39_valid(nr_t39 value)
{
    return value.value >= -NR_T39_MAX && value.value <= NR_T39_MAX;
}

static uint64_t nr_t39_magnitude(int64_t value)
{
    return value < 0 ? (uint64_t)(-value) : (uint64_t)value;
}

nr_t39_status nr_t39_from_i64(int64_t value, nr_t39 *out)
{
    if (out == NULL) {
        return NR_T39_ERR_ARGUMENT;
    }
    out->value = 0;
    if (value < -NR_T39_MAX || value > NR_T39_MAX) {
        return NR_T39_ERR_RANGE;
    }
    out->value = value;
    return NR_T39_OK;
}

nr_t39_status nr_t39_add(nr_t39 left, nr_t39 right, nr_t39 *out)
{
    int64_t sum;
    if (out == NULL) {
        return NR_T39_ERR_ARGUMENT;
    }
    out->value = 0;
    if (!nr_t39_valid(left) || !nr_t39_valid(right)) {
        return NR_T39_ERR_RANGE;
    }
    /* The largest intermediate is 2 * NR_T39_MAX, below INT64_MAX. */
    sum = left.value + right.value;
    if (sum < -NR_T39_MAX || sum > NR_T39_MAX) {
        return NR_T39_ERR_OVERFLOW;
    }
    out->value = sum;
    return NR_T39_OK;
}

nr_t39_status nr_t39_sub(nr_t39 left, nr_t39 right, nr_t39 *out)
{
    int64_t difference;
    if (out == NULL) {
        return NR_T39_ERR_ARGUMENT;
    }
    out->value = 0;
    if (!nr_t39_valid(left) || !nr_t39_valid(right)) {
        return NR_T39_ERR_RANGE;
    }
    difference = left.value - right.value;
    if (difference < -NR_T39_MAX || difference > NR_T39_MAX) {
        return NR_T39_ERR_OVERFLOW;
    }
    out->value = difference;
    return NR_T39_OK;
}

nr_t39_status nr_t39_mul(nr_t39 left, nr_t39 right, nr_t39 *out)
{
    uint64_t left_magnitude;
    uint64_t right_magnitude;
    uint64_t product;
    int negative;
    if (out == NULL) {
        return NR_T39_ERR_ARGUMENT;
    }
    out->value = 0;
    if (!nr_t39_valid(left) || !nr_t39_valid(right)) {
        return NR_T39_ERR_RANGE;
    }
    left_magnitude = nr_t39_magnitude(left.value);
    right_magnitude = nr_t39_magnitude(right.value);
    if (left_magnitude != 0U && right_magnitude > (uint64_t)NR_T39_MAX / left_magnitude) {
        return NR_T39_ERR_OVERFLOW;
    }
    product = left_magnitude * right_magnitude;
    negative = (left.value < 0) != (right.value < 0);
    out->value = negative ? -(int64_t)product : (int64_t)product;
    return NR_T39_OK;
}

nr_t39_status nr_t39_negate(nr_t39 value, nr_t39 *out)
{
    if (out == NULL) {
        return NR_T39_ERR_ARGUMENT;
    }
    out->value = 0;
    if (!nr_t39_valid(value)) {
        return NR_T39_ERR_RANGE;
    }
    out->value = -value.value;
    return NR_T39_OK;
}

nr_t39_status nr_t39_from_trits(const int8_t trits[NR_T39_TRITS], nr_t39 *out)
{
    uint64_t code = 0U;
    uint64_t place = 1U;
    size_t index;
    uint8_t packed[NR_T39_PACKED_BYTES];
    if (out == NULL || trits == NULL) {
        if (out != NULL) {
            out->value = 0;
        }
        return NR_T39_ERR_ARGUMENT;
    }
    out->value = 0;
    for (index = 0U; index < NR_T39_TRITS; ++index) {
        uint64_t digit;
        if (trits[index] < -1 || trits[index] > 1) {
            return NR_T39_ERR_NONCANONICAL;
        }
        digit = (uint64_t)(trits[index] + 1);
        code += digit * place;
        if (index + 1U < NR_T39_TRITS) {
            place *= NR_T39_RADIX;
        }
    }
    for (index = 0U; index < NR_T39_PACKED_BYTES; ++index) {
        packed[index] = (uint8_t)(code & UINT64_C(0xff));
        code >>= 8U;
    }
    return nr_t39_unpack(packed, out);
}

nr_t39_status nr_t39_to_trits(nr_t39 value, int8_t trits[NR_T39_TRITS])
{
    uint64_t code;
    size_t index;
    if (trits == NULL) {
        return NR_T39_ERR_ARGUMENT;
    }
    for (index = 0U; index < NR_T39_TRITS; ++index) {
        trits[index] = 0;
    }
    if (!nr_t39_valid(value)) {
        return NR_T39_ERR_RANGE;
    }
    /* Offset [-NR_T39_MAX,+NR_T39_MAX] into [0,3^39), then decode base-3
     * digits 0,1,2 canonically as balanced trits -1,0,+1. */
    code = (uint64_t)(value.value + NR_T39_MAX);
    for (index = 0U; index < NR_T39_TRITS; ++index) {
        trits[index] = (int8_t)(code % NR_T39_RADIX) - 1;
        code /= NR_T39_RADIX;
    }
    return code == 0U ? NR_T39_OK : NR_T39_ERR_NONCANONICAL;
}

nr_t39_status nr_t39_pack(nr_t39 value, uint8_t packed[NR_T39_PACKED_BYTES])
{
    uint64_t code;
    size_t index;
    if (packed == NULL) {
        return NR_T39_ERR_ARGUMENT;
    }
    for (index = 0U; index < NR_T39_PACKED_BYTES; ++index) {
        packed[index] = 0U;
    }
    if (!nr_t39_valid(value)) {
        return NR_T39_ERR_RANGE;
    }
    code = (uint64_t)(value.value + NR_T39_MAX);
    for (index = 0U; index < NR_T39_PACKED_BYTES; ++index) {
        packed[index] = (uint8_t)(code & UINT64_C(0xff));
        code >>= 8U;
    }
    return NR_T39_OK;
}

nr_t39_status nr_t39_unpack(const uint8_t packed[NR_T39_PACKED_BYTES], nr_t39 *out)
{
    uint64_t code = 0U;
    size_t index;
    if (packed == NULL || out == NULL) {
        if (out != NULL) {
            out->value = 0;
        }
        return NR_T39_ERR_ARGUMENT;
    }
    out->value = 0;
    for (index = NR_T39_PACKED_BYTES; index > 0U; --index) {
        code = (code << 8U) | (uint64_t)packed[index - 1U];
    }
    if (code >= NR_T39_CODE_LIMIT) {
        return NR_T39_ERR_NONCANONICAL;
    }
    if (code >= (uint64_t)NR_T39_MAX) {
        out->value = (int64_t)(code - (uint64_t)NR_T39_MAX);
    } else {
        out->value = -(int64_t)((uint64_t)NR_T39_MAX - code);
    }
    return NR_T39_OK;
}

static nr_t39_status nr_t39_write_balanced_field(int64_t value,
                                                  size_t offset,
                                                  size_t width,
                                                  int8_t trits[NR_T39_TRITS])
{
    size_t index;
    for (index = 0U; index < width; ++index) {
        int64_t remainder = value % INT64_C(3);
        value /= INT64_C(3);
        if (remainder == INT64_C(2)) {
            remainder = -INT64_C(1);
            ++value;
        } else if (remainder == -INT64_C(2)) {
            remainder = INT64_C(1);
            --value;
        }
        trits[offset + index] = (int8_t)remainder;
    }
    return value == 0 ? NR_T39_OK : NR_T39_ERR_OVERFLOW;
}

static int nr_t39_decision_valid(int8_t decision)
{
    return decision >= -1 && decision <= 1;
}

nr_t39_status nr_t39_lbit_validate(uint16_t hamming_distance,
                                   uint16_t stable_rank,
                                   int8_t omission_decision,
                                   int8_t coupling_decision,
                                   int8_t budget_decision,
                                   int8_t integrity_decision,
                                   nr_t39 *token,
                                   nr_lbit_collapse_decision *decision)
{
    int8_t trits[NR_T39_TRITS] = {0};
    nr_t39_status status;
    if (token == NULL || decision == NULL) {
        if (token != NULL) {
            token->value = 0;
        }
        if (decision != NULL) {
            *decision = NR_LBIT_COLLAPSE_REJECT;
        }
        return NR_T39_ERR_ARGUMENT;
    }
    token->value = 0;
    *decision = NR_LBIT_COLLAPSE_REJECT;
    if (hamming_distance > 256U || stable_rank > 255U ||
        !nr_t39_decision_valid(omission_decision) ||
        !nr_t39_decision_valid(coupling_decision) ||
        !nr_t39_decision_valid(budget_decision) ||
        !nr_t39_decision_valid(integrity_decision)) {
        return NR_T39_ERR_RANGE;
    }
    status = nr_t39_write_balanced_field(INT64_C(256) - (int64_t)hamming_distance,
                                         0U, 6U, trits);
    if (status != NR_T39_OK) {
        return status;
    }
    status = nr_t39_write_balanced_field(-(int64_t)stable_rank, 6U, 6U, trits);
    if (status != NR_T39_OK) {
        return status;
    }
    trits[12] = omission_decision;
    trits[13] = coupling_decision;
    trits[14] = budget_decision;
    trits[15] = integrity_decision;
    status = nr_t39_from_trits(trits, token);
    if (status != NR_T39_OK) {
        token->value = 0;
        return status;
    }
    if (omission_decision == 1 && coupling_decision == 1 &&
        budget_decision == 1 && integrity_decision == 1) {
        *decision = NR_LBIT_COLLAPSE_ALLOW;
    } else if (omission_decision >= 0 && coupling_decision >= 0 &&
               budget_decision >= 0 && integrity_decision >= 0) {
        *decision = NR_LBIT_COLLAPSE_RECURSE;
    }
    return NR_T39_OK;
}

const char *nr_t39_status_string(nr_t39_status status)
{
    switch (status) {
    case NR_T39_OK:
        return "ok";
    case NR_T39_ERR_ARGUMENT:
        return "invalid argument";
    case NR_T39_ERR_RANGE:
        return "out of range";
    case NR_T39_ERR_OVERFLOW:
        return "arithmetic overflow";
    case NR_T39_ERR_NONCANONICAL:
        return "noncanonical ternary encoding";
    default:
        return "unknown status";
    }
}
