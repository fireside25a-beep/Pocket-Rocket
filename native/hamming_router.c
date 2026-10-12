#include "hamming_router.h"
#include <limits.h>

static unsigned int popcount64(uint64_t value)
{
#if defined(__GNUC__) || defined(__clang__)
    return (unsigned int)__builtin_popcountll((unsigned long long)value);
#else
    unsigned int count = 0U;
    while (value != 0U) { value &= value - UINT64_C(1); ++count; }
    return count;
#endif
}

int nr_hamming1024(const nr_hamming1024_code *left, const nr_hamming1024_code *right,
                   uint16_t *distance)
{
    size_t word;
    unsigned int total = 0U;
    if (left == NULL || right == NULL || distance == NULL) return 0;
    for (word = 0U; word < NR_HAMMING1024_WORDS; ++word) total += popcount64(left->words[word] ^ right->words[word]);
    *distance = (uint16_t)total;
    return 1;
}

int nr_hamming_route(const nr_hamming1024_code *query, const nr_hamming1024_code *table,
                     size_t count, size_t *best_index, uint16_t *best_distance)
{
    size_t index;
    uint16_t distance;
    if (query == NULL || table == NULL || best_index == NULL || best_distance == NULL ||
        count == 0U || count > NR_HAMMING_ROUTER_MAX_ENTRIES) return 0;
    *best_index = 0U; *best_distance = UINT16_MAX;
    for (index = 0U; index < count; ++index) {
        if (!nr_hamming1024(query, &table[index], &distance)) return 0;
        if (distance < *best_distance) { *best_distance = distance; *best_index = index; }
    }
    return 1;
}
