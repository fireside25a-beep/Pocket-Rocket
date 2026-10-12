#include "binary32.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "check failed at %s:%d: %s\n",                    \
                    __FILE__, __LINE__, #condition);                           \
            return EXIT_FAILURE;                                                \
        }                                                                       \
    } while (0)

typedef enum binary32_operation {
    NR_BINARY32_OP_ADD = 0,
    NR_BINARY32_OP_MUL = 1
} binary32_operation;

typedef struct binary32_vector {
    binary32_operation operation;
    uint32_t left;
    uint32_t right;
    uint32_t expected;
} binary32_vector;

/* Byte-identical cases from tests/data/binary32_vectors.json (v1). */
static const binary32_vector vectors[] = {
    {NR_BINARY32_OP_ADD, UINT32_C(0x7fa12345), UINT32_C(0x3f800000), UINT32_C(0x7fc00000)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xffa12345), UINT32_C(0x3f800000), UINT32_C(0x7fc00000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x7f800000), UINT32_C(0xff800000), UINT32_C(0x7fc00000)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x7f800000), UINT32_C(0x00000000), UINT32_C(0x7fc00000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x7f800000), UINT32_C(0x7f7fffff), UINT32_C(0x7f800000)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xff800000), UINT32_C(0xc0000000), UINT32_C(0x7f800000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x00000000), UINT32_C(0x80000000), UINT32_C(0x00000000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x80000000), UINT32_C(0x80000000), UINT32_C(0x80000000)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x00000000), UINT32_C(0x80000000), UINT32_C(0x80000000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x7f7fffff), UINT32_C(0x7f7fffff), UINT32_C(0x7f800000)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x7f7fffff), UINT32_C(0x40000000), UINT32_C(0x7f800000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x7f7fffff), UINT32_C(0xff7fffff), UINT32_C(0x00000000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x00800000), UINT32_C(0x807fffff), UINT32_C(0x00000001)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x00800000), UINT32_C(0x00800000), UINT32_C(0x01000000)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x00800000), UINT32_C(0x3f000000), UINT32_C(0x00400000)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x00000001), UINT32_C(0x3f000000), UINT32_C(0x00000000)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x80000001), UINT32_C(0x3f000000), UINT32_C(0x80000000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x3f800000), UINT32_C(0x33800000), UINT32_C(0x3f800000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x3f800000), UINT32_C(0x34400000), UINT32_C(0x3f800002)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x007fffff), UINT32_C(0x00000001), UINT32_C(0x00800000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x00000001), UINT32_C(0x00000001), UINT32_C(0x00000002)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x00000001), UINT32_C(0x00000001), UINT32_C(0x00000000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xf4f162c1), UINT32_C(0xc6d9e12d), UINT32_C(0xf4f162c1)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xa4b1e52e), UINT32_C(0x08873a2c), UINT32_C(0x80000000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x56f6f733), UINT32_C(0x0fe574a6), UINT32_C(0x56f6f733)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xaf99f18f), UINT32_C(0x0bf40553), UINT32_C(0x8000495f)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x83139f6c), UINT32_C(0x21c2f599), UINT32_C(0x21c2f599)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x8cde7353), UINT32_C(0x320b5e38), UINT32_C(0x801e469f)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xb224a763), UINT32_C(0x25fcd5b3), UINT32_C(0xb224a763)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xe7e49ce1), UINT32_C(0xa2ff1ebf), UINT32_C(0x4b63d3b9)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xa4da2da3), UINT32_C(0xbde6c361), UINT32_C(0xbde6c361)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x230a9614), UINT32_C(0xff5601ab), UINT32_C(0xe2e7b4b8)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xde863d04), UINT32_C(0x29fc27f6), UINT32_C(0xde863d04)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x25a1faa5), UINT32_C(0x855945ae), UINT32_C(0x80000000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xe6993778), UINT32_C(0x9109ff25), UINT32_C(0xe6993778)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x72d5a95b), UINT32_C(0x77eb11be), UINT32_C(0x7f800000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x13e21a61), UINT32_C(0xf0c76824), UINT32_C(0xf0c76824)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xa45fe98e), UINT32_C(0x492daab3), UINT32_C(0xae17e623)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xc58a0278), UINT32_C(0xed8ec6d0), UINT32_C(0xed8ec6d0)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xf6798843), UINT32_C(0x7b301caa), UINT32_C(0xff800000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x7d85de6e), UINT32_C(0x1991da22), UINT32_C(0x7d85de6e)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x19c35eaa), UINT32_C(0x984f4fe3), UINT32_C(0x80000000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x4b10cbb2), UINT32_C(0x11567a7d), UINT32_C(0x4b10cbb2)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x02920d68), UINT32_C(0x3a1d3a72), UINT32_C(0x000166ce)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xb36df909), UINT32_C(0xe31f5d8a), UINT32_C(0xe31f5d8a)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x1601d4e9), UINT32_C(0x13df79c0), UINT32_C(0x00000000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x12d65a1b), UINT32_C(0x88d5c4b7), UINT32_C(0x12d65a0e)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xbeeb2b5e), UINT32_C(0x15412b1c), UINT32_C(0x94b1734c)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x4195b33b), UINT32_C(0x2502c663), UINT32_C(0x4195b33b)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x110cdc32), UINT32_C(0x0eb4b4b1), UINT32_C(0x00000000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x94ae7822), UINT32_C(0xc6f300b1), UINT32_C(0xc6f300b1)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x2c4f5d03), UINT32_C(0x1b626094), UINT32_C(0x08375e57)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x0a210943), UINT32_C(0x8365170c), UINT32_C(0x0a2105af)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x8714dd6b), UINT32_C(0x69da6c55), UINT32_C(0xb17e0718)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x9c98ca86), UINT32_C(0x30838e1c), UINT32_C(0x30838e1c)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xeedd29ca), UINT32_C(0x73251342), UINT32_C(0xff800000)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x66b2f31c), UINT32_C(0x344d632d), UINT32_C(0x66b2f31c)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xc5b41cf9), UINT32_C(0x5f6e382c), UINT32_C(0xe5a79a75)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x7c0f6980), UINT32_C(0x4968346f), UINT32_C(0x7c0f6980)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x4a9a4350), UINT32_C(0x8f763311), UINT32_C(0x9a945b75)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xc2fbe581), UINT32_C(0x254980e6), UINT32_C(0xc2fbe581)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x289aedae), UINT32_C(0xe5fc46e7), UINT32_C(0xcf18ace0)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xeeab7a24), UINT32_C(0x7ce1ea12), UINT32_C(0x7ce1ea12)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x59a35626), UINT32_C(0x554b8756), UINT32_C(0x6f81dba9)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xccff4d99), UINT32_C(0x6b232d0a), UINT32_C(0x6b232d0a)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xb04ad04b), UINT32_C(0x22f2873c), UINT32_C(0x93c0240a)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xfc7fe78e), UINT32_C(0x24e66c51), UINT32_C(0xfc7fe78e)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xac09175a), UINT32_C(0xe2c0434e), UINT32_C(0x4f4deb1d)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x85cdad75), UINT32_C(0xae9c9f29), UINT32_C(0xae9c9f29)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x839e7569), UINT32_C(0x5e260a26), UINT32_C(0xa24d8cd4)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x772884f5), UINT32_C(0x957cb496), UINT32_C(0x772884f5)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xaebdc308), UINT32_C(0x42cfdb64), UINT32_C(0xb21a1353)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xac501dc9), UINT32_C(0x06c19b6c), UINT32_C(0xac501dc9)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x202d4ef9), UINT32_C(0x70981cac), UINT32_C(0x514df49a)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x6a79bc31), UINT32_C(0xc84885d0), UINT32_C(0x6a79bc31)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x6649f9f2), UINT32_C(0xa44b6758), UINT32_C(0xcb207abc)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xb2c6f555), UINT32_C(0xb2d981d5), UINT32_C(0xb3503b95)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xe2103647), UINT32_C(0x53fe5c22), UINT32_C(0xf68f49c1)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x943235c9), UINT32_C(0xa02794c5), UINT32_C(0xa02794c6)},
    {NR_BINARY32_OP_MUL, UINT32_C(0xa738ad92), UINT32_C(0x0dc0116f), UINT32_C(0x80000002)},
    {NR_BINARY32_OP_ADD, UINT32_C(0x8098ac14), UINT32_C(0xc7076ca0), UINT32_C(0xc7076ca0)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x36917e13), UINT32_C(0xe8790e58), UINT32_C(0xdf8d8bc7)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xead1fef2), UINT32_C(0x8a06b955), UINT32_C(0xead1fef2)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x336e1ef1), UINT32_C(0xf20ac2d8), UINT32_C(0xe60111ea)},
    {NR_BINARY32_OP_ADD, UINT32_C(0xdd9c76ad), UINT32_C(0xb42c492e), UINT32_C(0xdd9c76ad)},
    {NR_BINARY32_OP_MUL, UINT32_C(0x80963413), UINT32_C(0x6f2d9169), UINT32_C(0xb04bad04)}
};

