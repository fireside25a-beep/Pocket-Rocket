#ifndef NEURO_ROUTE_BINARY32_H
#define NEURO_ROUTE_BINARY32_H

/* Bit-exact IEEE-754 binary32 add/multiply contract. */

#include <stdint.h>

#define NR_BINARY32_CANONICAL_NAN UINT32_C(0x7fc00000)

typedef enum nr_binary32_mode {
    NR_BINARY32_MODE_EXACT = 0,
    NR_BINARY32_MODE_HARDWARE = 1
} nr_binary32_mode;

typedef struct nr_binary32_stats {
    uint64_t add_calls;
    uint64_t mul_calls;
    uint64_t hardware_candidates;
    uint64_t candidate_mismatches;
    uint64_t reference_fallbacks;
    uint64_t exact_mode_calls;
    nr_binary32_mode mode;
} nr_binary32_stats;

void nr_binary32_stats_reset(nr_binary32_stats *stats);
int nr_binary32_set_mode(nr_binary32_mode mode);
nr_binary32_mode nr_binary32_get_mode(void);

/* The integer-only conformance reference. */
uint32_t nr_binary32_add_reference(uint32_t left, uint32_t right);
uint32_t nr_binary32_mul_reference(uint32_t left, uint32_t right);
uint32_t nr_binary32_from_int32_reference(int32_t value);

/* Compare a candidate with the reference and fail closed on disagreement. */
uint32_t nr_binary32_add_checked(uint32_t left,
                                 uint32_t right,
                                 uint32_t candidate,
                                 nr_binary32_stats *stats);
uint32_t nr_binary32_mul_checked(uint32_t left,
                                 uint32_t right,
                                 uint32_t candidate,
                                 nr_binary32_stats *stats);

/* Hardware candidates are accepted only when their bits match the reference. */
uint32_t nr_binary32_add_fast(uint32_t left,
                              uint32_t right,
                              nr_binary32_stats *stats);
uint32_t nr_binary32_mul_fast(uint32_t left,
                              uint32_t right,
                              nr_binary32_stats *stats);

/*
 * Optional x87 candidate.  The candidate is never enabled merely because
 * the compiler targets x86: it must pass the built-in edge-vector gate under
 * round-to-nearest.  A failed gate returns a concrete reason and the fast
 * entry points use the integer reference without counting a hardware hit.
 */
int nr_binary32_x87_conformance_gate(void);
const char *nr_binary32_x87_gate_reason(void);
uint32_t nr_binary32_add_x87_fast(uint32_t left,
                                  uint32_t right,
                                  nr_binary32_stats *stats);
uint32_t nr_binary32_mul_x87_fast(uint32_t left,
                                  uint32_t right,
                                  nr_binary32_stats *stats);

#endif
