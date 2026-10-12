#include "flat32.h"

#include <limits.h>
#include <stdlib.h>
#include <string.h>

typedef struct flat32_parsed {
    flat32_info info;
    const uint8_t *bitmap;
    const uint8_t *body;
    size_t body_size;
    const uint8_t *source_sha256;
} flat32_parsed;

static uint16_t load_u16(const uint8_t *bytes)
{
    return (uint16_t)((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8U));
}

static uint64_t load_u64(const uint8_t *bytes)
{
    uint64_t value = 0U;
    size_t index;

    for (index = 0U; index < 8U; ++index) {
        value |= (uint64_t)bytes[index] << (8U * index);
    }
    return value;
}

static int add_u64(uint64_t left, uint64_t right, uint64_t *result)
{
    if (result == NULL || left > UINT64_MAX - right) {
        return 0;
    }
    *result = left + right;
    return 1;
}

static int mul_u64(uint64_t left, uint64_t right, uint64_t *result)
{
    if (result == NULL || (right != 0U && left > UINT64_MAX / right)) {
        return 0;
    }
    *result = left * right;
    return 1;
}

static unsigned int popcount8(uint8_t value)
{
    unsigned int count = 0U;
    unsigned int bit;

    for (bit = 0U; bit < 8U; ++bit) {
        count += (((unsigned int)value >> bit) & 1U);
    }
    return count;
}

static flat32_status dictionary_digest(const flat32_dictionary *dictionary,
                                       uint8_t digest[NPRQ_SHA256_BYTES])
{
    nprq_status status;
    size_t bytes;

    if (dictionary == NULL || digest == NULL ||
        dictionary->count > FLAT32_MAX_DICTIONARY_ENTRIES ||
        dictionary->count > SIZE_MAX / (size_t)FLAT32_BLOCK_SIZE) {
        return FLAT32_ERR_DICTIONARY;
    }
    bytes = dictionary->count * (size_t)FLAT32_BLOCK_SIZE;
    status = nprq_sha256_bytes((const uint8_t *)dictionary->entries, bytes, digest);
    return status == NPRQ_OK ? FLAT32_OK : FLAT32_ERR_DICTIONARY;
}

flat32_status flat32_dictionary_init(flat32_dictionary *dictionary,
                                      const uint8_t *entries,
                                      size_t count)
{
    size_t index;
    size_t other;
    uint8_t digest[NPRQ_SHA256_BYTES];

    if (dictionary == NULL || (entries == NULL && count != 0U) ||
        count > FLAT32_MAX_DICTIONARY_ENTRIES) {
        return FLAT32_ERR_ARGUMENT;
    }
    memset(dictionary, 0, sizeof(*dictionary));
    dictionary->count = count;
    for (index = 0U; index < count; ++index) {
        memcpy(dictionary->entries[index],
               entries + index * (size_t)FLAT32_BLOCK_SIZE,
               (size_t)FLAT32_BLOCK_SIZE);
        for (other = 0U; other < index; ++other) {
            if (memcmp(dictionary->entries[index], dictionary->entries[other],
                       (size_t)FLAT32_BLOCK_SIZE) == 0) {
                memset(dictionary, 0, sizeof(*dictionary));
                return FLAT32_ERR_DICTIONARY;
            }
        }
    }
    if (dictionary_digest(dictionary, digest) != FLAT32_OK) {
        memset(dictionary, 0, sizeof(*dictionary));
        return FLAT32_ERR_DICTIONARY;
    }
    memcpy(dictionary->sha256, digest, sizeof(digest));
    return FLAT32_OK;
}

void flat32_default_limits(flat32_limits *limits)
{
    if (limits != NULL) {
        limits->max_source_bytes = FLAT32_MAX_SOURCE_BYTES;
        limits->max_encoded_bytes = FLAT32_MAX_ENCODED_BYTES;
    }
}