static uint32_t reference_for(binary32_vector vector)
{
    return vector.operation == NR_BINARY32_OP_MUL
        ? nr_binary32_mul_reference(vector.left, vector.right)
        : nr_binary32_add_reference(vector.left, vector.right);
}

static uint32_t fast_for(binary32_vector vector, nr_binary32_stats *stats)
{
    return vector.operation == NR_BINARY32_OP_MUL
        ? nr_binary32_mul_fast(vector.left, vector.right, stats)
        : nr_binary32_add_fast(vector.left, vector.right, stats);
}

int main(void)
{
    nr_binary32_stats stats;
    size_t index;
    size_t add_count = 0U;
    size_t mul_count = 0U;
    int x87_gate;
    const char *x87_reason;

    nr_binary32_stats_reset(&stats);
    nr_binary32_stats_reset(NULL);
    for (index = 0U; index < sizeof(vectors) / sizeof(vectors[0]); ++index) {
        uint32_t reference = reference_for(vectors[index]);
        uint32_t fast = fast_for(vectors[index], &stats);
        CHECK(reference == vectors[index].expected);
        CHECK(fast == vectors[index].expected);
        if (vectors[index].operation == NR_BINARY32_OP_MUL) {
            ++mul_count;
        } else {
            ++add_count;
        }
    }
    CHECK(stats.add_calls == (uint64_t)add_count);
    CHECK(stats.mul_calls == (uint64_t)mul_count);
    CHECK(stats.hardware_candidates == (uint64_t)(add_count + mul_count));
    CHECK(stats.candidate_mismatches == 0U);
    CHECK(stats.reference_fallbacks == 0U);

    x87_gate = nr_binary32_x87_conformance_gate();
    x87_reason = nr_binary32_x87_gate_reason();
    CHECK(x87_reason != NULL);
    printf("binary32 x87 gate: %s\n", x87_reason);
    nr_binary32_stats_reset(&stats);
    for (index = 0U; index < sizeof(vectors) / sizeof(vectors[0]); ++index) {
        uint32_t result = vectors[index].operation == NR_BINARY32_OP_MUL
            ? nr_binary32_mul_x87_fast(vectors[index].left, vectors[index].right, &stats)
            : nr_binary32_add_x87_fast(vectors[index].left, vectors[index].right, &stats);
        CHECK(result == vectors[index].expected);
    }
    if (x87_gate) {
        CHECK(stats.hardware_candidates == (uint64_t)(add_count + mul_count));
        CHECK(stats.candidate_mismatches == 0U);
    } else {
        CHECK(stats.hardware_candidates == 0U);
        CHECK(stats.reference_fallbacks == (uint64_t)(add_count + mul_count));
    }

    nr_binary32_stats_reset(&stats);
    CHECK(nr_binary32_add_checked(UINT32_C(0x3f800000), UINT32_C(0x3f800000),
                                  UINT32_C(0), &stats) == UINT32_C(0x40000000));
    CHECK(nr_binary32_mul_checked(UINT32_C(0x3f800000), UINT32_C(0x3f800000),
                                  UINT32_C(0), &stats) == UINT32_C(0x3f800000));
    CHECK(stats.add_calls == 1U);
    CHECK(stats.mul_calls == 1U);
    CHECK(stats.hardware_candidates == 2U);
    CHECK(stats.candidate_mismatches == 2U);
    CHECK(stats.reference_fallbacks == 2U);

    nr_binary32_stats_reset(&stats);
    CHECK(nr_binary32_add_checked(UINT32_C(0x7fa00001), UINT32_C(0x3f800000),
                                  NR_BINARY32_CANONICAL_NAN, &stats) ==
          NR_BINARY32_CANONICAL_NAN);
    CHECK(stats.candidate_mismatches == 0U);
    CHECK(nr_binary32_from_int32_reference(0) == UINT32_C(0x00000000));
    CHECK(nr_binary32_from_int32_reference(1) == UINT32_C(0x3f800000));
    CHECK(nr_binary32_from_int32_reference(-1) == UINT32_C(0xbf800000));
    CHECK(nr_binary32_set_mode(NR_BINARY32_MODE_EXACT) == 1);
    nr_binary32_stats_reset(&stats);
    CHECK(stats.mode == NR_BINARY32_MODE_EXACT);
    CHECK(nr_binary32_add_fast(UINT32_C(0x3f800000), UINT32_C(0x40000000), &stats) == UINT32_C(0x40400000));
    CHECK(stats.exact_mode_calls == 1U);
    CHECK(stats.hardware_candidates == 0U);
    CHECK(nr_binary32_set_mode(NR_BINARY32_MODE_HARDWARE) == 1);
    nr_binary32_stats_reset(&stats);
    CHECK(stats.mode == NR_BINARY32_MODE_HARDWARE);
    puts("binary32 tests: ok");
    return EXIT_SUCCESS;
}
