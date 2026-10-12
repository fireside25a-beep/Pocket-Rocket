#define _POSIX_C_SOURCE 200809L
#include "ternary_core.h"
#include "ternary_tcam.h"
#include "ternary_ssm.h"
#include "hamming_router.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static volatile int64_t sink_i64;
static volatile uint64_t sink_u64;

static uint64_t rng_state = UINT64_C(0x9e3779b97f4a7c15);
static uint64_t next_u64(void)
{
    uint64_t z = (rng_state += UINT64_C(0x9e3779b97f4a7c15));
    z = (z ^ (z >> 30U)) * UINT64_C(0xbf58476d1ce4e5b9);
    z = (z ^ (z >> 27U)) * UINT64_C(0x94d049bb133111eb);
    return z ^ (z >> 31U);
}

static uint64_t ns_now(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0U;
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}

static int compare_u64(const void *a, const void *b)
{
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}

static void fill_trits(int8_t *values, size_t n, unsigned int zero_percent)
{
    size_t i;
    for (i = 0U; i < n; ++i) {
        unsigned int r = (unsigned int)(next_u64() % 100U);
        if (r < zero_percent) values[i] = 0;
        else values[i] = (next_u64() & UINT64_C(1)) != 0U ? 1 : -1;
    }
}

static void bench_dot(void)
{
    static const size_t lengths[] = {256U, 1024U, 4096U};
    static const unsigned int sparsities[] = {1U, 10U, 50U, 90U};
    size_t li, si;
    puts("DOT,length,sparsity_zero_percent,dense_ns_per_dot,sparse_ns_per_dot,ratio_sparse_over_dense");
    for (li = 0U; li < sizeof(lengths)/sizeof(lengths[0]); ++li) {
        size_t n = lengths[li];
        size_t chunks = n / NR_TERNARY_MAX_TRITS;
        nr_ternary_vector *left = calloc(chunks, sizeof(*left));
        nr_ternary_vector *right = calloc(chunks, sizeof(*right));
        int8_t *lv = malloc(NR_TERNARY_MAX_TRITS), *rv = malloc(NR_TERNARY_MAX_TRITS);
        if (left == NULL || right == NULL || lv == NULL || rv == NULL) exit(2);
        for (si = 0U; si < sizeof(sparsities)/sizeof(sparsities[0]); ++si) {
            size_t c, repeat, repeats = 200000U / chunks;
            uint64_t start, dense_ns, sparse_ns;
            int32_t value;
            for (c = 0U; c < chunks; ++c) {
                fill_trits(lv, NR_TERNARY_MAX_TRITS, sparsities[si]);
                fill_trits(rv, NR_TERNARY_MAX_TRITS, sparsities[si]);
                if (nr_ternary_pack(lv, NR_TERNARY_MAX_TRITS, &left[c]) != NR_TERNARY_OK ||
                    nr_ternary_pack(rv, NR_TERNARY_MAX_TRITS, &right[c]) != NR_TERNARY_OK) exit(3);
            }
            start = ns_now();
            for (repeat = 0U; repeat < repeats; ++repeat)
                for (c = 0U; c < chunks; ++c) { nr_ternary_dot(&left[c], &right[c], &value); sink_i64 += value; }
            dense_ns = ns_now() - start;
            start = ns_now();
            for (repeat = 0U; repeat < repeats; ++repeat)
                for (c = 0U; c < chunks; ++c) { nr_ternary_dot_sparse(&left[c], &right[c], &value); sink_i64 += value; }
            sparse_ns = ns_now() - start;
            printf("DOT,%zu,%u,%.3f,%.3f,%.4f\n", n, sparsities[si],
                   (double)dense_ns / (double)repeats,
                   (double)sparse_ns / (double)repeats,
                   (double)sparse_ns / (double)dense_ns);
        }
        free(left); free(right); free(lv); free(rv);
    }
}

static void random_vector(nr_ternary_vector *out)
{
    int8_t values[NR_TERNARY_MAX_TRITS];
    fill_trits(values, NR_TERNARY_MAX_TRITS, 50U);
    if (nr_ternary_pack(values, NR_TERNARY_MAX_TRITS, out) != NR_TERNARY_OK) exit(4);
}

