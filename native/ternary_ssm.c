#include "ternary_ssm.h"
#include <limits.h>

static int valid_trit(int8_t value) { return value >= -1 && value <= 1; }

nr_ssm_status nr_ternary_ssm_step(int32_t *state, const int32_t *input,
                                  const int8_t *a, const int8_t *b,
                                  size_t hidden_dim)
{
    size_t index;
    if (state == NULL || input == NULL || a == NULL || b == NULL) return NR_SSM_ERR_ARGUMENT;
    if (hidden_dim == 0U || hidden_dim > NR_TERNARY_SSM_MAX_HIDDEN) return NR_SSM_ERR_RANGE;
    for (index = 0U; index < hidden_dim; ++index) {
        int64_t value;
        if (!valid_trit(a[index]) || !valid_trit(b[index])) return NR_SSM_ERR_TRIT;
        value = (int64_t)a[index] * (int64_t)state[index] +
                (int64_t)b[index] * (int64_t)input[index];
        if (value < INT32_MIN || value > INT32_MAX) return NR_SSM_ERR_OVERFLOW;
        state[index] = (int32_t)value;
    }
    return NR_SSM_OK;
}

nr_ssm_status nr_ternary_ssm_project_binary32(const int32_t *state,
                                              const uint32_t *weights_binary32,
                                              size_t hidden_dim,
                                              uint32_t *output_binary32)
{
    size_t index;
    uint32_t sum = UINT32_C(0);
    if (state == NULL || weights_binary32 == NULL || output_binary32 == NULL) return NR_SSM_ERR_ARGUMENT;
    if (hidden_dim == 0U || hidden_dim > NR_TERNARY_SSM_MAX_HIDDEN) return NR_SSM_ERR_RANGE;
    for (index = 0U; index < hidden_dim; ++index) {
        uint32_t state_bits = nr_binary32_from_int32_reference(state[index]);
        uint32_t product = nr_binary32_mul_reference(state_bits, weights_binary32[index]);
        sum = nr_binary32_add_reference(sum, product);
    }
    *output_binary32 = sum;
    return NR_SSM_OK;
}

const char *nr_ssm_status_string(nr_ssm_status status)
{
    switch (status) {
    case NR_SSM_OK: return "ok";
    case NR_SSM_ERR_ARGUMENT: return "invalid argument";
    case NR_SSM_ERR_RANGE: return "hidden dimension outside configured bound";
    case NR_SSM_ERR_TRIT: return "A/B weight is not ternary";
    case NR_SSM_ERR_OVERFLOW: return "exact int32 state overflow";
    default: return "unknown SSM status";
    }
}
