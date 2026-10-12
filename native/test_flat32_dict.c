#include "flat32_dict.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "check failed at %s:%d: %s\n",                    \
                    __FILE__, __LINE__, #condition);                           \
            return EXIT_FAILURE;                                                \
        }                                                                       \
    } while (0)

static const uint8_t dictionary_fixture[110U] = {
    0x4eU, 0x52U, 0x44U, 0x49U, 0x43U, 0x54U, 0x33U, 0x32U,
    0x01U, 0x00U, 0x00U, 0x00U, 0x02U, 0x00U,
    0x9eU, 0x2dU, 0x1fU, 0x68U, 0xa3U, 0xf9U, 0x80U, 0x59U,
    0xc3U, 0xc8U, 0xe6U, 0xf7U, 0x7dU, 0xe8U, 0x63U, 0xbeU,
    0x7fU, 0x58U, 0x65U, 0xc0U, 0xf5U, 0xf3U, 0x04U, 0xd7U,
    0x85U, 0xc3U, 0x45U, 0x83U, 0x3bU, 0x47U, 0xf2U, 0x49U,
    'A', 'A', 'A', 'A', 'A', 'A', 'A', 'A',
    'A', 'A', 'A', 'A', 'A', 'A', 'A', 'A',
    'A', 'A', 'A', 'A', 'A', 'A', 'A', 'A',
    'A', 'A', 'A', 'A', 'A', 'A', 'A', 'A',
    'B', 'B', 'B', 'B', 'B', 'B', 'B', 'B',
    'B', 'B', 'B', 'B', 'B', 'B', 'B', 'B',
    'B', 'B', 'B', 'B', 'B', 'B', 'B', 'B',
    'B', 'B', 'B', 'B', 'B', 'B', 'B', 'B'
};

static void put_u16(uint8_t *bytes, size_t offset, uint16_t value)
{
    bytes[offset] = (uint8_t)(value & 0xffU);
    bytes[offset + 1U] = (uint8_t)(value >> 8U);
}

static void put_u64(uint8_t *bytes, size_t offset, uint64_t value)
{
    size_t index;
    for (index = 0U; index < 8U; ++index) {
        bytes[offset + index] = (uint8_t)(value >> (8U * index));
    }
}

static int refresh_payload_digest(uint8_t *encoded, size_t encoded_bytes)
{
    uint8_t digest[NPRQ_SHA256_BYTES];

    if (encoded == NULL || encoded_bytes < FLAT32_DICT_HEADER_SIZE ||
        nprq_sha256_bytes(encoded + FLAT32_DICT_HEADER_SIZE,
                          encoded_bytes - FLAT32_DICT_HEADER_SIZE,
                          digest) != NPRQ_OK) {
        return 0;
    }
    memcpy(encoded + 14U, digest, sizeof(digest));
    return 1;
}

static int test_fixture_and_decoder(void)
{
    flat32_dictionary dictionary;
    flat32_dict_info dictionary_info;
    uint8_t encoded[114U];
    uint8_t output[32U];
    uint8_t source_digest[NPRQ_SHA256_BYTES];
    size_t output_bytes = 0U;
    flat32_status decode_status;

    CHECK(flat32_dict_parse_bytes(dictionary_fixture, sizeof(dictionary_fixture),
                                  &dictionary, &dictionary_info) == FLAT32_DICT_OK);
    CHECK(dictionary_info.count == 2U);
    CHECK(dictionary_info.payload_bytes == 64U);
    CHECK(dictionary_info.total_bytes == sizeof(dictionary_fixture));
    CHECK(memcmp(dictionary.entries[0], dictionary_fixture + 46U, 32U) == 0);
    CHECK(memcmp(dictionary.entries[1], dictionary_fixture + 78U, 32U) == 0);
    CHECK(memcmp(dictionary.sha256, dictionary_info.payload_sha256,
                 NPRQ_SHA256_BYTES) == 0);

    memset(encoded, 0, sizeof(encoded));
    memcpy(encoded, "NRFLAT32", 8U);
    put_u16(encoded, 8U, 1U);
    put_u16(encoded, 10U, 0U);
    put_u16(encoded, 12U, 32U);
    put_u16(encoded, 14U, 2U);
    put_u64(encoded, 16U, 32U);
    put_u64(encoded, 24U, 1U);
    put_u64(encoded, 32U, 1U);
    put_u64(encoded, 40U, 1U);
    memcpy(encoded + 48U, dictionary.sha256, NPRQ_SHA256_BYTES);
    CHECK(nprq_sha256_bytes(dictionary.entries[0], 32U, source_digest) == NPRQ_OK);
    memcpy(encoded + 80U, source_digest, NPRQ_SHA256_BYTES);
    encoded[112U] = 1U;
    encoded[113U] = 0U;

    decode_status = flat32_decode(encoded, sizeof(encoded), &dictionary, NULL,
                                  output, sizeof(output), &output_bytes);
    CHECK(decode_status == FLAT32_OK);
    CHECK(output_bytes == sizeof(output));
    CHECK(memcmp(output, dictionary.entries[0], sizeof(output)) == 0);
    return 0;
}

