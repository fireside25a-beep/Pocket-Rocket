# 30-GB model and 8-GB inference qualification plan

Date: 2026-11-06. Pocket Rocket base: `68b435ab314e603172fa4cdaf3186311310a51d9`.

**Result: there is a downloadable 122B candidate near 30 GB, but it cannot run
through the currently pinned Pocket Rocket / ds4 path. No full-model inference,
tokens/s, accuracy, or 8-GB success is claimed by this experiment.**

This directory provides a reproducible read-only planner, immutable candidate
identities, a bounded real-file probe, engine build/self-test evidence, gate
diagnostics, and the sequence needed for a valid full run. Production model pins
and release gates are unchanged.

## Model selection

All sizes below are decimal GB, not GiB. The 25-35 GB selection band and strict
greater-than-90B threshold are explicit planning interpretations, not model facts.
The complete revisions, file sizes and published SHA-256 values are in
`candidates.json`; upstream API snapshots are in `model-metadata.json`.

| Candidate | Total / active parameters | Weight file | Current disposition |
| --- | --- | ---: | --- |
| Qwen3.5-122B-A10B IQ1_S | 122B / 10B | 28.902 GB | Size/parameter match; unsupported architecture |
| Qwen3.5-122B-A10B IQ1_M | 122B / 10B | 31.790 GB | Size/parameter match; unsupported architecture |
| GLM-4.5-Air IQ1_M | 106B / 12B | 37.857 GB | Outside planning size band; unsupported architecture |
| Qwen3-Next-80B-A3B Q2_K | 80B / 3B | 28.168 GB | Does not exceed 90B; unsupported architecture |
| Pocket Rocket's pinned DeepSeek V4 Flash | 284B / 13B | 86.720 GB | Existing integration; exceeds this workspace's free disk and size band |

For an eventual new backend experiment, Qwen3.5 IQ1_M is a candidate if about
32 GB is acceptable; IQ1_S is the smaller alternative. Neither is a quality
recommendation. The quantizer labels IQ1 variants extremely low quality and not
recommended. The original model card's benchmark scores cannot be transferred
to these quantizations. Active parameter counts do not establish runtime RAM.

