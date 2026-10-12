# Measured native substrate benchmarks

**Host measured for this release:** AMD EPYC 9V74, Linux 6.18.44 x86-64, GCC 14.2.0. Benchmark compilation used `-O3 -march=native -mavx2 -mpopcnt`. These numbers are properties of this run and are not portable performance promises. Raw output is in `docs/MEASURED_NATIVE_BENCHMARKS.csv`.

## Dense vs explicit sparse ternary dot

Sparsity means percentage of zero trits. Values are nanoseconds per full logical dot product; sparse/dense >1 means sparse is slower.

| N | zero sparsity | dense ns | sparse ns | sparse/dense |
|---:|---:|---:|---:|---:|
| 256 | 1% | 9.832 | 198.087 | 20.1477 |
| 256 | 10% | 9.525 | 135.795 | 14.2561 |
| 256 | 50% | 11.548 | 45.192 | 3.9136 |
| 256 | 90% | 10.082 | 9.909 | 0.9828 |
| 1024 | 1% | 42.961 | 964.889 | 22.4594 |
| 1024 | 10% | 40.920 | 722.239 | 17.6500 |
| 1024 | 50% | 40.748 | 187.486 | 4.6011 |
| 1024 | 90% | 36.686 | 42.101 | 1.1476 |
| 4096 | 1% | 174.412 | 3761.894 | 21.5690 |
| 4096 | 10% | 194.080 | 3253.676 | 16.7646 |
| 4096 | 50% | 281.963 | 1036.560 | 3.6762 |
| 4096 | 90% | 162.178 | 155.225 | 0.9571 |

Result: dense is decisively better through 50% zero sparsity on this host. At 90% zeros the result is near break-even and not monotonic with N, so the release makes **no general sparse speedup claim**.

## Software TCAM scan

| entries | scalar total µs | scalar ns/entry | explicit AVX2 total µs | AVX2 ns/entry |
|---:|---:|---:|---:|---:|
| 256 | 1.173 | 4.582 | 1.215 | 4.745 |
| 1,024 | 4.970 | 4.853 | 8.501 | 8.302 |
| 4,096 | 23.737 | 5.795 | 26.499 | 6.469 |
| 16,384 | 91.176 | 5.565 | 101.464 | 6.193 |

The explicit AVX2 implementation was slower on this host. It remains opt-in and is never auto-dispatched. The meaningful property is bounded linear scaling with a small fixed-width per-entry comparator.

## Exact 1,024-bit native Hamming router

For a 10,000-entry table across 201 runs: **0.043957 ms median, 0.088093 ms p95**. The exact query was present in the table and returned distance 0. This directly disproves the need to repeat the earlier unmeasured 0.5–2 ms estimate for this host.

## Exact diagonal SSM kernel

256 hidden states × 100,000 recurrence steps: **277.253 ms**, **360,681 tokens/s** in the combined benchmark. A separate `/usr/bin/time -v` run measured 264.362 ms / 378,269 tokens/s and **640 KiB maximum RSS** for the microbenchmark process.

This is a recurrence-kernel measurement, not language-model tokens/s. Divergence against an external pretrained model is **NOT_RUN** because no compatible pretrained checkpoint is redistributed or present in this release. `neuro-inverse ssm-compare` performs the real divergence calculation when supplied a compatible `A/B/output_weight` NPZ plus integer input sequence; it never tunes the fixed ternarization threshold to improve the result.
