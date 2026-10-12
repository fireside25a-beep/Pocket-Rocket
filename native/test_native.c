#include "nprq.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TEST_PAGE ".native_test_page.nprq"
#define TEST_EMPTY ".native_test_empty.nprq"

static int failures = 0;

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        ++failures; \
    } \
} while (0)

static int write_file(const char *path, const unsigned char *data, size_t size)
{
    FILE *stream = fopen(path, "wb");
    int ok;
    if (stream == NULL) {
        return 0;
    }
    ok = size == 0U || fwrite(data, 1U, size, stream) == size;
    if (fclose(stream) != 0) {
        ok = 0;
    }
    return ok;
}

static void make_known_page(unsigned char page[12])
{
    /* 1.0 in IEEE-754 binary16, then 2.0 in the second block. */
    static const unsigned char packed_first[4] = {0xE4U, 0xE4U, 0xE4U, 0xE4U};
    static const unsigned char packed_second[4] = {0xE4U, 0x00U, 0x00U, 0x00U};
    page[0] = 0x00U;
    page[1] = 0x3CU;
    memcpy(page + 2U, packed_first, sizeof(packed_first));
    page[6] = 0x00U;
    page[7] = 0x40U;
    memcpy(page + 8U, packed_second, sizeof(packed_second));
}

static void test_page_layout_and_decode(void)
{
    unsigned char page[12];
    unsigned char oversized[13];
    unsigned char truncated[11];
    float output[20];
    float *allocated = NULL;
    size_t output_count = 0U;
    nprq_page_spec spec = {16U, 20U};
    nprq_page_info info;
    uint8_t digest[NPRQ_SHA256_BYTES];
    static const uint8_t expected_digest[NPRQ_SHA256_BYTES] = {
        0xBDU, 0x13U, 0x49U, 0x9BU, 0x0FU, 0xE2U, 0x6AU, 0xD2U,
        0xF9U, 0xCFU, 0x2BU, 0xDCU, 0x14U, 0x6CU, 0x1DU, 0x56U,
        0x3EU, 0x6BU, 0xA4U, 0x17U, 0xADU, 0x06U, 0x0FU, 0xBDU,
        0xB2U, 0xCAU, 0xC6U, 0xA6U, 0xB1U, 0xFFU, 0x35U, 0x3AU
    };
    static const float first_codes[16] = {
        -3.0F, -1.0F, 1.0F, 3.0F, -3.0F, -1.0F, 1.0F, 3.0F,
        -3.0F, -1.0F, 1.0F, 3.0F, -3.0F, -1.0F, 1.0F, 3.0F
    };
    size_t index;

    make_known_page(page);
    CHECK(write_file(TEST_PAGE, page, sizeof(page)));
    CHECK(nprq_sha256_file(TEST_PAGE, digest) == NPRQ_OK);
    CHECK(memcmp(digest, expected_digest, sizeof(digest)) == 0);
    CHECK(nprq_validate_page_file_hash(TEST_PAGE, &spec, expected_digest, &info) == NPRQ_OK);
    digest[0] ^= 1U;
    CHECK(nprq_validate_page_file_hash(TEST_PAGE, &spec, digest, NULL) == NPRQ_ERR_FORMAT);
    page[2] ^= 1U;
    CHECK(write_file(TEST_PAGE, page, sizeof(page)));
    CHECK(nprq_validate_page_file_hash(TEST_PAGE, &spec, expected_digest, NULL) == NPRQ_ERR_FORMAT);
    make_known_page(page);
    CHECK(write_file(TEST_PAGE, page, sizeof(page)));
    CHECK(nprq_page_layout(&spec, &info) == NPRQ_OK);
    CHECK(info.block_count == 2U && info.record_bytes == 6U &&
          info.expected_file_bytes == sizeof(page));
    CHECK(nprq_validate_page_file(TEST_PAGE, &spec, &info) == NPRQ_OK);
    CHECK(nprq_decode_page_file(TEST_PAGE, &spec, output, 20U) == NPRQ_OK);
    for (index = 0U; index < 16U; ++index) {
        CHECK(output[index] == first_codes[index]);
    }
    CHECK(output[16] == -6.0F && output[17] == -2.0F &&
          output[18] == 2.0F && output[19] == 6.0F);
    CHECK(nprq_decode_page_alloc(TEST_PAGE, &spec, &allocated, &output_count) == NPRQ_OK);
    CHECK(allocated != NULL && output_count == 20U);
    if (allocated != NULL) {
        for (index = 0U; index < output_count; ++index) {
            CHECK(allocated[index] == output[index]);
        }
    }
    free(allocated);
    CHECK(nprq_decode_page_file(TEST_PAGE, &spec, output, 19U) == NPRQ_ERR_OUTPUT);

    memcpy(truncated, page, sizeof(truncated));
    CHECK(write_file(TEST_PAGE, truncated, sizeof(truncated)));
    CHECK(nprq_validate_page_file(TEST_PAGE, &spec, NULL) == NPRQ_ERR_SIZE);
    memcpy(oversized, page, sizeof(page));
    oversized[12] = 0U;
    CHECK(write_file(TEST_PAGE, oversized, sizeof(oversized)));
    CHECK(nprq_validate_page_file(TEST_PAGE, &spec, NULL) == NPRQ_ERR_SIZE);

    page[0] = 0x00U;
    page[1] = 0x7CU; /* positive infinity: invalid scale */
    CHECK(write_file(TEST_PAGE, page, sizeof(page)));
    CHECK(nprq_validate_page_file(TEST_PAGE, &spec, NULL) == NPRQ_ERR_FORMAT);
    make_known_page(page);
    CHECK(write_file(TEST_PAGE, page, sizeof(page)));
}