Sources: [Qwen model](https://huggingface.co/Qwen/Qwen3.5-122B-A10B),
[Qwen quantizations](https://huggingface.co/bartowski/Qwen_Qwen3.5-122B-A10B-GGUF),
[GLM Air](https://huggingface.co/zai-org/GLM-4.5-Air),
[Qwen Next](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Instruct),
[DeepSeek](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash).

## Why replacing the download URL is not sufficient

Pocket Rocket pins ds4 to `84cc882352757baf628a1776badf7cc54d584e28`.
That source dispatches `glm-dsa` to its GLM validator and otherwise requires
DeepSeek V4 geometry. Its README explicitly limits supported GGUFs to tested
DeepSeek V4 and GLM 5.2 artifacts. It is not a generic GGUF loader.

A real HTTP Range request retrieved exactly 65,536 bytes of the IQ1_S file,
with response 206 and total file length 28,902,086,784 bytes. The GGUF metadata
declares `general.architecture = qwen35moe`. This is the GGUF architecture name;
the original Transformers architecture is named `qwen3_5_moe`. See
`header-probe.json`. This verifies public metadata access and the actual header,
not the full file's checksum, tensor integrity, or inference behavior. No sparse
or fabricated model was used as a substitute for inference.

Pocket Rocket additionally validates its exact model identity, file size and
SHA-256 in `src/neuro_inverse/model_target.py`. Changing only those checks would
not implement Qwen's hybrid attention/recurrent layers, tokenizer, quantization
kernels, or expert streaming. Removing the checks would hide the incompatibility.

Newer ds4 was also inspected at `b3f50180ec2c7324892be1f50bc83555ccb8d5e7`:
its Qwen3.8 Flash Next Q2 download is 137.10 GiB, including 95.37 GiB of disk
n-gram tables. It is a different architecture/artifact and does not satisfy
the 30-GB download request. Upgrading ds4 is not itself a solution.

## Work executed

- Built the exact pinned ds4 CPU revision with GCC 14.2 (`make -j4 cpu`).
- Q4_K arithmetic: 4/4 tests passed.
- Layer placement/packing: 97/97 checks passed.
- `ds4-eval --self-test-extractors`: passed.
- Queried public immutable weight metadata and fetched the bounded Qwen header.
- Rebuilt Aegis's native compiler and inspected both binaries' compiler metadata.
- Re-ran the empty-program LeakSanitizer host probe with leak detection enabled.

These checks do not execute a model. The previous output-provenance regression
and qualification evidence remains in `evidence/2026-11-06-output-provenance/`.
It is not relabeled as a new full-model run.

Run the read-only planner from the repository root:

```sh
python experiments/model-qualification/plan.py
```

It prints live free disk space, constraints and blockers. Exit 2 is intentional:
the plan is not an inference certificate. There is no download or model execution
in this script. `current-plan.json` records this workspace's observed run.

## Official gates: concrete remaining work

| Gate | Observation | Required next environment/action |
| --- | --- | --- |
| C2R ASan+UBSan corpus with leak detection | LeakSanitizer fails even for `int main(void) { return 0; }` | Run the unchanged official gate on a host where the empty probe and an intentional-leak control establish working LeakSanitizer |
| Aegis source-to-shipped byte identity | Shipped binary embeds Ubuntu GCC 13.3.0; local rebuild embeds Debian GCC 14.2.0 | Use the documented Ubuntu 24.04 x86-64 / glibc 2.39 / GCC 13.3 maintainer environment, then rerun the unchanged gate |
| Real DeepSeek inference | Pinned 86.720-GB file absent; available disk below required size | Supply a host/volume with sufficient capacity, verify the complete pinned file, then run the real gate |
| 8-GB qualification | Current default RSS cap is 15,569,256,448 bytes; no 8-GB model run exists | Measure separately with a declared 8,000,000,000-byte total budget and explicit accounting |

Different compiler metadata and the documented release environment explain why
the current source rebuild is not a byte-reproduction qualification. This is not
a claim that changing the compiler version alone guarantees all maintainer tests
pass. See Aegis `docs/TESTING.md` and `docs/RELEASE_PROCESS.md`.

The exact C2R command is `make -C toolchains/aegis-c2r-0.1.0 check` with the
required compilers available. The Aegis command is
`make -C toolchains/aegis-language-suite-2.4.3 maintainer-check` in its documented
release environment. Keep `detect_leaks=1`, corpus checks and byte comparisons.
Do not turn host limitations into PASS, replace shipped binaries to match this
host, or modify security policy to force a green report.

## Full-run sequence and measurement contract

1. **Choose a valid inference path.** The shortest path for testing the existing
   product is its exact DeepSeek file on a larger volume. The approximately
   30-GB Qwen route requires a separately pinned backend/architecture integration.
   A llama.cpp control run could compare the model, but would not validate ds4 or
   Pocket Rocket's existing inference path. Preserve that distinction in results.
2. **Freeze all identities before downloading.** Record repository and backend
   commits, build flags, binary SHA-256, model revision/file/size/full SHA-256,
   tokenizer/template, prompt corpus hash, sampling settings and hardware.
   Download one file to a temporary path with enough disk reserve; resume if
   necessary; stream-verify the complete SHA-256 before making it runnable.
3. **Run unchanged software gates first.** Require genuine C2R and Aegis release
   passes on qualified hosts. Keep stdout model content separate from diagnostics
   and preserve the receipt-root checks introduced in PR #1.
4. **Prove the memory condition.** Use a dedicated 8,000,000,000-byte total budget
   (report 8 GiB separately if desired), no swap, and record process-tree peak
   RSS plus cgroup memory peak, OOM events, file-cache usage and any GPU memory.
   RSS polling alone does not certify an 8-GB machine. This workspace does not
   expose the standard cgroup memory control files, so no enforced total limit
   is claimed. A bounded expert cache is only one allocation, not total RAM.
5. **Smoke, then expand.** Use (context, output allowance) = (512,16), (2048,128),
   (4096,512), (8192,2048), at concurrency 1. Stop the current lane on load error,
   cap breach, OOM, timeout, empty answer, invalid token count or verification
   failure; retain raw results as FAIL/BLOCKED rather than dropping samples.
6. **Separate speed measurements.** Time cold startup/model load, prompt prefill,
   time to first generated token, steady decode and total request duration.
   Count actual generated token IDs, including a stated EOS policy. Never divide
   the configured maximum output allowance by runtime. ds4-server exposes actual
   `prompt_tokens`/`completion_tokens`; add and verify monotonic phase timing or
   use the engine's internal timing, rather than treating SSE chunks as tokens.
   Record CPU threads, context length, prompt/output counts, cache settings,
   SSD read bytes/latency and page faults. Compare cold starts and warm runs
   separately; do not call a run cold unless cache state is established.
7. **Measure accuracy with a frozen corpus.** Before running, pin dataset revision,
   exact item IDs, prompt template, scoring code and a separately named reference
   model/quantization. Start with a fixed 100-item task-relevant pilot, then the
   full selected split; report correct/total, invalids, truncations and uncertainty.
   Verify scoring against known answers before model execution. An IQ1 candidate
   needs a measured comparison; the unquantized model card is not its baseline
   run. Speed and accuracy acceptance thresholds remain an explicit product
   decision; report measurements without inventing a quality PASS threshold.
8. **Repeat and preserve evidence.** At least five successful timed requests per
   performance condition, plus every failure; report median and min/max, not a
   single peak. Record raw output, stderr, actual usage, timings, memory/I/O and
   integrity/receipt results under one run ID. Audit the complete Pocket Rocket
   proposal-to-verification-to-receipt path in addition to bare model throughput.

The actionable boundary is now explicit: a 30-GB file exists, but a compatible
8-GB inference path has not been established. Backend support, storage capacity,
host qualification and measured quality are separate requirements.
