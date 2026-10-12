#include "envelope.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures = 0;

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        ++failures; \
    } \
} while (0)

static int request_text(size_t index, const char *prefix,
                        uint8_t buffer[64], size_t *length)
{
    int written = snprintf((char *)buffer, 64U, "%s-%03zu", prefix, index);
    if (written < 0 || (size_t)written >= 64U) {
        return 0;
    }
    *length = (size_t)written;
    return 1;
}

static void test_canonicalization_and_keys(void)
{
    static const uint8_t input[] = " \t alpha\n\r beta  \v";
    static const uint8_t expected[] = "alpha beta";
    uint8_t canonical[32];
    uint8_t key_a[NPRQ_SHA256_BYTES];
    uint8_t key_b[NPRQ_SHA256_BYTES];
    uint8_t oversized[NR_ENVELOPE_MAX_INPUT_BYTES + 1U];
    size_t length = 0U;
    size_t key_length_a = 0U;
    size_t key_length_b = 0U;

    CHECK(nr_envelope_canonicalize(input, sizeof(input) - 1U,
                                   canonical, sizeof(canonical), &length) == NR_ENVELOPE_OK);
    CHECK(length == sizeof(expected) - 1U);
    CHECK(memcmp(canonical, expected, length) == 0);
    CHECK(nr_envelope_canonicalize(input, sizeof(input) - 1U,
                                   canonical, 3U, &length) == NR_ENVELOPE_ERR_OUTPUT);
    CHECK(nr_envelope_key((const uint8_t *)"alpha beta", 10U, key_a, &key_length_a) == NR_ENVELOPE_OK);
    CHECK(nr_envelope_key((const uint8_t *)"\n alpha\t beta ",
                          sizeof("\n alpha\t beta ") - 1U,
                          key_b, &key_length_b) == NR_ENVELOPE_OK);
    CHECK(key_length_a == 10U && key_length_b == 14U);
    CHECK(memcmp(key_a, key_b, NPRQ_SHA256_BYTES) != 0);
    CHECK(nr_envelope_drift_key((const uint8_t *)"alpha beta", 10U,
                                key_a, &key_length_a) == NR_ENVELOPE_OK);
    CHECK(nr_envelope_drift_key((const uint8_t *)"\n alpha\t beta ",
                                sizeof("\n alpha\t beta ") - 1U,
                                key_b, &key_length_b) == NR_ENVELOPE_OK);
    CHECK(key_length_a == 10U && key_length_b == 10U);
    CHECK(memcmp(key_a, key_b, NPRQ_SHA256_BYTES) == 0);
    memset(oversized, (int)'x', sizeof(oversized));
    CHECK(nr_envelope_key(oversized, sizeof(oversized), key_a, &length) == NR_ENVELOPE_ERR_BOUNDS);
}

static void test_lock_and_gates(void)
{
    static const uint8_t first[] = "first";
    static const uint8_t second[] = "second";
    static const uint8_t shock[] = "shock";
    nr_envelope_cache cache;
    nr_envelope_result first_result;
    nr_envelope_result replay_result;
    nr_envelope_result conflict_result;
    nr_envelope_result shock_result;
    nr_envelope_result fallback_result;

    nr_envelope_cache_init(&cache);
    CHECK(nr_envelope_submit(&cache, first, sizeof(first) - 1U,
                             0U, 0U, 0U, 0U, &first_result) == NR_ENVELOPE_FIRST_MISS);
    CHECK(nr_envelope_submit(&cache, first, sizeof(first) - 1U,
                             0U, 0U, 0U, 0U, &replay_result) == NR_ENVELOPE_LOCKED_REPLAY);
    CHECK(nr_envelope_submit(&cache, second, sizeof(second) - 1U,
                             0U, 0U, 0U, 0U, &conflict_result) == NR_ENVELOPE_FAIL_SAFE_FALLBACK);
    CHECK(nr_envelope_submit(&cache, shock, sizeof(shock) - 1U,
                             0U, 0U, 1U, 0U, &shock_result) == NR_ENVELOPE_FAIL_SAFE_FALLBACK);
    CHECK(cache.counters.requests == 4U && cache.counters.outputs == 4U &&
          cache.counters.misses == 1U &&
          cache.counters.first_misses == 1U && cache.counters.locked_replays == 1U &&
          cache.counters.validation_retries == 1U &&
          cache.counters.conflicts == 1U && cache.counters.shocks == 1U &&
          cache.counters.fallbacks == 2U && cache.counters.fallback_hits == 0U &&
          cache.counters.conditional_checks == 4U &&
          cache.counters.conditional_passes == 3U &&
          cache.counters.conditional_failures == 1U);
    CHECK(nr_envelope_commit(&cache, first_result.key, 42U) == NR_ENVELOPE_COMMITTED);
    CHECK(nr_envelope_submit(&cache, second, sizeof(second) - 1U,
                             0U, 0U, 0U, 0U, &fallback_result) == NR_ENVELOPE_FAIL_SAFE_FALLBACK);
    CHECK(cache.counters.fallback_hits == 1U);
    CHECK(nr_envelope_submit(&cache, first, sizeof(first) - 1U,
                             0U, 0U, 0U, 0U, &first_result) == NR_ENVELOPE_CACHE_HIT);
    CHECK(first_result.value == 42U && cache.counters.cache_hits == 1U &&
          cache.counters.outputs == 6U);
    CHECK(nr_envelope_submit(&cache, second, sizeof(second) - 1U,
                             1U, 0U, 0U, 0U, &conflict_result) == NR_ENVELOPE_FAIL_SAFE_FALLBACK);
    CHECK(cache.counters.conflicts == 2U && cache.counters.fallbacks == 2U &&
          cache.counters.fallback_hits == 2U && cache.counters.conditional_checks == 7U &&
          cache.counters.conditional_passes == 4U &&
          cache.counters.conditional_failures == 3U);
}

