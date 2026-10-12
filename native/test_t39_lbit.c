#include "t39_lbit.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "check failed at %s:%d: %s\n",                    \
                    __FILE__, __LINE__, #condition);                           \
            return EXIT_FAILURE;                                                \
        }                                                                       \
    } while (0)

static int check_round_trip(int64_t input)
{
    nr_t39 value;
    nr_t39 decoded;
    int8_t trits[NR_T39_TRITS];
    uint8_t packed[NR_T39_PACKED_BYTES];
    if (nr_t39_from_i64(input, &value) != NR_T39_OK ||
        nr_t39_pack(value, packed) != NR_T39_OK ||
        nr_t39_unpack(packed, &decoded) != NR_T39_OK ||
        decoded.value != input ||
        nr_t39_to_trits(value, trits) != NR_T39_OK ||
        nr_t39_from_trits(trits, &decoded) != NR_T39_OK ||
        decoded.value != input) {
        return 0;
    }
    return 1;
}

int main(void)
{
    static const uint8_t zero_packed[NR_T39_PACKED_BYTES] = {
        0x05U, 0xfcU, 0x2fU, 0x5cU, 0xb8U, 0xc8U, 0x1eU, 0x1cU
    };
    static const uint8_t max_packed[NR_T39_PACKED_BYTES] = {
        0x0aU, 0xf8U, 0x5fU, 0xb8U, 0x70U, 0x91U, 0x3dU, 0x38U
    };
    static const uint8_t noncanonical[NR_T39_PACKED_BYTES] = {
        0x0bU, 0xf8U, 0x5fU, 0xb8U, 0x70U, 0x91U, 0x3dU, 0x38U
    };
    nr_t39 zero;
    nr_t39 one;
    nr_t39 maximum;
    nr_t39 minimum;
    nr_t39 result;
    nr_lbit_collapse_decision decision;
    uint8_t packed[NR_T39_PACKED_BYTES];
    int8_t trits[NR_T39_TRITS] = {0};
    uint64_t state = UINT64_C(0x9e3779b97f4a7c15);
    size_t index;

    CHECK(nr_t39_from_i64(0, &zero) == NR_T39_OK);
    CHECK(nr_t39_from_i64(1, &one) == NR_T39_OK);
    CHECK(nr_t39_from_i64(NR_T39_MAX, &maximum) == NR_T39_OK);
    CHECK(nr_t39_from_i64(-NR_T39_MAX, &minimum) == NR_T39_OK);
    CHECK(nr_t39_from_i64(NR_T39_MAX + INT64_C(1), &result) == NR_T39_ERR_RANGE);
    CHECK(result.value == 0);
    CHECK(nr_t39_from_i64(-NR_T39_MAX - INT64_C(1), &result) == NR_T39_ERR_RANGE);
    CHECK(result.value == 0);

    CHECK(nr_t39_pack(zero, packed) == NR_T39_OK);
    CHECK(memcmp(packed, zero_packed, sizeof(packed)) == 0);
    CHECK(nr_t39_pack(maximum, packed) == NR_T39_OK);
    CHECK(memcmp(packed, max_packed, sizeof(packed)) == 0);
    CHECK(nr_t39_pack(minimum, packed) == NR_T39_OK);
    CHECK(memcmp(packed, (uint8_t[NR_T39_PACKED_BYTES]){0}, sizeof(packed)) == 0);
    CHECK(nr_t39_unpack(noncanonical, &result) == NR_T39_ERR_NONCANONICAL);
    CHECK(result.value == 0);

    CHECK(nr_t39_add(maximum, one, &result) == NR_T39_ERR_OVERFLOW);
    CHECK(result.value == 0);
    CHECK(nr_t39_sub(minimum, one, &result) == NR_T39_ERR_OVERFLOW);
    CHECK(result.value == 0);
    CHECK(nr_t39_mul(maximum, one, &result) == NR_T39_OK);
    CHECK(result.value == NR_T39_MAX);
    CHECK(nr_t39_mul(maximum, (nr_t39){2}, &result) == NR_T39_ERR_OVERFLOW);
    CHECK(result.value == 0);
    CHECK(nr_t39_mul((nr_t39){-3}, (nr_t39){7}, &result) == NR_T39_OK);
    CHECK(result.value == -21);
    CHECK(nr_t39_negate(minimum, &result) == NR_T39_OK);
    CHECK(result.value == NR_T39_MAX);
    CHECK(nr_t39_add((nr_t39){NR_T39_MAX + INT64_C(1)}, zero, &result) == NR_T39_ERR_RANGE);

    trits[38] = 1;
    CHECK(nr_t39_from_trits(trits, &result) == NR_T39_OK);
    CHECK(result.value == INT64_C(1350851717672992089));
    trits[7] = 2;
    CHECK(nr_t39_from_trits(trits, &result) == NR_T39_ERR_NONCANONICAL);
    CHECK(result.value == 0);

    CHECK(check_round_trip(-NR_T39_MAX));
    CHECK(check_round_trip(-1));
    CHECK(check_round_trip(0));
    CHECK(check_round_trip(1));
    CHECK(check_round_trip(NR_T39_MAX));
    for (index = 0U; index < 10000U; ++index) {
        int64_t sample;
        state = state * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
        sample = (int64_t)(state % UINT64_C(4052555153018976267)) - NR_T39_MAX;
        CHECK(check_round_trip(sample));
    }

    CHECK(nr_t39_lbit_validate(0U, 0U, 1, 1, 1, 1, &result, &decision) == NR_T39_OK);
    CHECK(decision == NR_LBIT_COLLAPSE_ALLOW);
    CHECK(result.value == INT64_C(21257896));
    CHECK(nr_t39_lbit_validate(17U, 9U, 1, -1, 1, 1, &result, &decision) == NR_T39_OK);
    CHECK(decision == NR_LBIT_COLLAPSE_REJECT);
    CHECK(nr_t39_lbit_validate(17U, 9U, 1, 0, 1, 1, &result, &decision) == NR_T39_OK);
    CHECK(decision == NR_LBIT_COLLAPSE_RECURSE);
    CHECK(nr_t39_lbit_validate(17U, 9U, 0, 0, 0, 0, &result, &decision) == NR_T39_OK);
    CHECK(decision == NR_LBIT_COLLAPSE_RECURSE);
    CHECK(nr_t39_lbit_validate(257U, 0U, 1, 1, 1, 1, &result, &decision) == NR_T39_ERR_RANGE);
    CHECK(result.value == 0);
    CHECK(decision == NR_LBIT_COLLAPSE_REJECT);
    CHECK(nr_t39_lbit_validate(0U, 256U, 1, 1, 1, 1, &result, &decision) == NR_T39_ERR_RANGE);
    CHECK(nr_t39_lbit_validate(0U, 0U, 2, 1, 1, 1, &result, &decision) == NR_T39_ERR_RANGE);
    CHECK(decision == NR_LBIT_COLLAPSE_REJECT);
    CHECK(strcmp(nr_t39_status_string(NR_T39_ERR_NONCANONICAL),
                 "noncanonical ternary encoding") == 0);
    CHECK(strcmp(nr_t39_status_string((nr_t39_status)99), "unknown status") == 0);

    puts("T39 Lbit bridge tests: ok");
    return EXIT_SUCCESS;
}
