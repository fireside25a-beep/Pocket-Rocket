#include "nprq.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static nprq_status page_layout_checked(const nprq_page_spec *spec,
                                       nprq_page_info *info)
{
    uint64_t blocks;
    uint64_t packed_bytes;
    uint64_t record_bytes;
    uint64_t expected;

    if (spec == NULL || info == NULL) {
        return NPRQ_ERR_ARGUMENT;
    }
    if (spec->block_size < NPRQ_V2_MIN_BLOCK_SIZE ||
        spec->block_size > NPRQ_V2_MAX_BLOCK_SIZE ||
        (spec->block_size % 4U) != 0U) {
        return NPRQ_ERR_LIMIT;
    }

    blocks = spec->numel / spec->block_size;
    if ((spec->numel % spec->block_size) != 0U) {
        if (!add_u64(blocks, 1U, &blocks)) {
            return NPRQ_ERR_OVERFLOW;
        }
    }
    packed_bytes = spec->block_size / 4U;
    if (!add_u64(2U, packed_bytes, &record_bytes) ||
        !mul_u64(blocks, record_bytes, &expected)) {
        return NPRQ_ERR_OVERFLOW;
    }
    info->block_count = blocks;
    info->record_bytes = record_bytes;
    info->expected_file_bytes = expected;
    return NPRQ_OK;
}

nprq_status nprq_page_layout(const nprq_page_spec *spec,
                             nprq_page_info *info)
{
    return page_layout_checked(spec, info);
}

static nprq_status stream_size(FILE *stream, uint64_t *size)
{
    long position;

    if (stream == NULL || size == NULL) {
        return NPRQ_ERR_ARGUMENT;
    }
    if (fseek(stream, 0L, SEEK_END) != 0) {
        return NPRQ_ERR_IO;
    }
    position = ftell(stream);
    if (position < 0L) {
        return NPRQ_ERR_IO;
    }
    if (fseek(stream, 0L, SEEK_SET) != 0) {
        return NPRQ_ERR_IO;
    }
    *size = (uint64_t)position;
    return NPRQ_OK;
}

static int read_exact(FILE *stream, void *buffer, size_t bytes)
{
    return bytes == 0U || fread(buffer, 1U, bytes, stream) == bytes;
}

typedef nprq_sha256_context sha256_context;

static uint32_t sha256_rotate_right(uint32_t value, unsigned int amount)
{
    return (value >> amount) | (value << (32U - amount));
}

static uint32_t sha256_load_be(const unsigned char *bytes)
{
    return ((uint32_t)bytes[0] << 24U) |
           ((uint32_t)bytes[1] << 16U) |
           ((uint32_t)bytes[2] << 8U) |
           (uint32_t)bytes[3];
}

static void sha256_store_be(uint32_t value, unsigned char *bytes)
{
    bytes[0] = (unsigned char)(value >> 24U);
    bytes[1] = (unsigned char)(value >> 16U);
    bytes[2] = (unsigned char)(value >> 8U);
    bytes[3] = (unsigned char)value;
}

