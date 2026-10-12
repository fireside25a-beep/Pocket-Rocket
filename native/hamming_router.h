#ifndef NEURO_ROUTE_HAMMING_ROUTER_H
#define NEURO_ROUTE_HAMMING_ROUTER_H

#include <stddef.h>
#include <stdint.h>

#define NR_HAMMING1024_WORDS ((size_t)16U)
#define NR_HAMMING_ROUTER_MAX_ENTRIES ((size_t)65536U)

typedef struct nr_hamming1024_code { uint64_t words[NR_HAMMING1024_WORDS]; } nr_hamming1024_code;

int nr_hamming1024(const nr_hamming1024_code *left, const nr_hamming1024_code *right,
                   uint16_t *distance);
int nr_hamming_route(const nr_hamming1024_code *query, const nr_hamming1024_code *table,
                     size_t count, size_t *best_index, uint16_t *best_distance);

#endif