static void bench_tcam(void)
{
    static const size_t counts[] = {256U,1024U,4096U,16384U};
    size_t ci;
    puts("TCAM,count,scalar_total_us,scalar_ns_per_entry,avx2_total_us,avx2_ns_per_entry");
    for (ci=0U; ci<sizeof(counts)/sizeof(counts[0]); ++ci) {
        size_t count=counts[ci], i, best=0U, repeats=100U;
        int32_t score=0;
        nr_ternary_vector query, *table=calloc(count,sizeof(*table));
        uint64_t start, scalar, avx=0U;
        if (table==NULL) exit(5);
        random_vector(&query);
        for(i=0U;i<count;++i) random_vector(&table[i]);
        table[count/2U]=query;
        start=ns_now();
        for(i=0U;i<repeats;++i){ nr_tcam_lookup(&query,table,count,&best,&score); sink_u64 += best+(uint64_t)score; }
        scalar=ns_now()-start;
#if defined(__AVX2__)
        start=ns_now();
        for(i=0U;i<repeats;++i){ nr_tcam_lookup_avx2(&query,table,count,&best,&score); sink_u64 += best+(uint64_t)score; }
        avx=ns_now()-start;
#endif
        printf("TCAM,%zu,%.3f,%.3f,",count,(double)scalar/repeats/1000.0,(double)scalar/repeats/(double)count);
#if defined(__AVX2__)
        printf("%.3f,%.3f\n",(double)avx/repeats/1000.0,(double)avx/repeats/(double)count);
#else
        puts("NA,NA");
#endif
        free(table);
    }
}

static void bench_hamming(void)
{
    const size_t count=10000U, runs=201U;
    size_t i,r,best=0U;
    uint16_t distance=0U;
    nr_hamming1024_code query, *table=calloc(count,sizeof(*table));
    uint64_t *times=calloc(runs,sizeof(*times));
    if(table==NULL||times==NULL) exit(6);
    for(i=0U;i<NR_HAMMING1024_WORDS;++i) query.words[i]=next_u64();
    for(r=0U;r<count;++r) for(i=0U;i<NR_HAMMING1024_WORDS;++i) table[r].words[i]=next_u64();
    table[count/2U]=query;
    for(r=0U;r<runs;++r){ uint64_t start=ns_now(); nr_hamming_route(&query,table,count,&best,&distance); times[r]=ns_now()-start; sink_u64+=best+distance; }
    qsort(times,runs,sizeof(*times),compare_u64);
    printf("HAMMING,count,runs,median_ms,p95_ms,best_distance\nHAMMING,%zu,%zu,%.6f,%.6f,%u\n",count,runs,
           (double)times[runs/2U]/1e6,(double)times[(runs*95U)/100U]/1e6,(unsigned int)distance);
    free(table); free(times);
}

static void bench_ssm(void)
{
    const size_t hidden=256U,tokens=100000U;
    size_t i,t;
    int32_t *state=calloc(hidden,sizeof(*state)), *input=calloc(hidden,sizeof(*input));
    int8_t *a=malloc(hidden), *b=malloc(hidden);
    uint32_t *weights=malloc(hidden*sizeof(*weights)), output=0U;
    uint64_t start, elapsed;
    if(state==NULL||input==NULL||a==NULL||b==NULL||weights==NULL) exit(7);
    for(i=0U;i<hidden;++i){ a[i]=(i%3U==0U)?0:1; b[i]=(i%2U==0U)?1:-1; input[i]=(int32_t)((i%5U)-2U); weights[i]=UINT32_C(0x3b800000); }
    start=ns_now();
    for(t=0U;t<tokens;++t){
        if(nr_ternary_ssm_step(state,input,a,b,hidden)!=NR_SSM_OK) exit(8);
    }
    if(nr_ternary_ssm_project_binary32(state,weights,hidden,&output)!=NR_SSM_OK) exit(9);
    elapsed=ns_now()-start; sink_u64 += output;
    printf("SSM,hidden_dim,tokens,wall_ms,tokens_per_second,output_bits\nSSM,%zu,%zu,%.3f,%.3f,0x%08" PRIx32 "\n",
           hidden,tokens,(double)elapsed/1e6,(double)tokens/((double)elapsed/1e9),output);
    free(state); free(input); free(a); free(b); free(weights);
}

int main(int argc, char **argv)
{
    const char *mode = argc > 1 ? argv[1] : "all";
    if(strcmp(mode,"dot")==0||strcmp(mode,"all")==0) bench_dot();
    if(strcmp(mode,"tcam")==0||strcmp(mode,"all")==0) bench_tcam();
    if(strcmp(mode,"hamming")==0||strcmp(mode,"all")==0) bench_hamming();
    if(strcmp(mode,"ssm")==0||strcmp(mode,"all")==0) bench_ssm();
    return 0;
}
