#include "hamming_router.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    nr_hamming1024_code query, table[3];
    size_t index = 99U;
    uint16_t distance = 999U;
    memset(&query, 0, sizeof(query));
    memset(table, 0, sizeof(table));
    query.words[0] = UINT64_C(0x0f);
    table[0].words[0] = UINT64_C(0xff);
    table[1].words[0] = UINT64_C(0x0f);
    table[2].words[0] = UINT64_C(0x07);
    assert(nr_hamming_route(&query, table, 3U, &index, &distance) == 1);
    assert(index == 1U && distance == 0U);
    assert(nr_hamming_route(&query, table, 0U, &index, &distance) == 0);
    puts("hamming_router: PASS");
    return 0;
}