static void test_limits_and_empty_page(void)
{
    nprq_page_info info;
    nprq_page_spec invalid_block = {18U, 1U};
    nprq_page_spec too_large = {16U, UINT64_MAX};
    nprq_page_spec empty = {16U, 0U};
    float *output = NULL;
    size_t count = 999U;

    CHECK(nprq_page_layout(&invalid_block, &info) == NPRQ_ERR_LIMIT);
    CHECK(nprq_page_layout(&too_large, &info) == NPRQ_OK);
    CHECK(nprq_decode_page_alloc(TEST_EMPTY, &too_large, &output, &count) == NPRQ_ERR_OVERFLOW);
    CHECK(write_file(TEST_EMPTY, NULL, 0U));
    CHECK(nprq_validate_page_file(TEST_EMPTY, &empty, &info) == NPRQ_OK);
    CHECK(info.block_count == 0U && info.expected_file_bytes == 0U);
    CHECK(nprq_decode_page_alloc(TEST_EMPTY, &empty, &output, &count) == NPRQ_OK);
    CHECK(output == NULL && count == 0U);
    free(output);
}

static void test_ternary_payload_validation(void)
{
    static const uint8_t valid[] = {0xA4U, 0x55U};
    static const int8_t expected[] = {-1, 0, 1, 1, 0};
    int8_t output[9U];

    CHECK(nprq_validate_ternary_payload(valid, sizeof(valid), 5U) == NPRQ_OK);
    CHECK(nprq_decode_ternary_payload(valid, sizeof(valid), 5U,
                                      output, sizeof(output)) == NPRQ_OK);
    CHECK(memcmp(output, expected, sizeof(expected)) == 0);
    CHECK(nprq_decode_ternary_payload(valid, sizeof(valid), 9U,
                                      output, sizeof(output)) == NPRQ_ERR_SIZE);
    CHECK(nprq_validate_ternary_payload((const uint8_t[]){0x03U}, 1U, 1U) ==
          NPRQ_ERR_FORMAT);
    /* High two bits are tail padding for a three-value payload. */
    CHECK(nprq_validate_ternary_payload((const uint8_t[]){0xAAU}, 1U, 3U) ==
          NPRQ_ERR_FORMAT);
    CHECK(nprq_validate_ternary_payload(valid, sizeof(valid) - 1U, 5U) ==
          NPRQ_ERR_SIZE);
    CHECK(nprq_decode_ternary_payload(valid, sizeof(valid), 5U,
                                      output, 4U) == NPRQ_ERR_OUTPUT);
}

static void test_hamming_and_ranking(void)
{
    uint8_t query[NPRQ_V2_CODE_BYTES] = {0U};
    uint8_t centroids[5U * NPRQ_V2_CODE_BYTES];
    nprq_ranked_expert ranked[5];
    size_t index;

    memset(centroids, 0, sizeof(centroids));
    centroids[NPRQ_V2_CODE_BYTES + 0U] = 1U;
    memset(centroids + 2U * NPRQ_V2_CODE_BYTES, 0xFF, NPRQ_V2_CODE_BYTES);
    centroids[3U * NPRQ_V2_CODE_BYTES + 0U] = 1U;
    centroids[4U * NPRQ_V2_CODE_BYTES + 0U] = 3U;
    CHECK(nprq_hamming256(query, centroids + 2U * NPRQ_V2_CODE_BYTES) == 256U);
    CHECK(nprq_hamming256(query, centroids + NPRQ_V2_CODE_BYTES) == 1U);
    CHECK(nprq_rank_experts(query, centroids, 5U, 5U, ranked) == NPRQ_OK);
    CHECK(ranked[0].expert_id == 0U && ranked[0].distance == 0U);
    CHECK(ranked[1].expert_id == 1U && ranked[1].distance == 1U);
    CHECK(ranked[2].expert_id == 3U && ranked[2].distance == 1U);
    CHECK(ranked[3].expert_id == 4U && ranked[3].distance == 2U);
    CHECK(ranked[4].expert_id == 2U && ranked[4].distance == 256U);
    CHECK(nprq_rank_experts(query, centroids, 5U, 3U, ranked) == NPRQ_OK);
    for (index = 0U; index < 3U; ++index) {
        CHECK(ranked[index].expert_id == (index == 2U ? 3U : index));
    }
    CHECK(nprq_rank_experts(query, centroids, 5U, 0U, ranked) == NPRQ_ERR_ARGUMENT);
}

int main(void)
{
    test_page_layout_and_decode();
    test_limits_and_empty_page();
    test_ternary_payload_validation();
    test_hamming_and_ranking();
    (void)remove(TEST_PAGE);
    (void)remove(TEST_EMPTY);
    if (failures != 0) {
        fprintf(stderr, "%d native test(s) failed\n", failures);
        return EXIT_FAILURE;
    }
    puts("native tests: PASS");
    return EXIT_SUCCESS;
}