static void test_stress_profiles(void)
{
    nr_envelope_cache low_miss;
    nr_envelope_cache three_hundred_miss;
    nr_envelope_result result;
    uint8_t request[64];
    size_t length;
    size_t index;

    nr_envelope_cache_init(&low_miss);
    for (index = 0U; index < 1000U; ++index) {
        size_t unique = index < 2U ? index : index % 2U;
        CHECK(request_text(unique, "low", request, &length));
        CHECK(nr_envelope_submit(&low_miss, request, length,
                                 0U, 0U, 0U, 0U, &result) ==
              (index < 2U ? NR_ENVELOPE_FIRST_MISS : NR_ENVELOPE_CACHE_HIT));
        if (index < 2U) {
            CHECK(nr_envelope_commit(&low_miss, result.key, (uint64_t)index) ==
                  NR_ENVELOPE_COMMITTED);
        }
    }
    CHECK(low_miss.counters.requests == 1000U && low_miss.counters.outputs == 1000U);
    CHECK(low_miss.counters.misses == 2U && low_miss.counters.first_misses == 2U);
    CHECK(low_miss.counters.commits == 2U && low_miss.counters.cache_hits == 998U);
    CHECK(low_miss.counters.validation_retries == 0U &&
          low_miss.counters.conditional_checks == 1000U &&
          low_miss.counters.conditional_passes == 1000U &&
          low_miss.counters.conditional_failures == 0U &&
          low_miss.counters.fallbacks == 0U && low_miss.count == 2U);

    nr_envelope_cache_init(&three_hundred_miss);
    for (index = 0U; index < 1000U; ++index) {
        CHECK(request_text(0U, "retry", request, &length));
        CHECK(nr_envelope_submit(&three_hundred_miss, request, length,
                                 0U, 0U, 0U, 0U, &result) ==
              (index == 0U ? NR_ENVELOPE_FIRST_MISS :
               (index < 300U ? NR_ENVELOPE_LOCKED_REPLAY : NR_ENVELOPE_CACHE_HIT)));
        if (index == 299U) {
            CHECK(nr_envelope_commit(&three_hundred_miss, result.key, 0U) == NR_ENVELOPE_COMMITTED);
        }
    }
    CHECK(three_hundred_miss.counters.requests == 1000U &&
          three_hundred_miss.counters.outputs == 1000U);
    CHECK(three_hundred_miss.counters.misses == 1U &&
          three_hundred_miss.counters.first_misses == 1U);
    CHECK(three_hundred_miss.counters.commits == 1U &&
          three_hundred_miss.counters.cache_hits == 700U &&
          three_hundred_miss.counters.locked_replays == 299U &&
          three_hundred_miss.counters.validation_retries == 299U);
    CHECK(three_hundred_miss.counters.conditional_checks == 1000U &&
          three_hundred_miss.counters.conditional_passes == 1000U &&
          three_hundred_miss.counters.conditional_failures == 0U &&
          three_hundred_miss.counters.fallbacks == 0U &&
          three_hundred_miss.count == 1U);
}

static void test_fixed_capacity(void)
{
    nr_envelope_cache cache;
    nr_envelope_result result;
    uint8_t request[64];
    size_t length;
    size_t index;

    nr_envelope_cache_init(&cache);
    for (index = 0U; index < NR_ENVELOPE_CACHE_CAPACITY; ++index) {
        CHECK(request_text(index, "full", request, &length));
        CHECK(nr_envelope_submit(&cache, request, length,
                                 0U, 0U, 0U, 0U, &result) == NR_ENVELOPE_FIRST_MISS);
        CHECK(nr_envelope_commit(&cache, result.key, (uint64_t)index) == NR_ENVELOPE_COMMITTED);
    }
    CHECK(cache.count == NR_ENVELOPE_CACHE_CAPACITY);
    CHECK(request_text(NR_ENVELOPE_CACHE_CAPACITY, "full", request, &length));
    CHECK(nr_envelope_submit(&cache, request, length,
                             0U, 0U, 0U, 0U, &result) == NR_ENVELOPE_FAIL_SAFE_FALLBACK);
    CHECK(cache.counters.full_cache == 1U && cache.counters.fallbacks == 1U &&
          cache.counters.outputs == NR_ENVELOPE_CACHE_CAPACITY + 1U);
}


static void test_abort_and_status_surface(void)
{
    nr_envelope_cache cache;
    nr_envelope_result result;
    const uint8_t request[] = "abort-surface";
    nr_envelope_cache_init(&cache);
    CHECK(nr_envelope_status_string(NR_ENVELOPE_FIRST_MISS) != NULL);
    CHECK(nr_envelope_submit(&cache, request, sizeof(request) - 1U,
                             0U, 0U, 0U, 0U, &result) == NR_ENVELOPE_FIRST_MISS);
    CHECK(nr_envelope_abort(&cache, result.key) == NR_ENVELOPE_ABORTED);
}

int main(void)
{
    test_abort_and_status_surface();
    test_canonicalization_and_keys();
    test_lock_and_gates();
    test_stress_profiles();
    test_fixed_capacity();
    if (failures != 0) {
        fprintf(stderr, "%d envelope test(s) failed\n", failures);
        return EXIT_FAILURE;
    }
    puts("envelope tests: PASS (N=1000 profiles)");
    return EXIT_SUCCESS;
}