static void sha256_transform(sha256_context *context)
{
    static const uint32_t constants[64] = {
        0x428A2F98U, 0x71374491U, 0xB5C0FBCFU, 0xE9B5DBA5U,
        0x3956C25BU, 0x59F111F1U, 0x923F82A4U, 0xAB1C5ED5U,
        0xD807AA98U, 0x12835B01U, 0x243185BEU, 0x550C7DC3U,
        0x72BE5D74U, 0x80DEB1FEU, 0x9BDC06A7U, 0xC19BF174U,
        0xE49B69C1U, 0xEFBE4786U, 0x0FC19DC6U, 0x240CA1CCU,
        0x2DE92C6FU, 0x4A7484AAU, 0x5CB0A9DCU, 0x76F988DAU,
        0x983E5152U, 0xA831C66DU, 0xB00327C8U, 0xBF597FC7U,
        0xC6E00BF3U, 0xD5A79147U, 0x06CA6351U, 0x14292967U,
        0x27B70A85U, 0x2E1B2138U, 0x4D2C6DFCU, 0x53380D13U,
        0x650A7354U, 0x766A0ABBU, 0x81C2C92EU, 0x92722C85U,
        0xA2BFE8A1U, 0xA81A664BU, 0xC24B8B70U, 0xC76C51A3U,
        0xD192E819U, 0xD6990624U, 0xF40E3585U, 0x106AA070U,
        0x19A4C116U, 0x1E376C08U, 0x2748774CU, 0x34B0BCB5U,
        0x391C0CB3U, 0x4ED8AA4AU, 0x5B9CCA4FU, 0x682E6FF3U,
        0x748F82EEU, 0x78A5636FU, 0x84C87814U, 0x8CC70208U,
        0x90BEFFFAU, 0xA4506CEBU, 0xBEF9A3F7U, 0xC67178F2U
    };
    uint32_t words[64];
    uint32_t a;
    uint32_t b;
    uint32_t c;
    uint32_t d;
    uint32_t e;
    uint32_t f;
    uint32_t g;
    uint32_t h;
    size_t index;

    for (index = 0U; index < 16U; ++index) {
        words[index] = sha256_load_be(context->block + index * 4U);
    }
    for (index = 16U; index < 64U; ++index) {
        uint32_t s0 = sha256_rotate_right(words[index - 15U], 7U) ^
                      sha256_rotate_right(words[index - 15U], 18U) ^
                      (words[index - 15U] >> 3U);
        uint32_t s1 = sha256_rotate_right(words[index - 2U], 17U) ^
                      sha256_rotate_right(words[index - 2U], 19U) ^
                      (words[index - 2U] >> 10U);
        words[index] = words[index - 16U] + s0 + words[index - 7U] + s1;
    }
    a = context->state[0];
    b = context->state[1];
    c = context->state[2];
    d = context->state[3];
    e = context->state[4];
    f = context->state[5];
    g = context->state[6];
    h = context->state[7];
    for (index = 0U; index < 64U; ++index) {
        uint32_t s1 = sha256_rotate_right(e, 6U) ^
                      sha256_rotate_right(e, 11U) ^
                      sha256_rotate_right(e, 25U);
        uint32_t choose = (e & f) ^ ((~e) & g);
        uint32_t temporary1 = h + s1 + choose + constants[index] + words[index];
        uint32_t s0 = sha256_rotate_right(a, 2U) ^
                      sha256_rotate_right(a, 13U) ^
                      sha256_rotate_right(a, 22U);
        uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        uint32_t temporary2 = s0 + majority;
        h = g;
        g = f;
        f = e;
        e = d + temporary1;
        d = c;
        c = b;
        b = a;
        a = temporary1 + temporary2;
    }
    context->state[0] += a;
    context->state[1] += b;
    context->state[2] += c;
    context->state[3] += d;
    context->state[4] += e;
    context->state[5] += f;
    context->state[6] += g;
    context->state[7] += h;
}

static void sha256_init(sha256_context *context)
{
    static const uint32_t initial[8] = {
        0x6A09E667U, 0xBB67AE85U, 0x3C6EF372U, 0xA54FF53AU,
        0x510E527FU, 0x9B05688CU, 0x1F83D9ABU, 0x5BE0CD19U
    };
    memcpy(context->state, initial, sizeof(initial));
    context->bit_count = 0U;
    context->block_length = 0U;
}

static int sha256_update(sha256_context *context,
                         const unsigned char *data,
                         size_t length)
{
    size_t consumed = 0U;

    if (length > (size_t)(UINT64_MAX / 8U) ||
        (uint64_t)length > (UINT64_MAX - context->bit_count) / 8U) {
        return 0;
    }
    context->bit_count += (uint64_t)length * 8U;
    while (consumed < length) {
        size_t available = sizeof(context->block) - context->block_length;
        size_t take = length - consumed;
        if (take > available) {
            take = available;
        }
        memcpy(context->block + context->block_length, data + consumed, take);
        context->block_length += take;
        consumed += take;
        if (context->block_length == sizeof(context->block)) {
            sha256_transform(context);
            context->block_length = 0U;
        }
    }
    return 1;
}

