#include "flat32.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures = 0;
#define ENCODED_BYTES 151U

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        ++failures; \
    } \
} while (0)

static void put_u16(uint8_t *out, uint16_t value)
{
    out[0] = (uint8_t)value;
    out[1] = (uint8_t)(value >> 8U);
}

static void put_u64(uint8_t *out, uint64_t value)
{
    size_t index;
    for (index = 0U; index < 8U; ++index) {
        out[index] = (uint8_t)(value >> (8U * index));
    }
}

static int make_fixture(uint8_t encoded[ENCODED_BYTES],
                        uint8_t source[100],
                        flat32_dictionary *dictionary)
{
    uint8_t entries[2U * (size_t)FLAT32_BLOCK_SIZE];
    uint8_t dictionary_digest[NPRQ_SHA256_BYTES];
    uint8_t source_digest[NPRQ_SHA256_BYTES];
    uint8_t raw_block[NPRQ_SHA256_BYTES];
    size_t body_offset;

    memset(entries, 'A', (size_t)FLAT32_BLOCK_SIZE);
    memset(entries + (size_t)FLAT32_BLOCK_SIZE, 'B', (size_t)FLAT32_BLOCK_SIZE);
    if (flat32_dictionary_init(dictionary, entries, 2U) != FLAT32_OK ||
        nprq_sha256_bytes((const uint8_t *)"raw", 3U, raw_block) != NPRQ_OK) {
        return 0;
    }
    memcpy(source, entries, 32U);
    memcpy(source + 32U, raw_block, sizeof(raw_block));
    memcpy(source + 64U, entries + 32U, 32U);
    memcpy(source + 96U, "tail", 4U);
    if (nprq_sha256_bytes((const uint8_t *)dictionary->entries, 64U,
                          dictionary_digest) != NPRQ_OK ||
        nprq_sha256_bytes(source, 100U, source_digest) != NPRQ_OK) {
        return 0;
    }
    memset(encoded, 0, ENCODED_BYTES);
    memcpy(encoded, "NRFLAT32", 8U);
    put_u16(encoded + 8U, 1U);
    put_u16(encoded + 10U, 0U);
    put_u16(encoded + 12U, 32U);
    put_u16(encoded + 14U, 2U);
    put_u64(encoded + 16U, 100U);
    put_u64(encoded + 24U, 3U);
    put_u64(encoded + 32U, 1U);
    put_u64(encoded + 40U, 38U);
    memcpy(encoded + 48U, dictionary_digest, sizeof(dictionary_digest));
    memcpy(encoded + 80U, source_digest, sizeof(source_digest));
    encoded[112] = 0x05U;
    body_offset = 113U;
    encoded[body_offset++] = 0U;
    memcpy(encoded + body_offset, source + 32U, 32U);
    body_offset += 32U;
    encoded[body_offset++] = 1U;
    memcpy(encoded + body_offset, source + 96U, 4U);
    body_offset += 4U;
    return body_offset == ENCODED_BYTES;
}

static void test_exact_fixture(void)
{
    uint8_t encoded[ENCODED_BYTES];
    uint8_t source[100];
    uint8_t output[100];
    uint8_t *allocated = NULL;
    size_t output_bytes = 0U;
    flat32_dictionary dictionary;
    flat32_info info;
    static const uint8_t expected_encoded_sha[NPRQ_SHA256_BYTES] = {
        0xB1U, 0xF7U, 0x6CU, 0x39U, 0x90U, 0x13U, 0x4CU, 0x85U,
        0x43U, 0x70U, 0x6FU, 0xE9U, 0xCFU, 0x7AU, 0x19U, 0x3AU,
        0x2AU, 0x03U, 0x05U, 0x80U, 0x3AU, 0x38U, 0xB9U, 0xF8U,
        0xAEU, 0xFDU, 0x7AU, 0x95U, 0x6CU, 0x87U, 0xAFU, 0xA6U
    };
    uint8_t encoded_digest[NPRQ_SHA256_BYTES];

    CHECK(make_fixture(encoded, source, &dictionary));
    CHECK(nprq_sha256_bytes(encoded, sizeof(encoded), encoded_digest) == NPRQ_OK);
    CHECK(memcmp(encoded_digest, expected_encoded_sha, sizeof(encoded_digest)) == 0);
    CHECK(flat32_validate(encoded, sizeof(encoded), &dictionary, NULL, &info) == FLAT32_OK);
    CHECK(info.source_bytes == 100U && info.block_count == 3U &&
          info.bitmap_bytes == 1U && info.body_bytes == 38U &&
          info.tail_bytes == 4U && info.registered_blocks == 2U);
    CHECK(flat32_decode(encoded, sizeof(encoded), &dictionary, NULL,
                        output, sizeof(output), &output_bytes) == FLAT32_OK);
    CHECK(output_bytes == sizeof(source) && memcmp(output, source, sizeof(source)) == 0);
    CHECK(flat32_decode_alloc(encoded, sizeof(encoded), &dictionary, NULL,
                              &allocated, &output_bytes) == FLAT32_OK);
    CHECK(output_bytes == sizeof(source) && memcmp(allocated, source, sizeof(source)) == 0);
    free(allocated);
    CHECK(flat32_decode(encoded, sizeof(encoded), &dictionary, NULL,
                        output, 99U, &output_bytes) == FLAT32_ERR_OUTPUT);
}

