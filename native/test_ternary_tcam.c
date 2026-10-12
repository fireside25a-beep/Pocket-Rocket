#include "ternary_tcam.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

int main(void)
{
    assert(nr_tcam_status_string(NR_TCAM_OK) != NULL);
    int8_t qv[8] = {1,0,-1,1,0,-1,1,0};
    int8_t av[8] = {1,0,-1,1,0,-1,1,0};
    int8_t bv[8] = {1,0,-1,-1,0,-1,1,0};
    int8_t cv[8] = {-1,0,1,-1,0,1,-1,0};
    nr_ternary_vector query, table[3];
    size_t index = 99U;
    int32_t score = -99;
    assert(nr_ternary_pack(qv, 8U, &query) == NR_TERNARY_OK);
    assert(nr_ternary_pack(cv, 8U, &table[0]) == NR_TERNARY_OK);
    assert(nr_ternary_pack(bv, 8U, &table[1]) == NR_TERNARY_OK);
    assert(nr_ternary_pack(av, 8U, &table[2]) == NR_TERNARY_OK);
    assert(nr_tcam_lookup(&query, table, 3U, &index, &score) == NR_TCAM_OK);
    assert(index == 2U && score == 8);
    assert(nr_tcam_exact_match(&query, table, 3U, &index) == NR_TCAM_OK && index == 2U);
    assert(nr_tcam_lookup(&query, table, NR_TCAM_MAX_ENTRIES + 1U, &index, &score) == NR_TCAM_ERR_RANGE);
#if defined(__AVX2__)
    {
        size_t avx_index = 0U; int32_t avx_score = 0;
        assert(nr_tcam_lookup_avx2(&query, table, 3U, &avx_index, &avx_score) == NR_TCAM_OK);
        assert(avx_index == 2U && avx_score == 8);
    }
#else
    assert(nr_tcam_lookup_avx2(&query, table, 3U, &index, &score) == NR_TCAM_ERR_UNAVAILABLE);
#endif
    puts("ternary_tcam: PASS");
    return 0;
}
