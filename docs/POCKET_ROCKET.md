# Pocket Rocket

Pocket Rocket is the project name for the combined deterministic envelope,
NPRQ neural pages, 256-bit routing, recursive expert/precision expansion, and
optional lossless outer page packing.

## What UPX contributes as an idea

UPX is an executable packer, not a neural-weight format. Its official project
describes typical executable reductions of 50–70%, very fast decompression,
in-place execution support, and checksums for compressed and uncompressed data:
https://upx.github.io/

Pocket Rocket borrows four principles without copying UPX code:

1. compressed and reconstructed bytes both have integrity checks;
2. decompression is bounded and page-local;
3. a page is compressed only when its measured stored size wins;
4. corruption or unsupported structure fails closed.

UPX is GPL-licensed. No UPX source is included in this MIT repository.

## Loss boundaries

- BF16 -> NPRQ is quantization and therefore lossy.
- NPRQ stage -> Pocket Pack container -> NPRQ stage is bit-exact and lossless.
- Hamming routing may omit experts only within the certified bound; otherwise
  it activates the full configured target.

“Zero loss” applies only to the outer Pocket Pack round trip. It never means a
quantized model is identical to its BF16 source.

## Adaptive stage storage

`scripts/pack_nprq_adaptive.py` verifies the raw NPRQ package, then measures
each page group as raw NPRQ, shared-dictionary Flat32, and Pocket Pack. It
commits the least byte total using the deterministic tie order
`raw < pocket < flat32`:

```text
bytes(selected) = min(bytes(raw), bytes(Flat32 + dictionary), bytes(Pocket))
```

Flat32 and Pocket are lossless encodings of the already-produced NPRQ stage
bytes. They do not make NPRQ quantization lossless and they do not imply a
quality or speed improvement. The adaptive fixture tests verify decoded tensor
equality and leave the source manifest unchanged; full DeepSeek ratios remain a
target-machine measurement.

## Flat32 formula audit

Flat32 is **32 bytes to one 8-bit token** only when a block exactly matches one
of at most 256 registered dictionary entries. It is not 32 bytes to one bit.
Each full block also consumes one registration bit in the bitmap; misses retain
all 32 raw bytes. For `N` blocks, `R` registered matches, `F=N-R` misses, `D`
dictionary entries, framing `H`, and tail `T`:

```text
stored_stream = H + T + ceil(N/8) + R + 32F
stored_total  = stored_stream + 32D
ratio         = 32N / stored_bytes
```

For the recovered counts `R=701489`, `F=155311`, `N=856800`, `D=256`, and
64 bytes of framing/tail accounting, the stream ratio is `4.744674537×` and
the dictionary-inclusive ratio is `4.737957803×`. The separately recalled
`1.602698×` dictionary-inclusive result requires roughly 11.32 MB
additional scoped dictionaries/metadata not identified by the recovered
formula. This repository records the discrepancy and does not force-fit it.

Likewise, `8^4 = 4096` scalar levels require `log2(4096)=12` bits per symbol
before scales or metadata. That is not a smaller replacement for 4-bit storage.
No recovered thesis equation established a distinct “8^4 with 9 loss” codec,
so Pocket Rocket does not invent one. NPRQ and Flat32 remain separately tested
lossy and lossless layers.

For Flat32, with `B=32` bytes/block, `N` total blocks, `R` registered blocks,
`F=N-R`, `D≤256` dictionary entries, header `H`, and tail `T`, the accounting
is:

```text
bitmap = ceil(N/8)
stream = H + T + bitmap + R + 32F
dictionary-inclusive = stream + 32D
ratio = (32N) / stored_bytes
```

Current synthetic NPRQ-shaped fixtures measured random raw `202752`, Flat32
plus dictionary `204136` (`0.993220x`), and Pocket `190823` (`1.062513x`);
structured data measured Flat32 `9096` (`22.290237x`) and Pocket `1433`
(`141.487788x`) from the same raw size. These are storage measurements only,
not full-model compression or quality results.

## Measured small-page behavior

The included benchmark verifies reconstruction and reports actual ratio and
throughput. On a 2 MiB incompressible fixture, the container used raw chunks,
had about 0.0092% overhead, and verified around 547 MiB/s in the archive-build
environment. A separate exploratory NPRQ test found only 6–7% zlib/LZMA savings
for random-normal data, but more than 98% for deliberately repeated structured
data. Real model-page ratios must be measured after conversion.

## DeepSeek V4 Flash target

The Pocket Rocket target is the pinned public DeepSeek V4 Flash GGUF selected by
the recovered DwarfStar integration:

| field | exact value |
|---|---|
| model identity | `deepseek-ai/DeepSeek-V4-Flash` |
| weight repository | `antirez/deepseek-v4-gguf` |
| revision | `b0c3326275d2207e25e42bc8ac0704952466b5bb` |
| file | `DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf` |
| size | `86,720,111,488` bytes |
| SHA-256 | `efc7ed607ff27076e3e501fc3fefefa33c0ed8cf1eff483a2b7fdc0c2e616668` |
| routed / active experts | `256 / 6` |
| layers | `43` |

The repository deliberately does not infer a parameter count from a compressed
GGUF. The estimator reports exact pinned SSD bytes and labels any active-page
calculation as a routed-byte proxy until a native runtime exposes verified
tensor metadata.

The strict 16-GiB admission profile is a runtime envelope, not a claim that
the model has already passed on every machine:

- system RAM ceiling: `16 GiB`;
- non-routed weight budget: `8.20 GiB` (source-reported);
- routed expert cache: `1 GiB`;
- smoke context/output: `512 / 16` tokens;
- product context/output: `8192 / 2048` tokens;
- qualification ladder: `512/16 -> 2048/128 -> 4096/512 -> 8192/2048`;
- thinking disabled;
- GPU backends disabled; the admitted build target is CPU only.

The doctor must reject a host when its measured available memory cannot satisfy
the byte envelope. Only a real local smoke generation and conformance vectors
can change the status from *unmeasured* to *passed*; no estimate proves speed,
quality, or flawless inference.

The pinned ds4 Flash CPU layout uses a 128-row raw sliding window plus
alternating 4:1 and 128:1 compressed attention after layer 1. Exact mirrored
accounting gives 18,508,434 bytes of context buffers at 512 tokens and
124,202,514 bytes at 8,192 tokens. The previous zero-byte KV estimate was
invalid and has been removed.

Run:

```bash
PYTHONPATH=src python scripts/pocket_rocket_estimate.py --bits-per-param 4
PYTHONPATH=src python benchmarks/pocket_pack_bench.py --megabytes 64 --random
```

The optional Aegis boundary can verify a Pocket Rocket container or hash a
Flat32 file as storage, but it never interprets either as Aegis source. See
`docs/AEGIS_POCKET_ROCKET_BOUNDARY.md`.

## Performance hypothesis

MoE makes the target conceivable because only 6 of 256 routed experts are active
per token, but naive per-token SSD reads will be slow. The experiment must page
contiguous layer/expert chunks, prefetch upcoming experts, reuse decoded pages,
and measure cold/warm I/O. “1:1 speed” is a target to falsify, not a property of
compression.
