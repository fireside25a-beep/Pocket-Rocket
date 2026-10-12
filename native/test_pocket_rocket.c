#include "pocket_rocket.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(NR_HAVE_ZLIB)
#include <zlib.h>
#endif

#define FIXTURE ".native_pocket_fixture.pkr"
#define CORRUPT ".native_pocket_corrupt.pkr"
#define TRUNCATED ".native_pocket_truncated.pkr"
#define TRAILING ".native_pocket_trailing.pkr"
#define BOMB ".native_pocket_bomb.pkr"
#define EMPTY ".native_pocket_empty.pkr"
#define TEST_SOURCE_BYTES 300U
#define TEST_CHUNK_BYTES 100U

static int failures = 0;

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

static void put_u32(uint8_t *out, uint32_t value)
{
    out[0] = (uint8_t)value;
    out[1] = (uint8_t)(value >> 8U);
    out[2] = (uint8_t)(value >> 16U);
    out[3] = (uint8_t)(value >> 24U);
}

static void put_u64(uint8_t *out, uint64_t value)
{
    size_t index;
    for (index = 0U; index < 8U; ++index) {
        out[index] = (uint8_t)(value >> (8U * index));
    }
}

static int write_file(const char *path, const uint8_t *data, size_t length)
{
    FILE *handle = fopen(path, "wb");
    int ok;

    if (handle == NULL) {
        return 0;
    }
    ok = length == 0U || fwrite(data, 1U, length, handle) == length;
    if (fclose(handle) != 0) {
        ok = 0;
    }
    return ok;
}

static int read_file(const char *path, uint8_t **data, size_t *length)
{
    FILE *handle;
    long end;
    uint8_t *memory;

    if (data == NULL || length == NULL) {
        return 0;
    }
    *data = NULL;
    *length = 0U;
    handle = fopen(path, "rb");
    if (handle == NULL || fseek(handle, 0L, SEEK_END) != 0) {
        if (handle != NULL) {
            (void)fclose(handle);
        }
        return 0;
    }
    end = ftell(handle);
    if (end < 0L || fseek(handle, 0L, SEEK_SET) != 0) {
        (void)fclose(handle);
        return 0;
    }
    memory = end == 0L ? NULL : (uint8_t *)malloc((size_t)end);
    if (memory == NULL && end != 0L) {
        (void)fclose(handle);
        return 0;
    }
    if (end != 0L && fread(memory, 1U, (size_t)end, handle) != (size_t)end) {
        free(memory);
        (void)fclose(handle);
        return 0;
    }
    if (fclose(handle) != 0) {
        free(memory);
        return 0;
    }
    *data = memory;
    *length = (size_t)end;
    return 1;
}

static void make_source(uint8_t source[TEST_SOURCE_BYTES])
{
    uint32_t state = 0x13579BDFU;
    size_t index;

    memset(source, 'A', TEST_CHUNK_BYTES);
    for (index = TEST_CHUNK_BYTES; index < 2U * TEST_CHUNK_BYTES; ++index) {
        state = state * 1664525U + 1013904223U;
        source[index] = (uint8_t)(state >> 24U);
    }
    memset(source + 2U * TEST_CHUNK_BYTES, 'B', TEST_CHUNK_BYTES);
}

