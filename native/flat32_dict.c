#include "flat32_dict.h"

#include <string.h>

static uint16_t load_u16(const uint8_t *bytes)
{
    return (uint16_t)((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8U));
}

static int digest_equal(const uint8_t left[NPRQ_SHA256_BYTES],
                        const uint8_t right[NPRQ_SHA256_BYTES])
{
    unsigned int difference = 0U;
    size_t index;

    for (index = 0U; index < NPRQ_SHA256_BYTES; ++index) {
        difference |= (unsigned int)(left[index] ^ right[index]);
    }
    return difference == 0U;
}

flat32_dict_status flat32_dict_parse_bytes(const uint8_t *encoded,
                                           size_t encoded_bytes,
                                           flat32_dictionary *dictionary,
                                           flat32_dict_info *info)
{
    uint16_t count_field;
    size_t count;
    size_t payload_bytes;
    size_t expected_bytes;
    size_t index;
    size_t other;
    uint8_t digest[NPRQ_SHA256_BYTES];
    flat32_status dictionary_status;

    if (encoded == NULL || dictionary == NULL) {
        return FLAT32_DICT_ERR_ARGUMENT;
    }
    memset(dictionary, 0, sizeof(*dictionary));
    if (info != NULL) {
        memset(info, 0, sizeof(*info));
    }
    if (encoded_bytes < FLAT32_DICT_HEADER_SIZE ||
        encoded_bytes > FLAT32_DICT_MAX_BYTES) {
        return FLAT32_DICT_ERR_BOUNDS;
    }
    if (memcmp(encoded, "NRDICT32", FLAT32_DICT_MAGIC_SIZE) != 0 ||
        load_u16(encoded + 8U) != 1U ||
        load_u16(encoded + 10U) != 0U) {
        return FLAT32_DICT_ERR_FORMAT;
    }
    count_field = load_u16(encoded + 12U);
    if ((size_t)count_field > FLAT32_MAX_DICTIONARY_ENTRIES) {
        return FLAT32_DICT_ERR_DICTIONARY;
    }
    count = (size_t)count_field;
    payload_bytes = count * (size_t)FLAT32_BLOCK_SIZE;
    if (payload_bytes > SIZE_MAX - FLAT32_DICT_HEADER_SIZE) {
        return FLAT32_DICT_ERR_BOUNDS;
    }
    expected_bytes = FLAT32_DICT_HEADER_SIZE + payload_bytes;
    if (encoded_bytes != expected_bytes) {
        return FLAT32_DICT_ERR_FORMAT;
    }
    if (nprq_sha256_bytes(encoded + FLAT32_DICT_HEADER_SIZE,
                          payload_bytes, digest) != NPRQ_OK) {
        return FLAT32_DICT_ERR_CHECKSUM;
    }
    if (!digest_equal(digest, encoded + 14U)) {
        return FLAT32_DICT_ERR_CHECKSUM;
    }
    for (index = 0U; index < count; ++index) {
        const uint8_t *entry = encoded + FLAT32_DICT_HEADER_SIZE +
                               index * (size_t)FLAT32_BLOCK_SIZE;
        for (other = 0U; other < index; ++other) {
            const uint8_t *previous = encoded + FLAT32_DICT_HEADER_SIZE +
                                      other * (size_t)FLAT32_BLOCK_SIZE;
            if (memcmp(entry, previous, (size_t)FLAT32_BLOCK_SIZE) == 0) {
                return FLAT32_DICT_ERR_DUPLICATE;
            }
        }
    }
    dictionary_status = flat32_dictionary_init(
        dictionary, encoded + FLAT32_DICT_HEADER_SIZE, count);
    if (dictionary_status != FLAT32_OK) {
        memset(dictionary, 0, sizeof(*dictionary));
        return FLAT32_DICT_ERR_DICTIONARY;
    }
    if (info != NULL) {
        info->count = count;
        info->payload_bytes = payload_bytes;
        info->total_bytes = expected_bytes;
        memcpy(info->payload_sha256, digest, sizeof(digest));
    }
    return FLAT32_DICT_OK;
}

const char *flat32_dict_status_string(flat32_dict_status status)
{
    switch (status) {
    case FLAT32_DICT_OK: return "ok";
    case FLAT32_DICT_ERR_ARGUMENT: return "invalid argument";
    case FLAT32_DICT_ERR_BOUNDS: return "dictionary bounds exceeded";
    case FLAT32_DICT_ERR_FORMAT: return "invalid NRDICT32 format";
    case FLAT32_DICT_ERR_DUPLICATE: return "duplicate dictionary entry";
    case FLAT32_DICT_ERR_CHECKSUM: return "dictionary checksum mismatch";
    case FLAT32_DICT_ERR_DICTIONARY: return "invalid dictionary";
    default: return "unknown status";
    }
}
