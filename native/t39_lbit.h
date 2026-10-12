#ifndef NEURO_ROUTE_T39_LBIT_H
#define NEURO_ROUTE_T39_LBIT_H

/* Exact balanced-ternary validation bridge for the Lbit control plane. */

#include <stdint.h>

#define NR_T39_TRITS 39U
#define NR_T39_PACKED_BYTES 8U
#define NR_T39_MAX INT64_C(2026277576509488133)

typedef enum nr_t39_status {
    NR_T39_OK = 0,
    NR_T39_ERR_ARGUMENT = 1,
    NR_T39_ERR_RANGE = 2,
    NR_T39_ERR_OVERFLOW = 3,
    NR_T39_ERR_NONCANONICAL = 4
} nr_t39_status;

typedef struct nr_t39 {
    int64_t value;
} nr_t39;

typedef enum nr_lbit_collapse_decision {
    NR_LBIT_COLLAPSE_REJECT = -1,
    NR_LBIT_COLLAPSE_RECURSE = 0,
    NR_LBIT_COLLAPSE_ALLOW = 1
} nr_lbit_collapse_decision;

/* Construction and checked arithmetic never return an out-of-range T39. */
nr_t39_status nr_t39_from_i64(int64_t value, nr_t39 *out);
nr_t39_status nr_t39_add(nr_t39 left, nr_t39 right, nr_t39 *out);
nr_t39_status nr_t39_sub(nr_t39 left, nr_t39 right, nr_t39 *out);
nr_t39_status nr_t39_mul(nr_t39 left, nr_t39 right, nr_t39 *out);
nr_t39_status nr_t39_negate(nr_t39 value, nr_t39 *out);

/* Trit order and packed octet order are both least-significant first. */
nr_t39_status nr_t39_from_trits(const int8_t trits[NR_T39_TRITS], nr_t39 *out);
nr_t39_status nr_t39_to_trits(nr_t39 value, int8_t trits[NR_T39_TRITS]);
nr_t39_status nr_t39_pack(nr_t39 value, uint8_t packed[NR_T39_PACKED_BYTES]);
nr_t39_status nr_t39_unpack(const uint8_t packed[NR_T39_PACKED_BYTES], nr_t39 *out);

/*
 * Produce one canonical T39 validation token for an existing Lbit route.
 *
 * Trits 0..5 commit (256 - Hamming distance), trits 6..11 commit the
 * negative stable rank, and trits 12..15 commit the omission-certificate,
 * coupling-closure, resident-budget, and registry-integrity decisions.
 * Each decision must be exactly -1, 0, or +1. The result is REJECT when any
 * decision is -1, RECURSE when none is -1 but at least one is 0, and ALLOW
 * only when all four are +1. Invalid input leaves a reject result.
 */
nr_t39_status nr_t39_lbit_validate(uint16_t hamming_distance,
                                   uint16_t stable_rank,
                                   int8_t omission_decision,
                                   int8_t coupling_decision,
                                   int8_t budget_decision,
                                   int8_t integrity_decision,
                                   nr_t39 *token,
                                   nr_lbit_collapse_decision *decision);

const char *nr_t39_status_string(nr_t39_status status);

#endif
