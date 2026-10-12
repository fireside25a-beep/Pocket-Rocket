#ifndef NEURO_ROUTE_FLAT32_H
#define NEURO_ROUTE_FLAT32_H

/* Strict C11 decoder for src/neuro_inverse/flat_dictionary.py. */

#include "nprq.h"

#include <stddef.h>
#include <stdint.h>

#define FLAT32_BLOCK_SIZE ((uint64_t)32U)
#define FLAT32_MAX_DICTIONARY_ENTRIES ((size_t)256U)
#define FLAT32_HEADER_SIZE ((size_t)112U)
#define FLAT32_MAX_SOURCE_BYTES ((uint64_t)137438953472U)
#define FLAT32_MAX_ENCODED_BYTES ((uint64_t)137438953472U)

typedef enum flat32_status {
    FLAT32_OK = 0,
    FLAT32_ERR_ARGUMENT = 1,
    FLAT32_ERR_BOUNDS = 2,
    FLAT32_ERR_FORMAT = 3,
    FLAT32_ERR_DICTIONARY = 4,
    FLAT32_ERR_TOKEN = 5,
    FLAT32_ERR_OUTPUT = 6,
    FLAT32_ERR_CHECKSUM = 7,
    FLAT32_ERR_MEMORY = 8
} flat32_status;

typedef struct flat32_dictionary {
    uint8_t entries[FLAT32_MAX_DICTIONARY_ENTRIES][FLAT32_BLOCK_SIZE];
    size_t count;
    uint8_t sha256[NPRQ_SHA256_BYTES];
} flat32_dictionary;

typedef struct flat32_limits {
    uint64_t max_source_bytes;
    uint64_t max_encoded_bytes;
} flat32_limits;

typedef struct flat32_info {
    uint64_t source_bytes;
    uint64_t block_count;
    uint64_t bitmap_bytes;
    uint64_t body_bytes;
    uint64_t tail_bytes;
    uint64_t registered_blocks;
    uint16_t dictionary_count;
} flat32_info;

flat32_status flat32_dictionary_init(flat32_dictionary *dictionary,
                                      const uint8_t *entries,
                                      size_t count);
void flat32_default_limits(flat32_limits *limits);

flat32_status flat32_validate(const uint8_t *encoded,
                              size_t encoded_bytes,
                              const flat32_dictionary *dictionary,
                              const flat32_limits *limits,
                              flat32_info *info);

flat32_status flat32_decode(const uint8_t *encoded,
                            size_t encoded_bytes,
                            const flat32_dictionary *dictionary,
                            const flat32_limits *limits,
                            uint8_t *output,
                            size_t output_capacity,
                            size_t *output_bytes);

flat32_status flat32_decode_alloc(const uint8_t *encoded,
                                  size_t encoded_bytes,
                                  const flat32_dictionary *dictionary,
                                  const flat32_limits *limits,
                                  uint8_t **output,
                                  size_t *output_bytes);

const char *flat32_status_string(flat32_status status);

#endif
