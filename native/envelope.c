#include "envelope.h"

#include <limits.h>
#include <string.h>

static void counter_increment(uint64_t *counter)
{
    if (*counter != UINT64_MAX) {
        ++(*counter);
    }
}

static int ascii_space(uint8_t value)
{
    return value == (uint8_t)' ' || value == (uint8_t)'\t' ||
           value == (uint8_t)'\n' || value == (uint8_t)'\r' ||
           value == (uint8_t)'\f' || value == (uint8_t)'\v';
}

static nr_envelope_status canonical_length(const uint8_t *input,
                                           size_t input_bytes,
                                           size_t *length)
{
    size_t index;
    size_t required = 0U;
    uint8_t started = 0U;
    uint8_t pending_space = 0U;

    if (length == NULL || (input == NULL && input_bytes != 0U)) {
        return NR_ENVELOPE_ERR_ARGUMENT;
    }
    if (input_bytes > NR_ENVELOPE_MAX_INPUT_BYTES) {
        return NR_ENVELOPE_ERR_BOUNDS;
    }
    for (index = 0U; index < input_bytes; ++index) {
        if (ascii_space(input[index])) {
            if (started != 0U) {
                pending_space = 1U;
            }
        } else {
            if (pending_space != 0U) {
                if (required == SIZE_MAX) {
                    return NR_ENVELOPE_ERR_BOUNDS;
                }
                ++required;
                pending_space = 0U;
            }
            if (required == SIZE_MAX) {
                return NR_ENVELOPE_ERR_BOUNDS;
            }
            ++required;
            started = 1U;
        }
    }
    *length = required;
    return NR_ENVELOPE_OK;
}

void nr_envelope_cache_init(nr_envelope_cache *cache)
{
    if (cache != NULL) {
        memset(cache, 0, sizeof(*cache));
        cache->next_sequence = 1U;
    }
}

nr_envelope_status nr_envelope_canonicalize(const uint8_t *input,
                                            size_t input_bytes,
                                            uint8_t *output,
                                            size_t output_capacity,
                                            size_t *canonical_bytes)
{
    size_t required;
    size_t index;
    size_t written = 0U;
    uint8_t started = 0U;
    uint8_t pending_space = 0U;
    nr_envelope_status status;

    if (canonical_bytes == NULL) {
        return NR_ENVELOPE_ERR_ARGUMENT;
    }
    status = canonical_length(input, input_bytes, &required);
    if (status != NR_ENVELOPE_OK) {
        return status;
    }
    *canonical_bytes = required;
    if (required > output_capacity || (output == NULL && required != 0U)) {
        return NR_ENVELOPE_ERR_OUTPUT;
    }
    for (index = 0U; index < input_bytes; ++index) {
        if (ascii_space(input[index])) {
            if (started != 0U) {
                pending_space = 1U;
            }
        } else {
            if (pending_space != 0U) {
                output[written] = (uint8_t)' ';
                ++written;
                pending_space = 0U;
            }
            output[written] = input[index];
            ++written;
            started = 1U;
        }
    }
    return NR_ENVELOPE_OK;
}

nr_envelope_status nr_envelope_key(const uint8_t *input,
                                   size_t input_bytes,
                                   uint8_t key[NPRQ_SHA256_BYTES],
                                   size_t *canonical_bytes)
{
    nprq_status hash_status;

    if (key == NULL || canonical_bytes == NULL ||
        (input == NULL && input_bytes != 0U)) {
        return NR_ENVELOPE_ERR_ARGUMENT;
    }
    if (input_bytes > NR_ENVELOPE_MAX_INPUT_BYTES) {
        return NR_ENVELOPE_ERR_BOUNDS;
    }
    hash_status = nprq_sha256_bytes(input, input_bytes, key);
    if (hash_status != NPRQ_OK) {
        return NR_ENVELOPE_ERR_KEY;
    }
    *canonical_bytes = input_bytes;
    return NR_ENVELOPE_OK;
}

