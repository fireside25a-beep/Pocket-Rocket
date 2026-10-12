#include "pocket_rocket.h"

#include <limits.h>
#include <stdlib.h>
#include <string.h>

#if defined(NR_HAVE_ZLIB)
#include <zlib.h>
#endif

static uint16_t load_u16(const uint8_t *bytes)
{
    return (uint16_t)((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8U));
}

static uint32_t load_u32(const uint8_t *bytes)
{
    return ((uint32_t)bytes[0]) | ((uint32_t)bytes[1] << 8U) |
           ((uint32_t)bytes[2] << 16U) | ((uint32_t)bytes[3] << 24U);
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

static int ceil_div_u64(uint64_t value, uint64_t divisor, uint64_t *result)
{
    uint64_t quotient;

    if (result == NULL || divisor == 0U) {
        return 0;
    }
    quotient = value / divisor;
    if ((value % divisor) != 0U) {
        if (quotient == UINT64_MAX) {
            return 0;
        }
        ++quotient;
    }
    *result = quotient;
    return 1;
}

static pr_status stream_size(FILE *handle, uint64_t *size)
{
    long position;

    if (handle == NULL || size == NULL || fseek(handle, 0L, SEEK_END) != 0) {
        return PR_ERR_IO;
    }
    position = ftell(handle);
    if (position < 0L || fseek(handle, 0L, SEEK_SET) != 0) {
        return PR_ERR_IO;
    }
    *size = (uint64_t)position;
    return PR_OK;
}

static pr_status read_at(const pr_reader *reader,
                         uint64_t offset,
                         uint8_t *buffer,
                         size_t length)
{
    if (reader == NULL || reader->handle == NULL ||
        (buffer == NULL && length != 0U) || offset > reader->file_size ||
        (uint64_t)length > reader->file_size - offset) {
        return PR_ERR_BOUNDS;
    }
    if (fseek(reader->handle, (long)offset, SEEK_SET) != 0) {
        return PR_ERR_IO;
    }
    if (length != 0U && fread(buffer, 1U, length, reader->handle) != length) {
        return PR_ERR_IO;
    }
    return PR_OK;
}

static pr_status parse_entry(const uint8_t raw[PR_ENTRY_BYTES],
                             uint64_t index,
                             const pr_reader *reader,
                             pr_chunk_info *chunk)
{
    uint64_t chunk_start;
    uint64_t expected_raw;
    uint64_t end;

    if (raw == NULL || reader == NULL || chunk == NULL ||
        index >= reader->info.chunk_count) {
        return PR_ERR_ARGUMENT;
    }
    if (!mul_u64(index, reader->info.chunk_size, &chunk_start)) {
        return PR_ERR_BOUNDS;
    }
    expected_raw = reader->info.source_bytes - chunk_start;
    if (expected_raw > reader->info.chunk_size) {
        expected_raw = reader->info.chunk_size;
    }
    chunk->index = index;
    chunk->offset = load_u64(raw);
    chunk->stored_bytes = load_u64(raw + 8U);
    chunk->raw_bytes = load_u64(raw + 16U);
    chunk->crc32 = load_u32(raw + 24U);
    chunk->codec = raw[28];
    memcpy(chunk->sha256, raw + 32U, NPRQ_SHA256_BYTES);
    if (expected_raw == 0U || chunk->raw_bytes != expected_raw ||
        chunk->stored_bytes == 0U || chunk->codec > 1U) {
        return PR_ERR_FORMAT;
    }
    if (chunk->codec == 0U && chunk->stored_bytes != chunk->raw_bytes) {
        return PR_ERR_FORMAT;
    }
    if (chunk->codec == 1U && chunk->stored_bytes >= chunk->raw_bytes) {
        return PR_ERR_FORMAT;
    }
    if (chunk->stored_bytes > reader->file_size ||
        chunk->offset > reader->file_size - chunk->stored_bytes) {
        return PR_ERR_BOUNDS;
    }
    if (!add_u64(chunk->offset, chunk->stored_bytes, &end)) {
        return PR_ERR_BOUNDS;
    }
    (void)end;
    return PR_OK;
}

static pr_status read_entry(const pr_reader *reader,
                            uint64_t index,
                            pr_chunk_info *chunk)
{
    uint8_t raw[PR_ENTRY_BYTES];
    uint64_t entry_offset;
    pr_status status;

    if (reader == NULL || chunk == NULL || index >= reader->info.chunk_count) {
        return PR_ERR_INDEX;
    }
    if (!mul_u64(index, PR_ENTRY_BYTES, &entry_offset) ||
        !add_u64(PR_HEADER_BYTES, entry_offset, &entry_offset)) {
        return PR_ERR_BOUNDS;
    }
    status = read_at(reader, entry_offset, raw, sizeof(raw));
    if (status != PR_OK) {
        return status;
    }
    return parse_entry(raw, index, reader, chunk);
}

static pr_status validate_index(const pr_reader *reader)
{
    uint64_t index;
    uint64_t table_bytes;
    uint64_t payload_start;
    uint64_t previous_end;

    if (!mul_u64(reader->info.chunk_count, PR_ENTRY_BYTES, &table_bytes) ||
        !add_u64(PR_HEADER_BYTES, table_bytes, &payload_start) ||
        payload_start > reader->file_size) {
        return PR_ERR_SIZE;
    }
    previous_end = payload_start;
    for (index = 0U; index < reader->info.chunk_count; ++index) {
        pr_chunk_info chunk;
        pr_status status = read_entry(reader, index, &chunk);
        uint64_t end;

        if (status != PR_OK) {
            return status;
        }
        if (chunk.offset != previous_end ||
            !add_u64(chunk.offset, chunk.stored_bytes, &end)) {
            return PR_ERR_FORMAT;
        }
        previous_end = end;
    }
    return previous_end == reader->file_size ? PR_OK : PR_ERR_SIZE;
}

void pr_default_limits(pr_limits *limits)
{
    if (limits != NULL) {
        limits->max_source_bytes = PR_DEFAULT_MAX_SOURCE_BYTES;
        limits->max_chunk_bytes = PR_MAX_CHUNK_BYTES;
        limits->max_range_bytes = PR_DEFAULT_MAX_RANGE_BYTES;
    }
}

pr_status pr_open(pr_reader *reader, const char *path, const pr_limits *limits)
{
    uint8_t header[PR_HEADER_BYTES];
    uint64_t expected_count;
    uint64_t table_bytes;
    pr_limits selected;
    pr_status status;

    if (reader == NULL || path == NULL) {
        return PR_ERR_ARGUMENT;
    }
    memset(reader, 0, sizeof(*reader));
    if (limits == NULL) {
        pr_default_limits(&selected);
    } else {
        selected = *limits;
    }
    if (selected.max_chunk_bytes == 0U || selected.max_chunk_bytes > PR_MAX_CHUNK_BYTES) {
        return PR_ERR_BOUNDS;
    }
    reader->limits = selected;
    reader->handle = fopen(path, "rb");
    if (reader->handle == NULL) {
        return PR_ERR_IO;
    }
    status = stream_size(reader->handle, &reader->file_size);
    if (status != PR_OK || reader->file_size < PR_HEADER_BYTES) {
        (void)pr_close(reader);
        return status == PR_OK ? PR_ERR_SIZE : status;
    }
    status = read_at(reader, 0U, header, sizeof(header));
    if (status != PR_OK) {
        (void)pr_close(reader);
        return status;
    }
    if (memcmp(header, "NRPQR001", 8U) != 0 || load_u16(header + 8U) != 1U ||
        load_u16(header + 10U) != 0U) {
        (void)pr_close(reader);
        return PR_ERR_FORMAT;
    }
    reader->info.chunk_size = load_u32(header + 12U);
    reader->info.source_bytes = load_u64(header + 16U);
    reader->info.chunk_count = load_u64(header + 24U);
    memcpy(reader->info.source_sha256, header + 32U, NPRQ_SHA256_BYTES);
    if (reader->info.chunk_size == 0U ||
        reader->info.chunk_size > reader->limits.max_chunk_bytes ||
        reader->info.chunk_size > PR_MAX_CHUNK_BYTES ||
        reader->info.source_bytes > reader->limits.max_source_bytes ||
        !ceil_div_u64(reader->info.source_bytes, reader->info.chunk_size,
                      &expected_count) || reader->info.chunk_count != expected_count ||
        !mul_u64(reader->info.chunk_count, PR_ENTRY_BYTES, &table_bytes) ||
        table_bytes > reader->file_size - PR_HEADER_BYTES) {
        (void)pr_close(reader);
        return PR_ERR_FORMAT;
    }
    status = validate_index(reader);
    if (status != PR_OK) {
        (void)pr_close(reader);
        return status;
    }
    reader->info.container_bytes = reader->file_size;
    return PR_OK;
}

pr_status pr_close(pr_reader *reader)
{
    int close_status;

    if (reader == NULL) {
        return PR_ERR_ARGUMENT;
    }
    if (reader->handle == NULL) {
        return PR_OK;
    }
    close_status = fclose(reader->handle);
    reader->handle = NULL;
    return close_status == 0 ? PR_OK : PR_ERR_IO;
}

pr_status pr_get_chunk_info(const pr_reader *reader,
                            uint64_t index,
                            pr_chunk_info *chunk)
{
    if (reader == NULL || chunk == NULL) {
        return PR_ERR_ARGUMENT;
    }
    return read_entry(reader, index, chunk);
}

uint32_t pr_crc32(const uint8_t *data, size_t length)
{
    uint32_t crc = 0xFFFFFFFFU;
    size_t index;

    if (data == NULL && length != 0U) {
        return 0U;
    }
    for (index = 0U; index < length; ++index) {
        unsigned int bit;
        crc ^= (uint32_t)data[index];
        for (bit = 0U; bit < 8U; ++bit) {
            crc = (crc & 1U) != 0U ? (crc >> 1U) ^ 0xEDB88320U : crc >> 1U;
        }
    }
    return ~crc;
}

static pr_status authenticate_chunk(const pr_chunk_info *chunk,
                                    const uint8_t *raw,
                                    size_t raw_bytes)
{
    uint8_t digest[NPRQ_SHA256_BYTES];
    unsigned int difference = 0U;
    size_t index;
    nprq_status hash_status;

    if (chunk == NULL || (raw == NULL && raw_bytes != 0U)) {
        return PR_ERR_ARGUMENT;
    }
    if (pr_crc32(raw, raw_bytes) != chunk->crc32) {
        return PR_ERR_CHECKSUM;
    }
    hash_status = nprq_sha256_bytes(raw, raw_bytes, digest);
    if (hash_status != NPRQ_OK) {
        return PR_ERR_CHECKSUM;
    }
    for (index = 0U; index < NPRQ_SHA256_BYTES; ++index) {
        difference |= (unsigned int)(digest[index] ^ chunk->sha256[index]);
    }
    return difference == 0U ? PR_OK : PR_ERR_CHECKSUM;
}

static pr_status decode_zlib(const pr_reader *reader,
                             const pr_chunk_info *chunk,
                             uint8_t *output)
{
#if defined(NR_HAVE_ZLIB)
    uint8_t *stored;
    z_stream stream;
    int result;
    pr_status status;

    if (chunk->stored_bytes > (uint64_t)SIZE_MAX ||
        chunk->raw_bytes > (uint64_t)UINT_MAX) {
        return PR_ERR_BOUNDS;
    }
    stored = (uint8_t *)malloc((size_t)chunk->stored_bytes);
    if (stored == NULL) {
        return PR_ERR_MEMORY;
    }
    status = read_at(reader, chunk->offset, stored, (size_t)chunk->stored_bytes);
    if (status != PR_OK) {
        free(stored);
        return status;
    }
    memset(&stream, 0, sizeof(stream));
    result = inflateInit(&stream);
    if (result != Z_OK) {
        free(stored);
        return PR_ERR_ZLIB;
    }
    stream.next_in = stored;
    stream.avail_in = (uInt)chunk->stored_bytes;
    stream.next_out = output;
    stream.avail_out = (uInt)chunk->raw_bytes;
    result = inflate(&stream, Z_FINISH);
    status = result == Z_STREAM_END && stream.avail_in == 0U &&
                     stream.avail_out == 0U ? PR_OK : PR_ERR_ZLIB;
    if (inflateEnd(&stream) != Z_OK && status == PR_OK) {
        status = PR_ERR_ZLIB;
    }
    free(stored);
    return status;
#else
    (void)reader;
    (void)chunk;
    (void)output;
    return PR_ERR_ZLIB_UNAVAILABLE;
#endif
}

pr_status pr_read_chunk(const pr_reader *reader,
                        uint64_t index,
                        uint8_t *output,
                        size_t output_capacity,
                        size_t *output_bytes)
{
    pr_chunk_info chunk;
    pr_status status;

    if (output_bytes == NULL || reader == NULL ||
        (output == NULL && output_capacity != 0U)) {
        return PR_ERR_ARGUMENT;
    }
    *output_bytes = 0U;
    status = pr_get_chunk_info(reader, index, &chunk);
    if (status != PR_OK) {
        return status;
    }
    if (chunk.raw_bytes > (uint64_t)SIZE_MAX) {
        return PR_ERR_BOUNDS;
    }
    if (output_capacity < (size_t)chunk.raw_bytes || output == NULL) {
        return PR_ERR_OUTPUT;
    }
    if (chunk.codec == 0U) {
        status = read_at(reader, chunk.offset, output, (size_t)chunk.raw_bytes);
    } else {
        status = decode_zlib(reader, &chunk, output);
    }
    if (status != PR_OK) {
        return status;
    }
    status = authenticate_chunk(&chunk, output, (size_t)chunk.raw_bytes);
    if (status == PR_OK) {
        *output_bytes = (size_t)chunk.raw_bytes;
    }
    return status;
}

pr_status pr_read_chunk_alloc(const pr_reader *reader,
                              uint64_t index,
                              uint8_t **output,
                              size_t *output_bytes)
{
    pr_chunk_info chunk;
    uint8_t *memory;
    size_t length;
    pr_status status;

    if (output == NULL || output_bytes == NULL || reader == NULL) {
        return PR_ERR_ARGUMENT;
    }
    *output = NULL;
    *output_bytes = 0U;
    status = pr_get_chunk_info(reader, index, &chunk);
    if (status != PR_OK || chunk.raw_bytes > (uint64_t)SIZE_MAX) {
        return status == PR_OK ? PR_ERR_BOUNDS : status;
    }
    memory = (uint8_t *)malloc((size_t)chunk.raw_bytes);
    if (memory == NULL) {
        return PR_ERR_MEMORY;
    }
    status = pr_read_chunk(reader, index, memory, (size_t)chunk.raw_bytes, &length);
    if (status != PR_OK) {
        free(memory);
        return status;
    }
    *output = memory;
    *output_bytes = length;
    return PR_OK;
}

pr_status pr_read_range(const pr_reader *reader,
                        uint64_t offset,
                        uint64_t length,
                        uint8_t *output,
                        size_t output_capacity,
                        size_t *output_bytes)
{
    uint64_t last;
    uint64_t first;
    uint64_t index;
    uint64_t end;
    uint8_t *chunk_buffer;
    size_t written = 0U;
    pr_status status = PR_OK;

    if (output_bytes == NULL || reader == NULL ||
        (output == NULL && length != 0U)) {
        return PR_ERR_ARGUMENT;
    }
    *output_bytes = 0U;
    if (length > reader->limits.max_range_bytes ||
        length > (uint64_t)SIZE_MAX || offset > reader->info.source_bytes ||
        length > reader->info.source_bytes - offset ||
        output_capacity < (size_t)length) {
        return PR_ERR_BOUNDS;
    }
    if (length == 0U) {
        return PR_OK;
    }
    if (!add_u64(offset, length, &end)) {
        return PR_ERR_BOUNDS;
    }
    first = offset / reader->info.chunk_size;
    last = (end - 1U) / reader->info.chunk_size;
    if (reader->info.chunk_size > (uint64_t)SIZE_MAX) {
        return PR_ERR_BOUNDS;
    }
    chunk_buffer = (uint8_t *)malloc((size_t)reader->info.chunk_size);
    if (chunk_buffer == NULL) {
        return PR_ERR_MEMORY;
    }
    for (index = first; index <= last; ++index) {
        size_t decoded;
        uint64_t chunk_start = index * reader->info.chunk_size;
        uint64_t copy_start = offset > chunk_start ? offset - chunk_start : 0U;
        uint64_t copy_end = end - chunk_start;
        if (copy_end > reader->info.chunk_size) {
            copy_end = reader->info.chunk_size;
        }
        status = pr_read_chunk(reader, index, chunk_buffer,
                               (size_t)reader->info.chunk_size, &decoded);
        if (status != PR_OK || copy_start > (uint64_t)decoded ||
            copy_end > (uint64_t)decoded || copy_start > copy_end ||
            copy_end - copy_start > (uint64_t)SIZE_MAX - written) {
            status = status == PR_OK ? PR_ERR_FORMAT : status;
            break;
        }
        memcpy(output + written, chunk_buffer + (size_t)copy_start,
               (size_t)(copy_end - copy_start));
        written += (size_t)(copy_end - copy_start);
        if (index == UINT64_MAX) {
            status = PR_ERR_BOUNDS;
            break;
        }
    }
    free(chunk_buffer);
    if (status == PR_OK && written == (size_t)length) {
        *output_bytes = written;
        return PR_OK;
    }
    return status == PR_OK ? PR_ERR_FORMAT : status;
}

pr_status pr_verify(const pr_reader *reader)
{
    nprq_sha256_context context;
    uint8_t digest[NPRQ_SHA256_BYTES];
    uint8_t *chunk_buffer;
    uint64_t index;
    uint64_t total = 0U;
    unsigned int difference = 0U;
    size_t decoded;
    size_t byte_index;
    pr_status status;

    if (reader == NULL) {
        return PR_ERR_ARGUMENT;
    }
    if (reader->info.chunk_size > (uint64_t)SIZE_MAX) {
        return PR_ERR_BOUNDS;
    }
    chunk_buffer = (uint8_t *)malloc((size_t)reader->info.chunk_size);
    if (chunk_buffer == NULL && reader->info.chunk_count != 0U) {
        return PR_ERR_MEMORY;
    }
    nprq_sha256_init(&context);
    for (index = 0U; index < reader->info.chunk_count; ++index) {
        status = pr_read_chunk(reader, index, chunk_buffer,
                               (size_t)reader->info.chunk_size, &decoded);
        if (status != PR_OK || !add_u64(total, (uint64_t)decoded, &total) ||
            nprq_sha256_update(&context, chunk_buffer, decoded) != NPRQ_OK) {
            free(chunk_buffer);
            return status == PR_OK ? PR_ERR_CHECKSUM : status;
        }
    }
    free(chunk_buffer);
    nprq_sha256_final(&context, digest);
    for (byte_index = 0U; byte_index < NPRQ_SHA256_BYTES; ++byte_index) {
        difference |= (unsigned int)(digest[byte_index] ^
                                     reader->info.source_sha256[byte_index]);
    }
    return total == reader->info.source_bytes && difference == 0U ?
               PR_OK : PR_ERR_CHECKSUM;
}

const char *pr_status_string(pr_status status)
{
    switch (status) {
    case PR_OK: return "ok";
    case PR_ERR_ARGUMENT: return "invalid argument";
    case PR_ERR_IO: return "I/O failure";
    case PR_ERR_SIZE: return "unexpected container size";
    case PR_ERR_FORMAT: return "invalid container format";
    case PR_ERR_BOUNDS: return "bounds exceeded";
    case PR_ERR_MEMORY: return "allocation failure";
    case PR_ERR_ZLIB_UNAVAILABLE: return "zlib unavailable";
    case PR_ERR_ZLIB: return "invalid zlib payload";
    case PR_ERR_CHECKSUM: return "checksum mismatch";
    case PR_ERR_OUTPUT: return "output buffer too small";
    case PR_ERR_INDEX: return "chunk index outside container";
    default: return "unknown status";
    }
}