static int test_rejections(void)
{
    flat32_dictionary dictionary;
    flat32_dict_info info;
    uint8_t corrupted[sizeof(dictionary_fixture)];
    uint8_t oversized[sizeof(dictionary_fixture) + 1U];

    memcpy(corrupted, dictionary_fixture, sizeof(corrupted));
    corrupted[50U] ^= 0x01U;
    CHECK(flat32_dict_parse_bytes(corrupted, sizeof(corrupted), &dictionary, &info) ==
          FLAT32_DICT_ERR_CHECKSUM);

    memcpy(corrupted, dictionary_fixture, sizeof(corrupted));
    corrupted[14U] ^= 0x01U;
    CHECK(flat32_dict_parse_bytes(corrupted, sizeof(corrupted), &dictionary, &info) ==
          FLAT32_DICT_ERR_CHECKSUM);

    memcpy(corrupted, dictionary_fixture, sizeof(corrupted));
    corrupted[0U] = (uint8_t)'X';
    CHECK(flat32_dict_parse_bytes(corrupted, sizeof(corrupted), &dictionary, &info) ==
          FLAT32_DICT_ERR_FORMAT);

    memcpy(corrupted, dictionary_fixture, sizeof(corrupted));
    corrupted[8U] = 2U;
    CHECK(flat32_dict_parse_bytes(corrupted, sizeof(corrupted), &dictionary, &info) ==
          FLAT32_DICT_ERR_FORMAT);

    memcpy(corrupted, dictionary_fixture, sizeof(corrupted));
    corrupted[10U] = 1U;
    CHECK(flat32_dict_parse_bytes(corrupted, sizeof(corrupted), &dictionary, &info) ==
          FLAT32_DICT_ERR_FORMAT);

    memcpy(corrupted, dictionary_fixture, sizeof(corrupted));
    corrupted[12U] = 3U;
    CHECK(flat32_dict_parse_bytes(corrupted, sizeof(corrupted), &dictionary, &info) ==
          FLAT32_DICT_ERR_FORMAT);

    CHECK(flat32_dict_parse_bytes(dictionary_fixture, sizeof(dictionary_fixture) - 1U,
                                  &dictionary, &info) != FLAT32_DICT_OK);
    memcpy(oversized, dictionary_fixture, sizeof(dictionary_fixture));
    oversized[sizeof(dictionary_fixture)] = 0U;
    CHECK(flat32_dict_parse_bytes(oversized, sizeof(oversized), &dictionary, &info) !=
          FLAT32_DICT_OK);

    memcpy(corrupted, dictionary_fixture, sizeof(corrupted));
    memcpy(corrupted + 78U, corrupted + 46U, 32U);
    CHECK(refresh_payload_digest(corrupted, sizeof(corrupted)) != 0);
    CHECK(flat32_dict_parse_bytes(corrupted, sizeof(corrupted), &dictionary, &info) ==
          FLAT32_DICT_ERR_DUPLICATE);
    return 0;
}

int main(void)
{
    CHECK(test_fixture_and_decoder() == 0);
    CHECK(test_rejections() == 0);
    puts("flat32 dictionary tests: ok");
    return EXIT_SUCCESS;
}
