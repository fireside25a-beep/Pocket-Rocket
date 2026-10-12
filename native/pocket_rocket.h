#ifndef NEURO_ROUTE_POCKET_ROCKET_H
#define NEURO_ROUTE_POCKET_ROCKET_H

/* Strict C11 random-access reader for src/neuro_inverse/pocket_pack.py. */

#include "nprq.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#define PR_HEADER_BYTES ((uint64_t)64U)
#define PR_ENTRY_BYTES ((uint64_t)64U)
#define PR_MAX_CHUNK_BYTES ((uint64_t)67108864U)
#define PR_DEFAULT_MAX_SOURCE_BYTES ((uint64_t)137438953472U)
#define PR_DEFAULT_MAX_RANGE_BYTES ((uint64_t)268435456U)
#define PR_MAGIC_BYTES ((size_t)8U)

typedef enum pr_status {
    PR_OK = 0,
    PR_ERR_ARGUMENT = 1,
    PR_ERR_IO = 2,
    PR_ERR_SIZE = 3,
    PR_ERR_FORMAT = 4,
    PR_ERR_BOUNDS = 5,
    PR_ERR_MEMORY = 6,
    PR_ERR_ZLIB_UNAVAILABLE = 7,
    PR_ERR_ZLIB = 8,
    PR_ERR_CHECKSUM = 9,
    PR_ERR_OUTPUT = 10,
    PR_ERR_INDEX = 11
} pr_status;

typedef struct pr_limits {
    uint64_t max_source_bytes;
    uint64_t max_chunk_bytes;
    uint64_t max_range_bytes;
} pr_limits;

typedef struct pr_chunk_info {
    uint64_t index;
    uint64_t offset;
    uint64_t stored_bytes;
    uint64_t raw_bytes;
    uint32_t crc32;
    uint8_t codec;
    uint8_t sha256[NPRQ_SHA256_BYTES];
} pr_chunk_info;

typedef struct pr_container_info {
    uint64_t source_bytes;
    uint64_t chunk_size;
    uint64_t chunk_count;
    uint8_t source_sha256[NPRQ_SHA256_BYTES];
    uint64_t container_bytes;
} pr_container_info;

typedef struct pr_reader {
    FILE *handle;
    uint64_t file_size;
    pr_limits limits;
    pr_container_info info;
} pr_reader;

void pr_default_limits(pr_limits *limits);
pr_status pr_open(pr_reader *reader, const char *path, const pr_limits *limits);
pr_status pr_close(pr_reader *reader);

pr_status pr_get_chunk_info(const pr_reader *reader,
                            uint64_t index,
                            pr_chunk_info *chunk);

/* Decode one chunk into caller-owned output storage. */
pr_status pr_read_chunk(const pr_reader *reader,
                        uint64_t index,
                        uint8_t *output,
                        size_t output_capacity,
                        size_t *output_bytes);

/* Allocate one bounded decoded chunk; caller owns *output and must free it. */
pr_status pr_read_chunk_alloc(const pr_reader *reader,
                              uint64_t index,
                              uint8_t **output,
                              size_t *output_bytes);

/* Read a bounded source range using random chunk access. */
pr_status pr_read_range(const pr_reader *reader,
                        uint64_t offset,
                        uint64_t length,
                        uint8_t *output,
                        size_t output_capacity,
                        size_t *output_bytes);

/* Reconstruct and authenticate the complete source stream. */
pr_status pr_verify(const pr_reader *reader);

uint32_t pr_crc32(const uint8_t *data, size_t length);
const char *pr_status_string(pr_status status);

#endif
