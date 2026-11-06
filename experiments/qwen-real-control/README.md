# Real Qwen 122B control: measured result

2026-11-06. The complete Qwen3.5-122B-A10B IQ1_M artifact was downloaded,
SHA-256 verified and executed with an unmodified compatible llama.cpp CPU build.
This is an independent control run. Pocket Rocket's production ds4 backend,
model pins and official gates are unchanged.

| Observation | Result |
| --- | --- |
| Complete verified model file | 31,790,258,304 bytes |
| Elementary exact-answer checks | 3/3: 4, 102, EDCBA |
| Longer requests completed | 3 of 5 planned; 64 actual tokens each |
| Median decode rate, completed longer requests | 0.129434 tokens/s |
| Decode-rate range | 0.127088-0.132535 tokens/s |
| Sampled peak process-tree RSS | 6,826,385,408 bytes (6.826 GB decimal) |
| Entire bounded attempt | 1,800.220 seconds |
| Fourth longer request | Interrupted at the predeclared 30-minute limit |
| Fifth longer request | Not run |

The model generated real answers. The scheduled series is **partial**, not a
completed five-run benchmark. The harness ended with TIME_LIMIT, not a claimed
memory success or an inferred model crash. Timed requests took 509.280, 519.385
and 529.961 seconds each, including prompt processing. Their outputs ended at
the 64-token allowance; they are not complete 100-word answers.

## Reproducible identities and settings

- Model repository: `bartowski/Qwen_Qwen3.5-122B-A10B-GGUF`.
- File: `Qwen_Qwen3.5-122B-A10B-IQ1_M.gguf`.
- Model revision: `fec8b222a2eddc3346d6b6d7f7c85efea93cd6bf`.
- Full-file SHA-256: `39984db48fc7beb1115da4a6de3de64bdee73ac2dbab86b5e8585409df2ffd6f`.
- llama.cpp tag `b9222`, commit `9a532ae4bab1b164052ce60a738f78538b421c66`.
- CPU only; 8 inference threads; context 512; one slot; batch 64; microbatch 32.
- Temperature 0, seed 42, `--mmap --no-repack --no-warmup`, thinking disabled
  through the model template; no prompt-token reuse reported in these responses.
- Frozen prompts and allowances: `requests.json`.
- Public aggregate measurements: `results.json`.

Token counts are the backend's actual `n_decoded` counters, exposed through
usage and timing fields, not the requested maximum. The engine counts stopping
tokens. Its decode timing begins after the first sampled token, so the tiny
smoke-response rates are not included in the longer-request median.

## Limits and next work

The RSS abort threshold was 8,000,000,000 bytes, sampled approximately every
100 ms across the process tree. A real child-allocation probe checked the
accounting. The host had more than 8 GB of total memory and no usable standard
cgroup memory limit interface. **A process RSS peak below 8 GB does not prove
operation within 8 GB of total system RAM.** File cache, kernel memory and other
processes also matter; a kernel-enforced total-memory run remains required.

Three elementary correct answers do not measure general accuracy, preservation
of the original model's quality or equivalence to higher-precision weights.
Time to first token, SSD traffic, page faults, controlled cold-cache behavior,
long-context performance and full Pocket Rocket proposal/receipt execution
remain unmeasured. No speed improvement over Pocket Rocket is claimed.

The concrete result supports a separate Qwen integration experiment, with
architecture support and end-to-end validation still required. The observed
speed is unsuitable for fluent interactive use in this configuration. Raw logs,
responses, harness and detailed environment records are retained separately;
this public directory contains only the report, frozen prompts and aggregate
measurements. No model weights or runtime binaries are redistributed.

Codex-assisted independent verification for Massimiliano Brighindi / PHI-OMEGA.
