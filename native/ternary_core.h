#ifndef NEURO_ROUTE_TERNARY_CORE_H
#define NEURO_ROUTE_TERNARY_CORE_H

/* Exact bounded triadic arithmetic and direct ternary sign-plane kernels. */

#include <stddef.h>
#include <stdint.h>

#define NR_TERNARY_MAX_TRITS ((size_t)256U)
#define NR_TERNARY_WORDS ((size_t)4U)
#define NR_TRIADIC_MAX_EXPONENT ((uint8_t)39U)

typedef enum nr_ternary_status {
    NR_TERNARY_OK = 0,
    NR_TERNARY_ERR_ARGUMENT = 1,
    NR_TERNARY_ERR_TRIT = 2,
    NR_TERNARY_ERR_PADDING = 3,
    NR_TERNARY_ERR_OVERFLOW = 4,
    NR_TERNARY_ERR_RANGE = 5
} nr_ternary_status;

typedef struct nr_ternary_vector {
    uint64_t positive[NR_TERNARY_WORDS];
    uint64_t negative[NR_TERNARY_WORDS];
    size_t count;
} nr_ternary_vector;

typedef struct nr_triadic {
    int64_t numerator;
    uint8_t exponent;
} nr_triadic;

typedef enum nr_gate_status {
    NR_GATE_REJECT = -1,
    NR_GATE_ABSTAIN = 0,
    NR_GATE_ACCEPT = 1
} nr_gate_status;

nr_ternary_status nr_ternary_pack(const int8_t *trits,
                                  size_t count,
                                  nr_ternary_vector *out);
nr_ternary_status nr_ternary_validate(const nr_ternary_vector *vector);
nr_ternary_status nr_ternary_dot(const nr_ternary_vector *left,
                                 const nr_ternary_vector *right,
                                 int32_t *out);
/* Explicit event-driven reference path. It is not auto-dispatched and is not
 * claimed to outperform dense popcount on general-purpose CPUs. */
nr_ternary_status nr_ternary_dot_sparse(const nr_ternary_vector *left,
                                        const nr_ternary_vector *right,
                                        int32_t *out);

nr_ternary_status nr_triadic_make(int64_t numerator,
                                  uint8_t exponent,
                                  nr_triadic *out);
nr_ternary_status nr_triadic_add(nr_triadic left,
                                 nr_triadic right,
                                 nr_triadic *out);
nr_ternary_status nr_triadic_mul(nr_triadic left,
                                 nr_triadic right,
                                 nr_triadic *out);
nr_ternary_status nr_triadic_compare(nr_triadic left,
                                     nr_triadic right,
                                     int *out);
nr_ternary_status nr_triadic_gate(nr_triadic evidence,
                                  nr_triadic reject_below,
                                  nr_triadic accept_at,
                                  nr_gate_status *out);

const char *nr_ternary_status_string(nr_ternary_status status);

#endif