static void sha256_final(sha256_context *context,
                         uint8_t digest[NPRQ_SHA256_BYTES])
{
    uint64_t bit_count = context->bit_count;
    size_t index;

    context->block[context->block_length++] = 0x80U;
    if (context->block_length > 56U) {
        while (context->block_length < sizeof(context->block)) {
            context->block[context->block_length++] = 0U;
        }
        sha256_transform(context);
        context->block_length = 0U;
    }
    while (context->block_length < 56U) {
        context->block[context->block_length++] = 0U;
    }
    for (index = 0U; index < 8U; ++index) {
        context->block[63U - index] = (unsigned char)(bit_count >> (index * 8U));
    }
    sha256_transform(context);
    for (index = 0U; index < 8U; ++index) {
        sha256_store_be(context->state[index], digest + index * 4U);
    }
}

void nprq_sha256_init(nprq_sha256_context *context)
{
    if (context != NULL) {
        sha256_init(context);
    }
}

nprq_status nprq_sha256_update(nprq_sha256_context *context,
                               const uint8_t *data,
                               size_t length)
{
    if (context == NULL || (data == NULL && length != 0U)) {
        return NPRQ_ERR_ARGUMENT;
    }
    return sha256_update(context, data, length) ? NPRQ_OK : NPRQ_ERR_OVERFLOW;
}

void nprq_sha256_final(nprq_sha256_context *context,
                       uint8_t digest[NPRQ_SHA256_BYTES])
{
    if (context != NULL && digest != NULL) {
        sha256_final(context, digest);
    }
}

nprq_status nprq_sha256_bytes(const uint8_t *data,
                              size_t length,
                              uint8_t digest[NPRQ_SHA256_BYTES])
{
    sha256_context context;

    if ((data == NULL && length != 0U) || digest == NULL) {
        return NPRQ_ERR_ARGUMENT;
    }
    sha256_init(&context);
    if (!sha256_update(&context, data, length)) {
        return NPRQ_ERR_OVERFLOW;
    }
    sha256_final(&context, digest);
    return NPRQ_OK;
}

nprq_status nprq_sha256_file(const char *path,
                             uint8_t digest[NPRQ_SHA256_BYTES])
{
    unsigned char buffer[65536];
    sha256_context context;
    FILE *stream;
    size_t count;

    if (path == NULL || digest == NULL) {
        return NPRQ_ERR_ARGUMENT;
    }
    stream = fopen(path, "rb");
    if (stream == NULL) {
        return NPRQ_ERR_IO;
    }
    sha256_init(&context);
    while ((count = fread(buffer, 1U, sizeof(buffer), stream)) != 0U) {
        if (!sha256_update(&context, buffer, count)) {
            (void)fclose(stream);
            return NPRQ_ERR_OVERFLOW;
        }
    }
    if (ferror(stream) != 0) {
        (void)fclose(stream);
        return NPRQ_ERR_IO;
    }
    if (fclose(stream) != 0) {
        return NPRQ_ERR_IO;
    }
    sha256_final(&context, digest);
    return NPRQ_OK;
}

static float half_to_float(const unsigned char bytes[2])
{
    uint16_t raw = (uint16_t)((uint16_t)bytes[0] |
                              ((uint16_t)bytes[1] << 8U));
    unsigned int sign = (unsigned int)(raw >> 15U);
    unsigned int exponent = (unsigned int)((raw >> 10U) & 0x1FU);
    unsigned int fraction = (unsigned int)(raw & 0x03FFU);
    float value;

    if (exponent == 31U) {
        /* NPRQ stores finite scales only; both infinity and NaN are invalid. */
        return NAN;
    }
    if (exponent == 0U) {
        /* Subnormal: 2^-14 * fraction / 2^10. */
        value = ldexpf((float)fraction, -24);
    } else {
        value = ldexpf(1.0F + ((float)fraction / 1024.0F),
                       (int)exponent - 15);
    }
    return sign == 0U ? value : -value;
}

