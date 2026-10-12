#ifndef NEURO_ROUTE_ENVELOPE_H
#define NEURO_ROUTE_ENVELOPE_H

/*
 * Deterministic, bounded control envelope for the native runtime.
 *
 * This layer does not run a model and does not pretend to be one. It
 * canonicalizes bounded input bytes, derives content keys, serializes the
 * first cache miss, and exposes explicit fail-safe decisions for conflicts,
 * shocks, and a full fixed-capacity cache.
 */

#include "nprq.h"

#include <stddef.h>
#include <stdint.h>

#define NR_ENVELOPE_MAX_INPUT_BYTES ((size_t)65536U)
#define NR_ENVELOPE_CACHE_CAPACITY ((size_t)512U)

typedef enum nr_envelope_status {
    NR_ENVELOPE_OK = 0,
    NR_ENVELOPE_CACHE_HIT = 1,
    NR_ENVELOPE_FIRST_MISS = 2,
    NR_ENVELOPE_LOCKED_REPLAY = 3,
    NR_ENVELOPE_FAIL_SAFE_FALLBACK = 4,
    NR_ENVELOPE_COMMITTED = 5,
    NR_ENVELOPE_ABORTED = 6,
    NR_ENVELOPE_ERR_ARGUMENT = 100,
    NR_ENVELOPE_ERR_BOUNDS = 101,
    NR_ENVELOPE_ERR_OUTPUT = 102,
    NR_ENVELOPE_ERR_LOCK = 103,
    NR_ENVELOPE_ERR_KEY = 104
} nr_envelope_status;

typedef struct nr_envelope_cache_entry {
    uint8_t key[NPRQ_SHA256_BYTES];
    uint64_t value;
    uint64_t sequence;
    uint8_t occupied;
} nr_envelope_cache_entry;

typedef struct nr_envelope_counters {
    uint64_t requests;
    uint64_t outputs;
    uint64_t cache_hits;
    uint64_t misses;
    uint64_t first_misses;
    uint64_t locked_replays;
    uint64_t validation_retries;
    uint64_t commits;
    uint64_t aborts;
    uint64_t conflicts;
    uint64_t shocks;
    uint64_t full_cache;
    uint64_t fallbacks;
    uint64_t fallback_hits;
    uint64_t conditional_checks;
    uint64_t conditional_passes;
    uint64_t conditional_failures;
} nr_envelope_counters;

typedef struct nr_envelope_cache {
    nr_envelope_cache_entry entries[NR_ENVELOPE_CACHE_CAPACITY];
    size_t count;
    uint8_t first_miss_locked;
    uint8_t first_miss_key[NPRQ_SHA256_BYTES];
    uint8_t fallback_keys[NR_ENVELOPE_CACHE_CAPACITY][NPRQ_SHA256_BYTES];
    size_t fallback_count;
    uint64_t next_sequence;
    nr_envelope_counters counters;
} nr_envelope_cache;

typedef struct nr_envelope_result {
    uint8_t key[NPRQ_SHA256_BYTES];
    uint64_t value;
    nr_envelope_status status;
    size_t canonical_bytes;
} nr_envelope_result;

void nr_envelope_cache_init(nr_envelope_cache *cache);

/* Collapse bounded ASCII whitespace runs and trim their edges. */
nr_envelope_status nr_envelope_canonicalize(const uint8_t *input,
                                            size_t input_bytes,
                                            uint8_t *output,
                                            size_t output_capacity,
                                            size_t *canonical_bytes);

/* Hash exact input bytes; this is the default identity and never normalizes. */
nr_envelope_status nr_envelope_key(const uint8_t *input,
                                   size_t input_bytes,
                                   uint8_t key[NPRQ_SHA256_BYTES],
                                   size_t *canonical_bytes);

/*
 * Explicit whitespace-drift identity. The domain/version prefix prevents a
 * normalized key from colliding with an exact-content key. Do not use this
 * for code or prompts where whitespace can be semantic.
 */
nr_envelope_status nr_envelope_drift_key(const uint8_t *input,
                                         size_t input_bytes,
                                         uint8_t key[NPRQ_SHA256_BYTES],
                                         size_t *canonical_bytes);

/*
 * Submit one request. conflict_score/shock_score are caller-provided
 * evidence values; exceeding either limit is an immediate fail-safe result.
 * A FIRST_MISS must be followed by commit or abort before another key enters.
 */
nr_envelope_status nr_envelope_submit(nr_envelope_cache *cache,
                                      const uint8_t *input,
                                      size_t input_bytes,
                                      uint32_t conflict_score,
                                      uint32_t conflict_limit,
                                      uint32_t shock_score,
                                      uint32_t shock_limit,
                                      nr_envelope_result *result);

/* Complete the currently locked first miss with a deterministic value. */
nr_envelope_status nr_envelope_commit(nr_envelope_cache *cache,
                                      const uint8_t key[NPRQ_SHA256_BYTES],
                                      uint64_t value);

/* Release a first-miss lock without inserting a cache entry. */
nr_envelope_status nr_envelope_abort(nr_envelope_cache *cache,
                                     const uint8_t key[NPRQ_SHA256_BYTES]);

const char *nr_envelope_status_string(nr_envelope_status status);

#endif
