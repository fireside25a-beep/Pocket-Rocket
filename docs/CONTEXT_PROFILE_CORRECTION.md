# Context-profile correction

## Finding

The earlier package accidentally promoted its first hardware smoke values
(`context=512`, `output=16`, later CLI output cap `128`) into the normal chat
profile. Its local estimator also lacked the pinned DeepSeek V4 Flash KV shape,
so it reported zero KV bytes. Both were defects.

The remembered value 8192 had two historical meanings and must not be mixed:

- an older Dexr spatial page/address value, which was not a token window;
- a real pinned-ds4 benchmark frontier using an 8192-token prefix and an
  automatically sized 8193-token context.

The recovered earlier large-MoE memory preset explicitly used a 4096-token
context. No Qwen model or Qwen runtime is restored by this correction.

## Pinned ds4 facts used

Revision `84cc882352757baf628a1776badf7cc54d584e28` defines Flash as:

| field | value |
| --- | ---: |
| layers | 43 |
| hidden size | 4096 |
| attention heads | 64 |
| KV heads | 1 |
| head/KV row dimension | 512 |
| raw sliding-attention rows | 128 |
| default CLI context | 32768 |

For Flash, layers 0 and 1 have no compressed rows. Layers 2 through 42
alternate compression ratios 4 and 128. Ratio-4 layers also store a
128-element indexer row. The source uses float32 CPU caches.

For context `C`, the mirrored accounting is:

```text
R = min(128, C)
raw = 43 * R * 512 * 4

compressed = sum(layer=2..42) (
    (floor(C / ratio[layer]) + 2) * 512 * 4
    + [ratio[layer] = 4] * (floor(C / 4) + 2) * 128 * 4
)

S = floor(C / 4) + 2
scratch = (R + S) * 4 + S * 4 + S
context_buffers = raw + compressed + scratch
```

The implementation is `ds4_flash_cpu_context_memory()` and its exact regression
vectors are:

| context | context buffers |
| ---: | ---: |
| 512 | 18,508,434 bytes |
| 2,048 | 39,647,250 bytes |
| 4,096 | 67,832,338 bytes |
| 8,192 | 124,202,514 bytes |

This mirrors ds4's context-scaled CPU accounting. It is not a replacement for
measured whole-process RSS: fixed model mappings, allocator state, worker
threads, transient expert pages and OS page residency are still measured by
the 14.5 GiB process-tree gate.

## Correct profiles

```text
smoke:       context 512  / output 16
frontier 2:  context 2048 / output 128
frontier 3:  context 4096 / output 512
product:     context 8192 / output 2048
```

`DS4LocalTransport`, the CLI, `/ask`, and `config/default.toml` now default to
the product profile. `run_16gb_gate.py` defaults to the smoke profile because a
new host must not jump directly to the longest generation. The deterministic
`run_context_ladder.py` executes every frontier in order and stops at the first
failure. Only all four PASS records constitute a product memory pass.
