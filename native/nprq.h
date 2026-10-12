#ifndef NEURO_ROUTE_NPRQ_H
#define NEURO_ROUTE_NPRQ_H

/*
 * Small, dependency-free reader for the NPRQ signed-quaternary v2 stage
 * pages produced by src/neuro_inverse/nprq.py.
 *
 * A v2 page has no self-describing header.  The caller must therefore supply
 * the authenticated shape information in nprq_page_spec.  Every page is
 * checked for an exact byte length before decoding; no prefix of a truncated
 * or oversized page is accepted.
 */

#include <stddef.h>
#include <stdint.h>

#define NPRQ_V2_CODE_BYTES ((size_t)32U)
#define NPRQ_SHA256_BYTES ((size_t)32U)
#define NPRQ_V2_MIN_BLOCK_SIZE ((uint64_t)16U)
#define NPRQ_V2_MAX_BLOCK_SIZE ((uint64_t)1048576U)

typedef enum nprq_status {
    NPRQ_OK = 0,
    NPRQ_ERR_ARGUMENT = 1,
    NPRQ_ERR_OVERFLOW = 2,
    NPRQ_ERR_LIMIT = 3,
    NPRQ_ERR_IO = 4,
    NPRQ_ERR_SIZE = 5,
    NPRQ_ERR_FORMAT = 6,
    NPRQ_ERR_MEMORY = 7,
    NPRQ_ERR_OUTPUT = 8
} nprq_status;

typedef struct nprq_page_spec {
    uint64_t block_size;
    uint64_t numel;
} nprq_page_spec;

typedef struct nprq_page_info {
    uint64_t block_count;
    uint64_t record_bytes;
    uint64_t expected_file_bytes;
} nprq_page_info;

typedef struct nprq_sha256_context {
    uint32_t state[8];
    uint64_t bit_count;
    unsigned char block[64];
    size_t block_length;
} nprq_sha256_context;

/* Validate dimensions and calculate the exact page byte length. */
nprq_status nprq_page_layout(const nprq_page_spec *spec,
                             nprq_page_info *info);

/* Validate an existing v2 page, including exact size and finite float16 scales. */
nprq_status nprq_validate_page_file(const char *path,
                                    const nprq_page_spec *spec,
                                    nprq_page_info *info);

/* Compute a binary SHA-256 digest without invoking an external command. */
nprq_status nprq_sha256_file(const char *path,
                             uint8_t digest[NPRQ_SHA256_BYTES]);

/* Hash a bounded in-memory byte sequence with SHA-256. */
nprq_status nprq_sha256_bytes(const uint8_t *data,
                              size_t length,
                              uint8_t digest[NPRQ_SHA256_BYTES]);

void nprq_sha256_init(nprq_sha256_context *context);
nprq_status nprq_sha256_update(nprq_sha256_context *context,
                               const uint8_t *data,
                               size_t length);
void nprq_sha256_final(nprq_sha256_context *context,
                       uint8_t digest[NPRQ_SHA256_BYTES]);

/* Validate both the page structure and its manifest SHA-256 digest. */
nprq_status nprq_validate_page_file_hash(
    const char *path,
    const nprq_page_spec *spec,
    const uint8_t expected_sha256[NPRQ_SHA256_BYTES],
    nprq_page_info *info);

/* Decode into caller-owned float32 storage. output_count must be >= numel. */
nprq_status nprq_decode_page_file(const char *path,
                                  const nprq_page_spec *spec,
                                  float *output,
                                  size_t output_count);

/* Allocate and decode a complete page. The caller owns *output and must free it. */
nprq_status nprq_decode_page_alloc(const char *path,
                                   const nprq_page_spec *spec,
                                   float **output,
                                   size_t *output_count);

/*
 * Validate/decode the legacy three-symbol packed representation used by the
 * Python compatibility helpers.  A packed symbol is 0, 1, or 2 for -1, 0,
 * or +1; symbol 3 and non-canonical tail padding are rejected.  The payload
 * length must be exactly ceil(count / 4), so trailing corruption is visible.
 */
nprq_status nprq_validate_ternary_payload(const uint8_t *packed,
                                         size_t packed_bytes,
                                         size_t count);
nprq_status nprq_decode_ternary_payload(const uint8_t *packed,
                                       size_t packed_bytes,
                                       size_t count,
                                       int8_t *output,
                                       size_t output_count);

const char *nprq_status_string(nprq_status status);

typedef struct nprq_ranked_expert {
    size_t expert_id;
    uint16_t distance;
} nprq_ranked_expert;

/* Hamming distance over exactly 256 bits. */
uint16_t nprq_hamming256(const uint8_t left[NPRQ_V2_CODE_BYTES],
                         const uint8_t right[NPRQ_V2_CODE_BYTES]);

/*
 * Rank implicit IDs [0, expert_count) by (Hamming distance, expert_id).
 * top_k must be in [1, expert_count].  out must contain top_k entries.
 */
nprq_status nprq_rank_experts(
    const uint8_t query[NPRQ_V2_CODE_BYTES],
    const uint8_t *centroids,
    size_t expert_count,
    size_t top_k,
    nprq_ranked_expert *out);

#endif
