#ifndef NEURO_ROUTE_TERNARY_TCAM_H
#define NEURO_ROUTE_TERNARY_TCAM_H

#include <stddef.h>
#include <stdint.h>
#include "ternary_core.h"

#define NR_TCAM_MAX_ENTRIES ((size_t)65536U)

typedef enum nr_tcam_status {
    NR_TCAM_OK = 0,
    NR_TCAM_NOT_FOUND = 1,
    NR_TCAM_ERR_ARGUMENT = 2,
    NR_TCAM_ERR_RANGE = 3,
    NR_TCAM_ERR_VECTOR = 4,
    NR_TCAM_ERR_UNAVAILABLE = 5
} nr_tcam_status;

/* Fixed-width per-entry comparison is O(1); the software table scan is O(n). */
nr_tcam_status nr_tcam_lookup(const nr_ternary_vector *query,
                              const nr_ternary_vector *table,
                              size_t count,
                              size_t *best_index,
                              int32_t *best_score);
nr_tcam_status nr_tcam_exact_match(const nr_ternary_vector *query,
                                   const nr_ternary_vector *table,
                                   size_t count,
                                   size_t *index);
/* Explicit optional accelerator. Never auto-dispatched. */
nr_tcam_status nr_tcam_lookup_avx2(const nr_ternary_vector *query,
                                   const nr_ternary_vector *table,
                                   size_t count,
                                   size_t *best_index,
                                   int32_t *best_score);
const char *nr_tcam_status_string(nr_tcam_status status);

#endif