static void test_fail_closed_cases(void)
{
    uint8_t encoded[ENCODED_BYTES];
    uint8_t source[100];
    uint8_t output[100];
    flat32_dictionary dictionary;
    flat32_dictionary wrong;
    flat32_limits limits;

    CHECK(make_fixture(encoded, source, &dictionary));
    {
        uint8_t wrong_entries[32];
        memset(wrong_entries, 'C', sizeof(wrong_entries));
        CHECK(flat32_dictionary_init(&wrong, wrong_entries, 1U) == FLAT32_OK);
        CHECK(flat32_validate(encoded, sizeof(encoded), &wrong, NULL, NULL) == FLAT32_ERR_DICTIONARY);
    }
    {
        uint8_t corrupted[ENCODED_BYTES];
        memcpy(corrupted, encoded, sizeof(corrupted));
        corrupted[ENCODED_BYTES - 1U] ^= 1U;
        CHECK(flat32_decode(corrupted, sizeof(corrupted), &dictionary, NULL,
                            output, sizeof(output), NULL) == FLAT32_ERR_ARGUMENT);
        {
            size_t output_bytes = 0U;
            CHECK(flat32_decode(corrupted, sizeof(corrupted), &dictionary, NULL,
                                output, sizeof(output), &output_bytes) == FLAT32_ERR_CHECKSUM);
        }
        memcpy(corrupted, encoded, sizeof(corrupted));
        corrupted[112] |= 0x80U;
        CHECK(flat32_validate(corrupted, sizeof(corrupted), &dictionary, NULL, NULL) == FLAT32_ERR_FORMAT);
        memcpy(corrupted, encoded, sizeof(corrupted));
        corrupted[113] = 2U;
        {
            size_t output_bytes = 0U;
            CHECK(flat32_validate(corrupted, sizeof(corrupted), &dictionary, NULL, NULL) == FLAT32_OK);
            CHECK(flat32_decode(corrupted, sizeof(corrupted), &dictionary, NULL,
                                output, sizeof(output), &output_bytes) == FLAT32_ERR_TOKEN);
        }
        memcpy(corrupted, encoded, sizeof(corrupted));
        put_u64(corrupted + 40U, 40U);
        CHECK(flat32_validate(corrupted, sizeof(corrupted), &dictionary, NULL, NULL) == FLAT32_ERR_FORMAT);
        CHECK(flat32_validate(encoded, sizeof(encoded) - 1U, &dictionary, NULL, NULL) == FLAT32_ERR_FORMAT);
    }
    flat32_default_limits(&limits);
    limits.max_source_bytes = 1U;
    CHECK(flat32_validate(encoded, sizeof(encoded), &dictionary, &limits, NULL) == FLAT32_ERR_FORMAT);
    limits.max_source_bytes = 100U;
    limits.max_encoded_bytes = ENCODED_BYTES - 1U;
    CHECK(flat32_validate(encoded, sizeof(encoded), &dictionary, &limits, NULL) == FLAT32_ERR_BOUNDS);
}

static void test_dictionary_limits_and_empty(void)
{
    flat32_dictionary dictionary;
    uint8_t duplicate[64];
    uint8_t encoded[FLAT32_HEADER_SIZE];
    uint8_t digest[NPRQ_SHA256_BYTES];
    size_t output_bytes = 0U;
    uint8_t *output = NULL;

    memset(duplicate, 'A', sizeof(duplicate));
    CHECK(flat32_dictionary_init(&dictionary, duplicate, 2U) == FLAT32_ERR_DICTIONARY);
    CHECK(flat32_dictionary_init(&dictionary, NULL, 0U) == FLAT32_OK);
    memset(encoded, 0, sizeof(encoded));
    memcpy(encoded, "NRFLAT32", 8U);
    put_u16(encoded + 8U, 1U);
    put_u16(encoded + 12U, 32U);
    put_u64(encoded + 32U, 0U);
    put_u64(encoded + 40U, 0U);
    CHECK(nprq_sha256_bytes(NULL, 0U, digest) == NPRQ_OK);
    memcpy(encoded + 48U, digest, sizeof(digest));
    memcpy(encoded + 80U, digest, sizeof(digest));
    CHECK(flat32_decode_alloc(encoded, sizeof(encoded), &dictionary, NULL,
                              &output, &output_bytes) == FLAT32_OK);
    CHECK(output == NULL && output_bytes == 0U);
    free(output);
}

int main(void)
{
    test_exact_fixture();
    test_fail_closed_cases();
    test_dictionary_limits_and_empty();
    if (failures != 0) {
        fprintf(stderr, "%d Flat32 test(s) failed\n", failures);
        return EXIT_FAILURE;
    }
    puts("Flat32 tests: PASS");
    return EXIT_SUCCESS;
}