static int make_fixture(const char *path,
                        const uint8_t *source,
                        size_t source_bytes,
                        size_t chunk_size)
{
    uint8_t header[PR_HEADER_BYTES];
    uint8_t table[3U * PR_ENTRY_BYTES];
    uint8_t stored[3U][128U];
#if defined(NR_HAVE_ZLIB)
    uint8_t compressed[3U][128U];
#endif
    size_t stored_bytes[3U];
    uint8_t codecs[3U] = {0U, 0U, 0U};
    size_t count = source_bytes == 0U ? 0U : (source_bytes + chunk_size - 1U) / chunk_size;
    size_t index;
    uint64_t payload_offset = PR_HEADER_BYTES + PR_ENTRY_BYTES * count;
    uint8_t source_digest[NPRQ_SHA256_BYTES];
    FILE *handle;

    if (count > 3U || chunk_size == 0U || source_bytes > sizeof(stored[0]) * 3U ||
        nprq_sha256_bytes(source, source_bytes, source_digest) != NPRQ_OK) {
        return 0;
    }
    memset(header, 0, sizeof(header));
    memcpy(header, "NRPQR001", 8U);
    put_u16(header + 8U, 1U);
    put_u16(header + 10U, 0U);
    put_u32(header + 12U, (uint32_t)chunk_size);
    put_u64(header + 16U, (uint64_t)source_bytes);
    put_u64(header + 24U, (uint64_t)count);
    memcpy(header + 32U, source_digest, NPRQ_SHA256_BYTES);
    memset(table, 0, sizeof(table));
    for (index = 0U; index < count; ++index) {
        size_t raw_bytes = source_bytes - index * chunk_size;
#if defined(NR_HAVE_ZLIB)
        uLongf compressed_bytes;
#endif

        if (raw_bytes > chunk_size) {
            raw_bytes = chunk_size;
        }
        memcpy(stored[index], source + index * chunk_size, raw_bytes);
        stored_bytes[index] = raw_bytes;
#if defined(NR_HAVE_ZLIB)
        compressed_bytes = (uLongf)sizeof(compressed[index]);
        if (compress2(compressed[index], &compressed_bytes,
                      source + index * chunk_size, (uLong)raw_bytes, 9) == Z_OK &&
            compressed_bytes < (uLongf)raw_bytes) {
            stored_bytes[index] = (size_t)compressed_bytes;
            memcpy(stored[index], compressed[index], stored_bytes[index]);
            codecs[index] = 1U;
        }
#endif
        put_u64(table + index * PR_ENTRY_BYTES, payload_offset);
        put_u64(table + index * PR_ENTRY_BYTES + 8U, (uint64_t)stored_bytes[index]);
        put_u64(table + index * PR_ENTRY_BYTES + 16U, (uint64_t)raw_bytes);
        put_u32(table + index * PR_ENTRY_BYTES + 24U,
                pr_crc32(source + index * chunk_size, raw_bytes));
        table[index * PR_ENTRY_BYTES + 28U] = codecs[index];
        if (nprq_sha256_bytes(source + index * chunk_size, raw_bytes,
                              table + index * PR_ENTRY_BYTES + 32U) != NPRQ_OK) {
            return 0;
        }
        payload_offset += stored_bytes[index];
    }
    handle = fopen(path, "wb");
    if (handle == NULL || fwrite(header, 1U, sizeof(header), handle) != sizeof(header) ||
        fwrite(table, 1U, PR_ENTRY_BYTES * count, handle) != PR_ENTRY_BYTES * count) {
        if (handle != NULL) {
            (void)fclose(handle);
        }
        return 0;
    }
    for (index = 0U; index < count; ++index) {
        size_t raw_bytes = source_bytes - index * chunk_size;
        if (raw_bytes > chunk_size) {
            raw_bytes = chunk_size;
        }
        if (fwrite(stored[index], 1U, stored_bytes[index], handle) != stored_bytes[index]) {
            (void)fclose(handle);
            return 0;
        }
        (void)raw_bytes;
    }
    return fclose(handle) == 0;
}

