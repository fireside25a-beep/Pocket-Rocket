#ifndef NEURO_ROUTE_TERNARY_SSM_H
#define NEURO_ROUTE_TERNARY_SSM_H

#include <stddef.h>
#include <stdint.h>
#include "binary32.h"

#define NR_TERNARY_SSM_MAX_HIDDEN ((size_t)4096U)

typedef enum nr_ssm_status {
    NR_SSM_OK = 0,
    NR_SSM_ERR_ARGUMENT = 1,
    NR_SSM_ERR_RANGE = 2,
    NR_SSM_ERR_TRIT = 3,
    NR_SSM_ERR_OVERFLOW = 4
} nr_ssm_status;

/* Exact diagonal recurrence: state[i] = A[i]*state[i] + B[i]*input[i]. */
nr_ssm_status nr_ternary_ssm_step(int32_t *state, const int32_t *input,
                                  const int8_t *a, const int8_t *b,
                                  size_t hidden_dim);
/* The only numeric-plane boundary: exact int32->binary32 then reference mul/add. */
nr_ssm_status nr_ternary_ssm_project_binary32(const int32_t *state,
                                              const uint32_t *weights_binary32,
                                              size_t hidden_dim,
                                              uint32_t *output_binary32);
const char *nr_ssm_status_string(nr_ssm_status status);

#endif