static flat32_status parse_stream(const uint8_t *encoded,
                                  size_t encoded_bytes,
                                  const flat32_dictionary *dictionary,
                                  const flat32_limits *limits,
                                  flat32_parsed *parsed)
{
    flat32_limits selected;
    uint64_t source_bytes;
    uint64_t block_count;
    uint64_t bitmap_bytes;
    uint64_t body_bytes;
    uint64_t expected_bitmap;
    uint64_t framing_end;
    uint64_t expected_body;
    uint64_t registered = 0U;
    uint16_t dictionary_count;
    size_t index;
    uint8_t digest[NPRQ_SHA256_BYTES];

    if (encoded == NULL || dictionary == NULL || parsed == NULL) {
        return FLAT32_ERR_ARGUMENT;
    }
    if (limits == NULL) {
        flat32_default_limits(&selected);
    } else {
        selected = *limits;
    }
    if (encoded_bytes < FLAT32_HEADER_SIZE ||
        (uint64_t)encoded_bytes > selected.max_encoded_bytes ||
        (uint64_t)encoded_bytes > FLAT32_MAX_ENCODED_BYTES) {
        return FLAT32_ERR_BOUNDS;
    }
    if (memcmp(encoded, "NRFLAT32", 8U) != 0 ||
        load_u16(encoded + 8U) != 1U || load_u16(encoded + 10U) != 0U ||
        load_u16(encoded + 12U) != (uint16_t)FLAT32_BLOCK_SIZE) {
        return FLAT32_ERR_FORMAT;
    }
    dictionary_count = load_u16(encoded + 14U);
    if (dictionary_count > FLAT32_MAX_DICTIONARY_ENTRIES ||
        dictionary_count != dictionary->count) {
        return FLAT32_ERR_DICTIONARY;
    }
    source_bytes = load_u64(encoded + 16U);
    block_count = load_u64(encoded + 24U);
    bitmap_bytes = load_u64(encoded + 32U);
    body_bytes = load_u64(encoded + 40U);
    if (source_bytes > selected.max_source_bytes ||
        source_bytes > FLAT32_MAX_SOURCE_BYTES ||
        block_count != source_bytes / FLAT32_BLOCK_SIZE ||
        block_count > UINT64_MAX - 7U) {
        return FLAT32_ERR_FORMAT;
    }
    expected_bitmap = (block_count + 7U) / 8U;
    if (bitmap_bytes != expected_bitmap ||
        !add_u64(FLAT32_HEADER_SIZE, bitmap_bytes, &framing_end) ||
        !add_u64(framing_end, body_bytes, &framing_end) ||
        framing_end != (uint64_t)encoded_bytes) {
        return FLAT32_ERR_FORMAT;
    }
    if (memcmp(encoded + 48U, dictionary->sha256, NPRQ_SHA256_BYTES) != 0) {
        return FLAT32_ERR_DICTIONARY;
    }
    if (bitmap_bytes > (uint64_t)SIZE_MAX || body_bytes > (uint64_t)SIZE_MAX) {
        return FLAT32_ERR_BOUNDS;
    }
    for (index = 0U; index < (size_t)bitmap_bytes; ++index) {
        uint8_t value = encoded[FLAT32_HEADER_SIZE + index];
        if (index + 1U == (size_t)bitmap_bytes && (block_count % 8U) != 0U &&
            (value >> (block_count % 8U)) != 0U) {
            return FLAT32_ERR_FORMAT;
        }
        registered += popcount8(value);
    }
    if (registered > block_count ||
        !mul_u64(block_count - registered, FLAT32_BLOCK_SIZE, &expected_body) ||
        !add_u64(expected_body, registered, &expected_body) ||
        !add_u64(expected_body, source_bytes % FLAT32_BLOCK_SIZE, &expected_body) ||
        expected_body != body_bytes) {
        return FLAT32_ERR_FORMAT;
    }
    if (dictionary_digest(dictionary, digest) != FLAT32_OK ||
        memcmp(digest, encoded + 48U, NPRQ_SHA256_BYTES) != 0) {
        return FLAT32_ERR_DICTIONARY;
    }
    parsed->info.source_bytes = source_bytes;
    parsed->info.block_count = block_count;
    parsed->info.bitmap_bytes = bitmap_bytes;
    parsed->info.body_bytes = body_bytes;
    parsed->info.tail_bytes = source_bytes % FLAT32_BLOCK_SIZE;
    parsed->info.registered_blocks = registered;
    parsed->info.dictionary_count = dictionary_count;
    parsed->bitmap = encoded + FLAT32_HEADER_SIZE;
    parsed->body = encoded + FLAT32_HEADER_SIZE + (size_t)bitmap_bytes;
    parsed->body_size = (size_t)body_bytes;
    parsed->source_sha256 = encoded + 80U;
    return FLAT32_OK;
}

flat32_status flat32_validate(const uint8_t *encoded,
                              size_t encoded_bytes,
                              const flat32_dictionary *dictionary,
                              const flat32_limits *limits,
                              flat32_info *info)
{
    flat32_parsed parsed;
    flat32_status status = parse_stream(encoded, encoded_bytes, dictionary,
                                        limits, &parsed);
    if (status == FLAT32_OK && info != NULL) {
        *info = parsed.info;
    }
    return status;
}