nr_envelope_status nr_envelope_drift_key(const uint8_t *input,
                                         size_t input_bytes,
                                         uint8_t key[NPRQ_SHA256_BYTES],
                                         size_t *canonical_bytes)
{
    static const uint8_t domain[] = "neuro-envelope/whitespace-v1:";
    uint8_t canonical[NR_ENVELOPE_MAX_INPUT_BYTES];
    uint8_t framed[NR_ENVELOPE_MAX_INPUT_BYTES + sizeof(domain) - 1U];
    size_t length;
    nr_envelope_status status;
    nprq_status hash_status;

    if (key == NULL || canonical_bytes == NULL) {
        return NR_ENVELOPE_ERR_ARGUMENT;
    }
    status = nr_envelope_canonicalize(input, input_bytes,
                                       canonical, sizeof(canonical), &length);
    if (status != NR_ENVELOPE_OK) {
        return status;
    }
    if (length > sizeof(framed) - (sizeof(domain) - 1U)) {
        return NR_ENVELOPE_ERR_BOUNDS;
    }
    memcpy(framed, domain, sizeof(domain) - 1U);
    memcpy(framed + sizeof(domain) - 1U, canonical, length);
    hash_status = nprq_sha256_bytes(framed,
                                    (sizeof(domain) - 1U) + length,
                                    key);
    if (hash_status != NPRQ_OK) {
        return NR_ENVELOPE_ERR_KEY;
    }
    *canonical_bytes = length;
    return NR_ENVELOPE_OK;
}

static int key_equal(const uint8_t left[NPRQ_SHA256_BYTES],
                     const uint8_t right[NPRQ_SHA256_BYTES])
{
    uint8_t difference = 0U;
    size_t index;

    for (index = 0U; index < NPRQ_SHA256_BYTES; ++index) {
        difference |= (uint8_t)(left[index] ^ right[index]);
    }
    return difference == 0U;
}

static size_t find_entry(const nr_envelope_cache *cache,
                         const uint8_t key[NPRQ_SHA256_BYTES])
{
    size_t index;

    for (index = 0U; index < cache->count; ++index) {
        if (cache->entries[index].occupied != 0U &&
            key_equal(cache->entries[index].key, key)) {
            return index;
        }
    }
    return NR_ENVELOPE_CACHE_CAPACITY;
}

static size_t find_fallback(const nr_envelope_cache *cache,
                            const uint8_t key[NPRQ_SHA256_BYTES])
{
    size_t index;

    for (index = 0U; index < cache->fallback_count; ++index) {
        if (key_equal(cache->fallback_keys[index], key)) {
            return index;
        }
    }
    return NR_ENVELOPE_CACHE_CAPACITY;
}

static void remember_fallback(nr_envelope_cache *cache,
                              const uint8_t key[NPRQ_SHA256_BYTES])
{
    if (find_fallback(cache, key) < NR_ENVELOPE_CACHE_CAPACITY ||
        cache->fallback_count >= NR_ENVELOPE_CACHE_CAPACITY) {
        return;
    }
    memcpy(cache->fallback_keys[cache->fallback_count], key, NPRQ_SHA256_BYTES);
    ++cache->fallback_count;
}

static nr_envelope_status fallback(nr_envelope_cache *cache,
                                   nr_envelope_result *result)
{
    remember_fallback(cache, result->key);
    counter_increment(&cache->counters.fallbacks);
    result->status = NR_ENVELOPE_FAIL_SAFE_FALLBACK;
    return NR_ENVELOPE_FAIL_SAFE_FALLBACK;
}

nr_envelope_status nr_envelope_submit(nr_envelope_cache *cache,
                                      const uint8_t *input,
                                      size_t input_bytes,
                                      uint32_t conflict_score,
                                      uint32_t conflict_limit,
                                      uint32_t shock_score,
                                      uint32_t shock_limit,
                                      nr_envelope_result *result)
{
    size_t entry;
    nr_envelope_status status;

    if (cache == NULL || result == NULL) {
        return NR_ENVELOPE_ERR_ARGUMENT;
    }
    memset(result, 0, sizeof(*result));
    status = nr_envelope_key(input, input_bytes, result->key,
                             &result->canonical_bytes);
    if (status != NR_ENVELOPE_OK) {
        return status;
    }
    counter_increment(&cache->counters.requests);
    counter_increment(&cache->counters.outputs);
    counter_increment(&cache->counters.conditional_checks);
    if (conflict_score > conflict_limit) {
        counter_increment(&cache->counters.conflicts);
    }
    if (shock_score > shock_limit) {
        counter_increment(&cache->counters.shocks);
    }
    if (find_fallback(cache, result->key) < NR_ENVELOPE_CACHE_CAPACITY) {
        counter_increment(&cache->counters.fallback_hits);
        counter_increment(&cache->counters.conditional_failures);
        result->status = NR_ENVELOPE_FAIL_SAFE_FALLBACK;
        return NR_ENVELOPE_FAIL_SAFE_FALLBACK;
    }
    if (conflict_score > conflict_limit || shock_score > shock_limit) {
        counter_increment(&cache->counters.conditional_failures);
        return fallback(cache, result);
    }
    counter_increment(&cache->counters.conditional_passes);

    entry = find_entry(cache, result->key);
    if (entry < NR_ENVELOPE_CACHE_CAPACITY) {
        result->value = cache->entries[entry].value;
        result->status = NR_ENVELOPE_CACHE_HIT;
        counter_increment(&cache->counters.cache_hits);
        return NR_ENVELOPE_CACHE_HIT;
    }
    if (cache->first_miss_locked != 0U) {
        if (key_equal(cache->first_miss_key, result->key)) {
            result->status = NR_ENVELOPE_LOCKED_REPLAY;
            counter_increment(&cache->counters.locked_replays);
            counter_increment(&cache->counters.validation_retries);
            return NR_ENVELOPE_LOCKED_REPLAY;
        }
        counter_increment(&cache->counters.conflicts);
        return fallback(cache, result);
    }
    if (cache->count >= NR_ENVELOPE_CACHE_CAPACITY) {
        counter_increment(&cache->counters.full_cache);
        return fallback(cache, result);
    }
    memcpy(cache->first_miss_key, result->key, NPRQ_SHA256_BYTES);
    cache->first_miss_locked = 1U;
    counter_increment(&cache->counters.misses);
    counter_increment(&cache->counters.first_misses);
    result->status = NR_ENVELOPE_FIRST_MISS;
    return NR_ENVELOPE_FIRST_MISS;
}