#if defined(NR_HAVE_ZLIB)
static int make_expansion_bomb(const char *path)
{
    uint8_t raw[64];
    uint8_t bomb[4096];
    uint8_t compressed[128];
    uint8_t header[PR_HEADER_BYTES];
    uint8_t entry[PR_ENTRY_BYTES];
    uint8_t digest[NPRQ_SHA256_BYTES];
    uLongf compressed_bytes = sizeof(compressed);
    FILE *handle;

    memset(raw, 'A', sizeof(raw));
    memset(bomb, 'B', sizeof(bomb));
    if (compress2(compressed, &compressed_bytes, bomb, sizeof(bomb), 9) != Z_OK ||
        compressed_bytes >= sizeof(raw) ||
        nprq_sha256_bytes(raw, sizeof(raw), digest) != NPRQ_OK) {
        return 0;
    }
    memset(header, 0, sizeof(header));
    memcpy(header, "NRPQR001", 8U);
    put_u16(header + 8U, 1U);
    put_u32(header + 12U, 64U);
    put_u64(header + 16U, 64U);
    put_u64(header + 24U, 1U);
    memcpy(header + 32U, digest, sizeof(digest));
    memset(entry, 0, sizeof(entry));
    put_u64(entry, PR_HEADER_BYTES + PR_ENTRY_BYTES);
    put_u64(entry + 8U, compressed_bytes);
    put_u64(entry + 16U, sizeof(raw));
    put_u32(entry + 24U, pr_crc32(raw, sizeof(raw)));
    entry[28] = 1U;
    memcpy(entry + 32U, digest, sizeof(digest));
    handle = fopen(path, "wb");
    if (handle == NULL || fwrite(header, 1U, sizeof(header), handle) != sizeof(header) ||
        fwrite(entry, 1U, sizeof(entry), handle) != sizeof(entry) ||
        fwrite(compressed, 1U, compressed_bytes, handle) != compressed_bytes) {
        if (handle != NULL) {
            (void)fclose(handle);
        }
        return 0;
    }
    return fclose(handle) == 0;
}
#endif

static void test_roundtrip_and_bounds(void)
{
    uint8_t source[TEST_SOURCE_BYTES];
    uint8_t range[220];
    uint8_t small[10];
    uint8_t *chunk = NULL;
    size_t chunk_bytes = 0U;
    size_t range_bytes = 0U;
    pr_reader reader;
    pr_chunk_info info;
    pr_limits limits;
    static const uint64_t order[3] = {2U, 0U, 1U};
    size_t index;

    make_source(source);
    CHECK(make_fixture(FIXTURE, source, sizeof(source), TEST_CHUNK_BYTES));
    CHECK(pr_open(&reader, FIXTURE, NULL) == PR_OK);
    CHECK(reader.info.chunk_count == 3U && reader.info.chunk_size == TEST_CHUNK_BYTES);
    {
        pr_status verify_status = pr_verify(&reader);
        if (verify_status != PR_OK) {
            fprintf(stderr, "verify status: %s\n", pr_status_string(verify_status));
        }
        CHECK(verify_status == PR_OK);
    }
    for (index = 0U; index < 3U; ++index) {
        pr_status chunk_status = pr_read_chunk_alloc(&reader, order[index], &chunk, &chunk_bytes);
        if (chunk_status != PR_OK) {
            fprintf(stderr, "chunk %llu status: %s\n",
                    (unsigned long long)order[index], pr_status_string(chunk_status));
        }
        CHECK(chunk_status == PR_OK);
        CHECK(chunk_bytes == TEST_CHUNK_BYTES &&
              memcmp(chunk, source + order[index] * TEST_CHUNK_BYTES, chunk_bytes) == 0);
        free(chunk);
        chunk = NULL;
    }
    CHECK(pr_read_range(&reader, 41U, 200U, range, sizeof(range), &range_bytes) == PR_OK);
    CHECK(range_bytes == 200U && memcmp(range, source + 41U, 200U) == 0);
    CHECK(pr_read_chunk(&reader, 0U, small, sizeof(small), &chunk_bytes) == PR_ERR_OUTPUT);
    CHECK(pr_read_chunk(&reader, 3U, range, sizeof(range), &chunk_bytes) == PR_ERR_INDEX);
    CHECK(pr_get_chunk_info(&reader, 1U, &info) == PR_OK && info.index == 1U);
    CHECK(pr_read_range(&reader, 0U, 11U, small, sizeof(small), &range_bytes) == PR_ERR_BOUNDS);
    CHECK(pr_read_range(&reader, 300U, 0U, range, sizeof(range), &range_bytes) == PR_OK);
    CHECK(range_bytes == 0U);
    CHECK(pr_close(&reader) == PR_OK);

    pr_default_limits(&limits);
    limits.max_source_bytes = 0U;
    CHECK(pr_open(&reader, FIXTURE, &limits) == PR_ERR_FORMAT);
    pr_default_limits(&limits);
    limits.max_chunk_bytes = 8U;
    CHECK(pr_open(&reader, FIXTURE, &limits) == PR_ERR_FORMAT);
}

