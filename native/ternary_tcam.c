#include "ternary_tcam.h"

#include <limits.h>
#if defined(__AVX2__)
#include <immintrin.h>
#endif

static unsigned int popcount64(uint64_t value)
{
#if defined(__GNUC__) || defined(__clang__)
    return (unsigned int)__builtin_popcountll((unsigned long long)value);
#else
    unsigned int count = 0U;
    while (value != 0U) { value &= value - UINT64_C(1); ++count; }
    return count;
#endif
}

static nr_tcam_status validate_table(const nr_ternary_vector *query,
                                     const nr_ternary_vector *table,
                                     size_t count)
{
    size_t index;
    if (query == NULL || table == NULL || count == 0U) return NR_TCAM_ERR_ARGUMENT;
    if (count > NR_TCAM_MAX_ENTRIES) return NR_TCAM_ERR_RANGE;
    if (nr_ternary_validate(query) != NR_TERNARY_OK) return NR_TCAM_ERR_VECTOR;
    for (index = 0U; index < count; ++index) {
        if (nr_ternary_validate(&table[index]) != NR_TERNARY_OK ||
            table[index].count != query->count) return NR_TCAM_ERR_VECTOR;
    }
    return NR_TCAM_OK;
}

static int32_t score_scalar(const nr_ternary_vector *query,
                            const nr_ternary_vector *stored)
{
    size_t word;
    unsigned int mismatch = 0U;
    for (word = 0U; word < NR_TERNARY_WORDS; ++word) {
        uint64_t diff = (query->positive[word] ^ stored->positive[word]) |
                        (query->negative[word] ^ stored->negative[word]);
        mismatch += popcount64(diff);
    }
    return (int32_t)query->count - (int32_t)mismatch;
}

nr_tcam_status nr_tcam_lookup(const nr_ternary_vector *query,
                              const nr_ternary_vector *table,
                              size_t count,
                              size_t *best_index,
                              int32_t *best_score)
{
    size_t index;
    int32_t score;
    nr_tcam_status status;
    if (best_index == NULL || best_score == NULL) return NR_TCAM_ERR_ARGUMENT;
    *best_index = 0U; *best_score = INT32_MIN;
    status = validate_table(query, table, count);
    if (status != NR_TCAM_OK) return status;
    for (index = 0U; index < count; ++index) {
        score = score_scalar(query, &table[index]);
        if (score > *best_score) { *best_score = score; *best_index = index; }
    }
    return NR_TCAM_OK;
}

nr_tcam_status nr_tcam_exact_match(const nr_ternary_vector *query,
                                   const nr_ternary_vector *table,
                                   size_t count,
                                   size_t *index)
{
    size_t current;
    nr_tcam_status status;
    if (index == NULL) return NR_TCAM_ERR_ARGUMENT;
    *index = 0U;
    status = validate_table(query, table, count);
    if (status != NR_TCAM_OK) return status;
    for (current = 0U; current < count; ++current) {
        if (score_scalar(query, &table[current]) == (int32_t)query->count) {
            *index = current; return NR_TCAM_OK;
        }
    }
    return NR_TCAM_NOT_FOUND;
}

nr_tcam_status nr_tcam_lookup_avx2(const nr_ternary_vector *query,
                                   const nr_ternary_vector *table,
                                   size_t count,
                                   size_t *best_index,
                                   int32_t *best_score)
{
#if defined(__AVX2__)
    size_t index;
    nr_tcam_status status;
    __m256i qp, qn;
    if (best_index == NULL || best_score == NULL) return NR_TCAM_ERR_ARGUMENT;
    *best_index = 0U; *best_score = INT32_MIN;
    status = validate_table(query, table, count);
    if (status != NR_TCAM_OK) return status;
    qp = _mm256_loadu_si256((const __m256i *)(const void *)query->positive);
    qn = _mm256_loadu_si256((const __m256i *)(const void *)query->negative);
    for (index = 0U; index < count; ++index) {
        uint64_t lanes[NR_TERNARY_WORDS];
        unsigned int mismatch = 0U;
        __m256i sp = _mm256_loadu_si256((const __m256i *)(const void *)table[index].positive);
        __m256i sn = _mm256_loadu_si256((const __m256i *)(const void *)table[index].negative);
        __m256i diff = _mm256_or_si256(_mm256_xor_si256(qp, sp), _mm256_xor_si256(qn, sn));
        size_t lane;
        _mm256_storeu_si256((__m256i *)(void *)lanes, diff);
        for (lane = 0U; lane < NR_TERNARY_WORDS; ++lane) mismatch += popcount64(lanes[lane]);
        {
            int32_t score = (int32_t)query->count - (int32_t)mismatch;
            if (score > *best_score) { *best_score = score; *best_index = index; }
        }
    }
    return NR_TCAM_OK;
#else
    (void)query; (void)table; (void)count; (void)best_index; (void)best_score;
    return NR_TCAM_ERR_UNAVAILABLE;
#endif
}

const char *nr_tcam_status_string(nr_tcam_status status)
{
    switch (status) {
    case NR_TCAM_OK: return "ok";
    case NR_TCAM_NOT_FOUND: return "not found";
    case NR_TCAM_ERR_ARGUMENT: return "invalid argument";
    case NR_TCAM_ERR_RANGE: return "table exceeds configured bound";
    case NR_TCAM_ERR_VECTOR: return "invalid or incompatible ternary vector";
    case NR_TCAM_ERR_UNAVAILABLE: return "accelerator unavailable in this build";
    default: return "unknown TCAM status";
    }
}