nr_envelope_status nr_envelope_commit(nr_envelope_cache *cache,
                                      const uint8_t key[NPRQ_SHA256_BYTES],
                                      uint64_t value)
{
    nr_envelope_cache_entry *entry;

    if (cache == NULL || key == NULL) {
        return NR_ENVELOPE_ERR_ARGUMENT;
    }
    if (cache->first_miss_locked == 0U) {
        return NR_ENVELOPE_ERR_LOCK;
    }
    if (!key_equal(cache->first_miss_key, key)) {
        counter_increment(&cache->counters.conflicts);
        counter_increment(&cache->counters.fallbacks);
        return NR_ENVELOPE_FAIL_SAFE_FALLBACK;
    }
    if (cache->count >= NR_ENVELOPE_CACHE_CAPACITY) {
        counter_increment(&cache->counters.full_cache);
        counter_increment(&cache->counters.fallbacks);
        return NR_ENVELOPE_FAIL_SAFE_FALLBACK;
    }
    entry = &cache->entries[cache->count];
    memcpy(entry->key, key, NPRQ_SHA256_BYTES);
    entry->value = value;
    entry->sequence = cache->next_sequence;
    entry->occupied = 1U;
    ++cache->count;
    if (cache->next_sequence != UINT64_MAX) {
        ++cache->next_sequence;
    }
    cache->first_miss_locked = 0U;
    memset(cache->first_miss_key, 0, NPRQ_SHA256_BYTES);
    counter_increment(&cache->counters.commits);
    return NR_ENVELOPE_COMMITTED;
}

nr_envelope_status nr_envelope_abort(nr_envelope_cache *cache,
                                     const uint8_t key[NPRQ_SHA256_BYTES])
{
    if (cache == NULL || key == NULL) {
        return NR_ENVELOPE_ERR_ARGUMENT;
    }
    if (cache->first_miss_locked == 0U) {
        return NR_ENVELOPE_ERR_LOCK;
    }
    if (!key_equal(cache->first_miss_key, key)) {
        return NR_ENVELOPE_ERR_KEY;
    }
    cache->first_miss_locked = 0U;
    memset(cache->first_miss_key, 0, NPRQ_SHA256_BYTES);
    counter_increment(&cache->counters.aborts);
    return NR_ENVELOPE_ABORTED;
}

const char *nr_envelope_status_string(nr_envelope_status status)
{
    switch (status) {
    case NR_ENVELOPE_OK: return "ok";
    case NR_ENVELOPE_CACHE_HIT: return "cache hit";
    case NR_ENVELOPE_FIRST_MISS: return "first miss";
    case NR_ENVELOPE_LOCKED_REPLAY: return "first miss locked replay";
    case NR_ENVELOPE_FAIL_SAFE_FALLBACK: return "FAIL_SAFE_FALLBACK";
    case NR_ENVELOPE_COMMITTED: return "committed";
    case NR_ENVELOPE_ABORTED: return "aborted";
    case NR_ENVELOPE_ERR_ARGUMENT: return "invalid argument";
    case NR_ENVELOPE_ERR_BOUNDS: return "input bounds exceeded";
    case NR_ENVELOPE_ERR_OUTPUT: return "output buffer too small";
    case NR_ENVELOPE_ERR_LOCK: return "no active first miss lock";
    case NR_ENVELOPE_ERR_KEY: return "invalid or mismatched key";
    default: return "unknown status";
    }
}
