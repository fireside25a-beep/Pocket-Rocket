#ifndef NEURO_ROUTE_FLAT32_DICT_H
#define NEURO_ROUTE_FLAT32_DICT_H

/* Strict parser for the standalone NRDICT32 dictionary file. */

#include "flat32.h"

#include <stddef.h>
#include <stdint.h>

#define FLAT32_DICT_MAGIC_SIZE ((size_t)8U)
#define FLAT32_DICT_HEADER_SIZE ((size_t)46U)
#define FLAT32_DICT_MAX_BYTES \
    (FLAT32_DICT_HEADER_SIZE + \
     FLAT32_MAX_DICTIONARY_ENTRIES * (size_t)FLAT32_BLOCK_SIZE)

typedef enum flat32_dict_status {
    FLAT32_DICT_OK = 0,
    FLAT32_DICT_ERR_ARGUMENT = 1,
    FLAT32_DICT_ERR_BOUNDS = 2,
    FLAT32_DICT_ERR_FORMAT = 3,
    FLAT32_DICT_ERR_DUPLICATE = 4,
    FLAT32_DICT_ERR_CHECKSUM = 5,
    FLAT32_DICT_ERR_DICTIONARY = 6
} flat32_dict_status;

typedef struct flat32_dict_info {
    size_t count;
    size_t payload_bytes;
    size_t total_bytes;
    uint8_t payload_sha256[NPRQ_SHA256_BYTES];
} flat32_dict_info;

/* Parse one complete _flat32.dict file image into an existing Flat32 decoder. */
flat32_dict_status flat32_dict_parse_bytes(const uint8_t *encoded,
                                           size_t encoded_bytes,
                                           flat32_dictionary *dictionary,
                                           flat32_dict_info *info);

const char *flat32_dict_status_string(flat32_dict_status status);

#endif