flat32_status flat32_decode(const uint8_t *encoded,
                            size_t encoded_bytes,
                            const flat32_dictionary *dictionary,
                            const flat32_limits *limits,
                            uint8_t *output,
                            size_t output_capacity,
                            size_t *output_bytes)
{
    flat32_parsed parsed;
    size_t body_offset = 0U;
    uint64_t index;
    flat32_status status;
    uint8_t digest[NPRQ_SHA256_BYTES];
    unsigned int difference = 0U;
    size_t digest_index;

    if (output_bytes == NULL || (output == NULL && output_capacity != 0U)) {
        return FLAT32_ERR_ARGUMENT;
    }
    *output_bytes = 0U;
    status = parse_stream(encoded, encoded_bytes, dictionary, limits, &parsed);
    if (status != FLAT32_OK) {
        return status;
    }
    if (parsed.info.source_bytes > (uint64_t)SIZE_MAX ||
        output_capacity < (size_t)parsed.info.source_bytes ||
        (output == NULL && parsed.info.source_bytes != 0U)) {
        return FLAT32_ERR_OUTPUT;
    }
    for (index = 0U; index < parsed.info.block_count; ++index) {
        size_t bitmap_index = (size_t)(index / 8U);
        unsigned int bit = (unsigned int)(index % 8U);
        size_t destination = (size_t)(index * FLAT32_BLOCK_SIZE);
        if ((parsed.bitmap[bitmap_index] & (uint8_t)(1U << bit)) != 0U) {
            uint8_t token;
            if (body_offset >= parsed.body_size) {
                return FLAT32_ERR_FORMAT;
            }
            token = parsed.body[body_offset++];
            if ((size_t)token >= dictionary->count) {
                return FLAT32_ERR_TOKEN;
            }
            memcpy(output + destination, dictionary->entries[token],
                   (size_t)FLAT32_BLOCK_SIZE);
        } else {
            if (parsed.body_size - body_offset < (size_t)FLAT32_BLOCK_SIZE) {
                return FLAT32_ERR_FORMAT;
            }
            memcpy(output + destination, parsed.body + body_offset,
                   (size_t)FLAT32_BLOCK_SIZE);
            body_offset += (size_t)FLAT32_BLOCK_SIZE;
        }
    }
    if (parsed.info.tail_bytes != 0U) {
        size_t tail = (size_t)parsed.info.tail_bytes;
        if (parsed.body_size - body_offset != tail) {
            return FLAT32_ERR_FORMAT;
        }
        memcpy(output + (size_t)(parsed.info.source_bytes - parsed.info.tail_bytes),
               parsed.body + body_offset, tail);
        body_offset += tail;
    }
    if (body_offset != parsed.body_size ||
        nprq_sha256_bytes(output, (size_t)parsed.info.source_bytes, digest) != NPRQ_OK) {
        return FLAT32_ERR_FORMAT;
    }
    for (digest_index = 0U; digest_index < NPRQ_SHA256_BYTES; ++digest_index) {
        difference |= (unsigned int)(digest[digest_index] ^ parsed.source_sha256[digest_index]);
    }
    if (difference != 0U) {
        return FLAT32_ERR_CHECKSUM;
    }
    *output_bytes = (size_t)parsed.info.source_bytes;
    return FLAT32_OK;
}

flat32_status flat32_decode_alloc(const uint8_t *encoded,
                                  size_t encoded_bytes,
                                  const flat32_dictionary *dictionary,
                                  const flat32_limits *limits,
                                  uint8_t **output,
                                  size_t *output_bytes)
{
    flat32_info info;
    uint8_t *memory;
    size_t length;
    flat32_status status;

    if (output == NULL || output_bytes == NULL) {
        return FLAT32_ERR_ARGUMENT;
    }
    *output = NULL;
    *output_bytes = 0U;
    status = flat32_validate(encoded, encoded_bytes, dictionary, limits, &info);
    if (status != FLAT32_OK || info.source_bytes > (uint64_t)SIZE_MAX) {
        return status == FLAT32_OK ? FLAT32_ERR_BOUNDS : status;
    }
    if (info.source_bytes > SIZE_MAX / sizeof(uint8_t)) {
        return FLAT32_ERR_BOUNDS;
    }
    memory = info.source_bytes == 0U ? NULL : (uint8_t *)malloc((size_t)info.source_bytes);
    if (memory == NULL && info.source_bytes != 0U) {
        return FLAT32_ERR_MEMORY;
    }
    status = flat32_decode(encoded, encoded_bytes, dictionary, limits,
                           memory, (size_t)info.source_bytes, &length);
    if (status != FLAT32_OK) {
        free(memory);
        return status;
    }
    *output = memory;
    *output_bytes = length;
    return FLAT32_OK;
}

const char *flat32_status_string(flat32_status status)
{
    switch (status) {
    case FLAT32_OK: return "ok";
    case FLAT32_ERR_ARGUMENT: return "invalid argument";
    case FLAT32_ERR_BOUNDS: return "bounds exceeded";
    case FLAT32_ERR_FORMAT: return "invalid Flat32 format";
    case FLAT32_ERR_DICTIONARY: return "dictionary mismatch";
    case FLAT32_ERR_TOKEN: return "dictionary token out of range";
    case FLAT32_ERR_OUTPUT: return "output buffer too small";
    case FLAT32_ERR_CHECKSUM: return "source checksum mismatch";
    case FLAT32_ERR_MEMORY: return "allocation failure";
    default: return "unknown status";
    }
}
