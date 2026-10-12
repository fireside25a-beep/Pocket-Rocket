#include "ternary_ssm.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

int main(void)
{
    assert(nr_ssm_status_string(NR_SSM_OK) != NULL);
    int32_t state[4] = {1,2,3,4};
    int32_t input[4] = {10,20,30,40};
    int8_t a[4] = {1,0,-1,1};
    int8_t b[4] = {0,1,1,-1};
    uint32_t weights[4] = {0x3f800000U,0x3f800000U,0x3f800000U,0x3f800000U};
    uint32_t output = 0U;
    assert(nr_ternary_ssm_step(state, input, a, b, 4U) == NR_SSM_OK);
    assert(state[0] == 1 && state[1] == 20 && state[2] == 27 && state[3] == -36);
    assert(nr_ternary_ssm_project_binary32(state, weights, 4U, &output) == NR_SSM_OK);
    assert(output == nr_binary32_from_int32_reference(12));
    a[0] = 2;
    assert(nr_ternary_ssm_step(state, input, a, b, 4U) == NR_SSM_ERR_TRIT);
    puts("ternary_ssm: PASS");
    return 0;
}