static nprq_status validate_stream_records(FILE *stream,
                                            const nprq_page_info *info)
{
    unsigned char *record;
    uint64_t block;
    size_t record_bytes;

    if (stream == NULL || info == NULL) {
        return NPRQ_ERR_ARGUMENT;
    }
    if (info->record_bytes > (uint64_t)SIZE_MAX) {
        return NPRQ_ERR_OVERFLOW;
    }
    record_bytes = (size_t)info->record_bytes;
    record = (unsigned char *)malloc(record_bytes);
    if (record == NULL && record_bytes != 0U) {
        return NPRQ_ERR_MEMORY;
    }
    for (block = 0U; block < info->block_count; ++block) {
        float scale;
        if (!read_exact(stream, record, record_bytes)) {
            free(record);
            return NPRQ_ERR_IO;
        }
        scale = half_to_float(record);
        if (!isfinite(scale)) {
            free(record);
            return NPRQ_ERR_FORMAT;
        }
    }
    free(record);
    return NPRQ_OK;
}

nprq_status nprq_validate_page_file(const char *path,
                                    const nprq_page_spec *spec,
                                    nprq_page_info *info)
{
    FILE *stream;
    nprq_page_info local_info;
    nprq_status status;
    uint64_t actual_size;

    if (path == NULL || spec == NULL) {
        return NPRQ_ERR_ARGUMENT;
    }
    status = page_layout_checked(spec, &local_info);
    if (status != NPRQ_OK) {
        return status;
    }
    stream = fopen(path, "rb");
    if (stream == NULL) {
        return NPRQ_ERR_IO;
    }
    status = stream_size(stream, &actual_size);
    if (status == NPRQ_OK && actual_size != local_info.expected_file_bytes) {
        status = NPRQ_ERR_SIZE;
    }
    if (status == NPRQ_OK) {
        status = validate_stream_records(stream, &local_info);
    }
    if (fclose(stream) != 0 && status == NPRQ_OK) {
        status = NPRQ_ERR_IO;
    }
    if (status == NPRQ_OK && info != NULL) {
        *info = local_info;
    }
    return status;
}

nprq_status nprq_validate_page_file_hash(
    const char *path,
    const nprq_page_spec *spec,
    const uint8_t expected_sha256[NPRQ_SHA256_BYTES],
    nprq_page_info *info)
{
    uint8_t actual[NPRQ_SHA256_BYTES];
    nprq_status status;
    unsigned int difference = 0U;
    size_t index;

    if (expected_sha256 == NULL) {
        return NPRQ_ERR_ARGUMENT;
    }
    status = nprq_validate_page_file(path, spec, info);
    if (status != NPRQ_OK) {
        return status;
    }
    status = nprq_sha256_file(path, actual);
    if (status != NPRQ_OK) {
        return status;
    }
    for (index = 0U; index < NPRQ_SHA256_BYTES; ++index) {
        difference |= (unsigned int)(actual[index] ^ expected_sha256[index]);
    }
    return difference == 0U ? NPRQ_OK : NPRQ_ERR_FORMAT;
}

static nprq_status decode_stream(FILE *stream,
                                 const nprq_page_spec *spec,
                                 const nprq_page_info *info,
                                 float *output)
{
    unsigned char *record;
    uint64_t block;
    size_t record_bytes;
    uint64_t index;
    uint64_t block_start;
    uint64_t element;
    static const float codebook[4] = {-3.0F, -1.0F, 1.0F, 3.0F};

    if (stream == NULL || spec == NULL || info == NULL ||
        (output == NULL && spec->numel != 0U)) {
        return NPRQ_ERR_ARGUMENT;
    }
    if (info->record_bytes > (uint64_t)SIZE_MAX) {
        return NPRQ_ERR_OVERFLOW;
    }
    record_bytes = (size_t)info->record_bytes;
    record = (unsigned char *)malloc(record_bytes);
    if (record == NULL && record_bytes != 0U) {
        return NPRQ_ERR_MEMORY;
    }
    index = 0U;
    for (block = 0U; block < info->block_count; ++block) {
        float scale;
        block_start = block * spec->block_size;
        if (!read_exact(stream, record, record_bytes)) {
            free(record);
            return NPRQ_ERR_IO;
        }
        scale = half_to_float(record);
        if (!isfinite(scale)) {
            free(record);
            return NPRQ_ERR_FORMAT;
        }
        for (element = 0U; element < spec->block_size; ++element) {
            uint64_t absolute = block_start + element;
            unsigned char packed = record[2U + (size_t)(element / 4U)];
            unsigned int code = ((unsigned int)packed >> (2U * (element % 4U))) & 0x03U;
            if (absolute < spec->numel) {
                /* index is bounded by numel and is safe to convert below. */
                output[(size_t)index] = scale * codebook[code];
                ++index;
            }
        }
    }
    free(record);
    return index == spec->numel ? NPRQ_OK : NPRQ_ERR_FORMAT;
}

