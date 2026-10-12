#include "ternary_core.h"

#include <limits.h>
#include <stdio.h>

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        return 1; \
    } \
} while (0)

static int test_dot(void)
{
    static const int8_t left[] = {-1, 0, 1, 1, -1, 0, 1, -1, 1};
    static const int8_t right[] = {1, 0, 1, -1, -1, 1, 0, -1, 1};
    nr_ternary_vector a;
    nr_ternary_vector b;
    int32_t dot = 0;
    CHECK(nr_ternary_pack(left, sizeof(left), &a) == NR_TERNARY_OK);
    CHECK(nr_ternary_pack(right, sizeof(right), &b) == NR_TERNARY_OK);
    CHECK(nr_ternary_dot(&a, &b, &dot) == NR_TERNARY_OK);
    CHECK(dot == 2);
    { int32_t sparse_dot = 0; CHECK(nr_ternary_dot_sparse(&a, &b, &sparse_dot) == NR_TERNARY_OK); CHECK(sparse_dot == dot); }
    a.positive[3] = UINT64_C(1) << 63U;
    CHECK(nr_ternary_validate(&a) == NR_TERNARY_ERR_PADDING);
    return 0;
}

static int test_triadic(void)
{
    nr_triadic one_third;
    nr_triadic four_ninths;
    nr_triadic sum;
    nr_triadic product;
    nr_gate_status gate;
    int order = 0;
    CHECK(nr_triadic_make(3, 2U, &one_third) == NR_TERNARY_OK);
    CHECK(one_third.numerator == 1 && one_third.exponent == 1U);
    CHECK(nr_triadic_make(4, 2U, &four_ninths) == NR_TERNARY_OK);
    CHECK(nr_triadic_add(one_third, four_ninths, &sum) == NR_TERNARY_OK);
    CHECK(sum.numerator == 7 && sum.exponent == 2U);
    CHECK(nr_triadic_mul(one_third, four_ninths, &product) == NR_TERNARY_OK);
    CHECK(product.numerator == 4 && product.exponent == 3U);
    CHECK(nr_triadic_compare(one_third, four_ninths, &order) == NR_TERNARY_OK);
    CHECK(order < 0);
    CHECK(nr_triadic_gate((nr_triadic){0, 0U},
                          (nr_triadic){-1, 1U},
                          (nr_triadic){1, 1U}, &gate) == NR_TERNARY_OK);
    CHECK(gate == NR_GATE_ABSTAIN);
    CHECK(nr_triadic_mul((nr_triadic){INT64_MAX, 0U},
                         (nr_triadic){2, 0U}, &product) == NR_TERNARY_ERR_OVERFLOW);
    return 0;
}

int main(void)
{
    CHECK(nr_ternary_status_string(NR_TERNARY_OK) != NULL);
    CHECK(test_dot() == 0);
    CHECK(test_triadic() == 0);
    puts("exact ternary core tests: PASS");
    return 0;
}