static void test_corruption(void)
{
    uint8_t *data = NULL;
    size_t length = 0U;
    uint8_t source[TEST_SOURCE_BYTES];
    pr_reader reader;
    pr_chunk_info info = {0};
    uint8_t output[TEST_CHUNK_BYTES];
    size_t output_bytes = 0U;

    make_source(source);
    CHECK(read_file(FIXTURE, &data, &length));
    CHECK(pr_open(&reader, FIXTURE, NULL) == PR_OK);
    CHECK(pr_get_chunk_info(&reader, 0U, &info) == PR_OK);
    CHECK(pr_close(&reader) == PR_OK);
    if (data != NULL && info.offset < length) {
        data[(size_t)info.offset] ^= 1U;
    }
    CHECK(write_file(CORRUPT, data, length));
    free(data);
    data = NULL;
    CHECK(pr_open(&reader, CORRUPT, NULL) == PR_OK);
    {
        pr_status corruption_status = pr_read_chunk(&reader, 0U, output,
                                                    sizeof(output), &output_bytes);
        CHECK(corruption_status == PR_ERR_CHECKSUM || corruption_status == PR_ERR_ZLIB);
    }
    CHECK(pr_close(&reader) == PR_OK);
    CHECK(read_file(FIXTURE, &data, &length));
    CHECK(length > 0U);
    CHECK(write_file(TRUNCATED, data, length - 1U));
    CHECK(pr_open(&reader, TRUNCATED, NULL) != PR_OK);
    CHECK(write_file(TRAILING, data, length));
    free(data);
    data = NULL;
    CHECK(read_file(TRAILING, &data, &length));
    {
        uint8_t *extended = (uint8_t *)realloc(data, length + 1U);
        CHECK(extended != NULL);
        if (extended != NULL) {
            data = extended;
            data[length] = 0xA5U;
            CHECK(write_file(TRAILING, data, length + 1U));
        }
    }
    free(data);
    CHECK(pr_open(&reader, TRAILING, NULL) != PR_OK);
    (void)source;
}

static void test_empty_and_zlib_bound(void)
{
    pr_reader reader;

    CHECK(make_fixture(EMPTY, NULL, 0U, 16U));
    CHECK(pr_open(&reader, EMPTY, NULL) == PR_OK);
    CHECK(reader.info.chunk_count == 0U && pr_verify(&reader) == PR_OK);
    CHECK(pr_close(&reader) == PR_OK);
#if defined(NR_HAVE_ZLIB)
    CHECK(make_expansion_bomb(BOMB));
    CHECK(pr_open(&reader, BOMB, NULL) == PR_OK);
    {
        uint8_t output[64];
        size_t output_bytes = 0U;
        CHECK(pr_read_chunk(&reader, 0U, output, sizeof(output), &output_bytes) == PR_ERR_ZLIB);
    }
    CHECK(pr_close(&reader) == PR_OK);
#endif
}

int main(void)
{
    CHECK(pr_crc32((const uint8_t *)"123456789", 9U) == 0xCBF43926U);
    test_roundtrip_and_bounds();
    test_corruption();
    test_empty_and_zlib_bound();
    (void)remove(FIXTURE);
    (void)remove(CORRUPT);
    (void)remove(TRUNCATED);
    (void)remove(TRAILING);
    (void)remove(BOMB);
    (void)remove(EMPTY);
    if (failures != 0) {
        fprintf(stderr, "%d Pocket Rocket test(s) failed\n", failures);
        return EXIT_FAILURE;
    }
    puts("Pocket Rocket tests: PASS");
    return EXIT_SUCCESS;
}