nprq_status nprq_decode_page_file(const char *path,
                                  const nprq_page_spec *spec,
                                  float *output,
                                  size_t output_count)
{
    FILE *stream;
    nprq_page_info info;
    nprq_status status;

    if (path == NULL || spec == NULL ||
        (spec->numel != 0U && output == NULL)) {
        return NPRQ_ERR_ARGUMENT;
    }
    status = page_layout_checked(spec, &info);
    if (status != NPRQ_OK) {
        return status;
    }
    if (spec->numel > (uint64_t)SIZE_MAX || output_count < (size_t)spec->numel) {
        return NPRQ_ERR_OUTPUT;
    }
    status = nprq_validate_page_file(path, spec, NULL);
    if (status != NPRQ_OK) {
        return status;
    }
    stream = fopen(path, "rb");
    if (stream == NULL) {
        return NPRQ_ERR_IO;
    }
    status = decode_stream(stream, spec, &info, output);
    if (fclose(stream) != 0 && status == NPRQ_OK) {
        status = NPRQ_ERR_IO;
    }
    return status;
}

nprq_status nprq_decode_page_alloc(const char *path,
                                   const nprq_page_spec *spec,
                                   float **output,
                                   size_t *output_count)
{
    float *memory;
    size_t count;
    nprq_status status;

    if (output == NULL || output_count == NULL) {
        return NPRQ_ERR_ARGUMENT;
    }
    *output = NULL;
    *output_count = 0U;
    if (spec == NULL || spec->numel > (uint64_t)SIZE_MAX) {
        return spec == NULL ? NPRQ_ERR_ARGUMENT : NPRQ_ERR_OVERFLOW;
    }
    count = (size_t)spec->numel;
    if (count > SIZE_MAX / sizeof(*memory)) {
        return NPRQ_ERR_OVERFLOW;
    }
    memory = count == 0U ? NULL : (float *)malloc(count * sizeof(*memory));
    if (memory == NULL && count != 0U) {
        return NPRQ_ERR_MEMORY;
    }
    status = nprq_decode_page_file(path, spec, memory, count);
    if (status != NPRQ_OK) {
        free(memory);
        return status;
    }
    *output = memory;
    *output_count = count;
    return NPRQ_OK;
}

static nprq_status ternary_layout(size_t count, size_t packed_bytes)
{
    size_t expected = count / 4U;

    if ((count % 4U) != 0U) {
        if (expected == SIZE_MAX) {
            return NPRQ_ERR_OVERFLOW;
        }
        ++expected;
    }
    return packed_bytes == expected ? NPRQ_OK : NPRQ_ERR_SIZE;
}

nprq_status nprq_validate_ternary_payload(const uint8_t *packed,
                                         size_t packed_bytes,
                                         size_t count)
{
    size_t index;
    nprq_status status = ternary_layout(count, packed_bytes);

    if ((packed == NULL && packed_bytes != 0U) || status != NPRQ_OK) {
        return packed == NULL && packed_bytes != 0U ? NPRQ_ERR_ARGUMENT : status;
    }
    for (index = 0U; index < packed_bytes; ++index) {
        unsigned int symbols[4];
        size_t lane;

        symbols[0] = (unsigned int)(packed[index] & 0x03U);
        symbols[1] = (unsigned int)((packed[index] >> 2U) & 0x03U);
        symbols[2] = (unsigned int)((packed[index] >> 4U) & 0x03U);
        symbols[3] = (unsigned int)((packed[index] >> 6U) & 0x03U);
        for (lane = 0U; lane < 4U; ++lane) {
            size_t absolute;
            if (index > (SIZE_MAX - lane) / 4U) {
                return NPRQ_ERR_OVERFLOW;
            }
            absolute = index * 4U + lane;
            if (absolute >= count) {
                /* The encoder writes the zero symbol (packed value 1). */
                if (symbols[lane] != 1U) {
                    return NPRQ_ERR_FORMAT;
                }
            } else if (symbols[lane] == 3U) {
                return NPRQ_ERR_FORMAT;
            }
        }
    }
    return NPRQ_OK;
}

nprq_status nprq_decode_ternary_payload(const uint8_t *packed,
                                       size_t packed_bytes,
                                       size_t count,
                                       int8_t *output,
                                       size_t output_count)
{
    size_t index;
    nprq_status status;

    if (output == NULL && count != 0U) {
        return NPRQ_ERR_ARGUMENT;
    }
    if (output_count < count) {
        return NPRQ_ERR_OUTPUT;
    }
    status = nprq_validate_ternary_payload(packed, packed_bytes, count);
    if (status != NPRQ_OK) {
        return status;
    }
    for (index = 0U; index < count; ++index) {
        unsigned int packed_value = (unsigned int)packed[index / 4U];
        unsigned int symbol = (packed_value >> (2U * (index % 4U))) & 0x03U;
        output[index] = (int8_t)((int)symbol - 1);
    }
    return NPRQ_OK;
}

const char *nprq_status_string(nprq_status status)
{
    switch (status) {
    case NPRQ_OK: return "ok";
    case NPRQ_ERR_ARGUMENT: return "invalid argument";
    case NPRQ_ERR_OVERFLOW: return "integer overflow";
    case NPRQ_ERR_LIMIT: return "format limit exceeded";
    case NPRQ_ERR_IO: return "I/O failure";
    case NPRQ_ERR_SIZE: return "unexpected page size";
    case NPRQ_ERR_FORMAT: return "invalid page format";
    case NPRQ_ERR_MEMORY: return "allocation failure";
    case NPRQ_ERR_OUTPUT: return "output buffer too small";
    default: return "unknown status";
    }
}

static unsigned int popcount8(unsigned int value)
{
    unsigned int count = 0U;
    while (value != 0U) {
        count += value & 1U;
        value >>= 1U;
    }
    return count;
}

uint16_t nprq_hamming256(const uint8_t left[NPRQ_V2_CODE_BYTES],
                         const uint8_t right[NPRQ_V2_CODE_BYTES])
{
    size_t index;
    unsigned int count = 0U;

    if (left == NULL || right == NULL) {
        return 0U;
    }
    for (index = 0U; index < NPRQ_V2_CODE_BYTES; ++index) {
        count += popcount8((unsigned int)(left[index] ^ right[index]));
    }
    return (uint16_t)count;
}

static int ranked_compare(const void *left, const void *right)
{
    const nprq_ranked_expert *a = (const nprq_ranked_expert *)left;
    const nprq_ranked_expert *b = (const nprq_ranked_expert *)right;
    if (a->distance < b->distance) {
        return -1;
    }
    if (a->distance > b->distance) {
        return 1;
    }
    if (a->expert_id < b->expert_id) {
        return -1;
    }
    if (a->expert_id > b->expert_id) {
        return 1;
    }
    return 0;
}

nprq_status nprq_rank_experts(
    const uint8_t query[NPRQ_V2_CODE_BYTES],
    const uint8_t *centroids,
    size_t expert_count,
    size_t top_k,
    nprq_ranked_expert *out)
{
    nprq_ranked_expert *all;
    size_t index;

    if (query == NULL || centroids == NULL || out == NULL ||
        expert_count == 0U || top_k == 0U || top_k > expert_count) {
        return NPRQ_ERR_ARGUMENT;
    }
    if (expert_count > SIZE_MAX / sizeof(*all) ||
        expert_count > SIZE_MAX / NPRQ_V2_CODE_BYTES) {
        return NPRQ_ERR_OVERFLOW;
    }
    all = (nprq_ranked_expert *)malloc(expert_count * sizeof(*all));
    if (all == NULL) {
        return NPRQ_ERR_MEMORY;
    }
    for (index = 0U; index < expert_count; ++index) {
        all[index].expert_id = index;
        all[index].distance = nprq_hamming256(
            query, centroids + index * NPRQ_V2_CODE_BYTES);
    }
    qsort(all, expert_count, sizeof(*all), ranked_compare);
    for (index = 0U; index < top_k; ++index) {
        out[index] = all[index];
    }
    free(all);
    return NPRQ_OK;
}
