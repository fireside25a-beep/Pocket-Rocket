# Pocket Rocket image runtime — v1 design record

**Status:** design and source/licence review only. No image weights are in this
repository and no image download or backend is enabled by this document.

This component is a local, CPU-only image generator for the GTK application.
It is deliberately a separate inference process from the DeepSeek chat
process. The recovered Dexr Rendr material is used only for exact compositing,
decoding, colour conversion, and display signatures; it is not a generator and
does not provide a neural image backend.

## Decision summary

The proposed implementation boundary is:

```text
GTK4 application
  -> user-space supervisor / memory admission
  -> image worker (pinned stable-diffusion.cpp, CPU backend)
  -> local model file (GGUF or locally converted GGUF)
  -> PNG/RGBA result
  -> Rendr-compatible exact compositor/display path
```

The worker is started only after the supervisor has admitted the request. Chat
and image generation do not run concurrently when their measured resident sets
could exceed the 14.5 GiB application budget. A failed admission is a clear
error, not a silent downgrade to a hosted service or an unverified model.

## Pinned source proposal

### Runtime

Use [leejet/stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp)
at commit
`de298c225bed97c3f9026b73cd7b71e7879bd41b`. The commit was resolved from the
official `master` ref during this review. Its `LICENSE` is MIT (copyright
`2023 leejet`). The source describes itself as a pure C/C++ diffusion runtime,
and its README lists CPU AVX/AVX2/AVX512 backends, Linux support, and GGUF
weights. Those are source capabilities, not a completed Pocket Rocket
qualification result.

The runtime must be built with its CPU backend only. CUDA, Vulkan, Metal,
OpenCL, SYCL, and any GPU dispatch are rejected by the build manifest. The
exact compiler, flags, submodule revisions, and resulting executable SHA-256
will be recorded before release. The repository is active and explicitly warns
that its API may change, which is why a commit—not a floating branch—is part of
the proposal.

The runtime source and its submodules still require a transitive licence audit
at the pinned commit. “MIT” here identifies the top-level repository only; the
release gate must enumerate every vendored dependency and reject an unapproved
copyleft dependency.

### Model candidate

The first permissive candidate is the official
[black-forest-labs/FLUX.1-schnell model card](https://huggingface.co/black-forest-labs/FLUX.1-schnell).
The card identifies it as a 12-billion-parameter text-to-image model, states
that it can run in 1–4 steps, and labels the model `apache-2.0`. The official
[BFL inference repository](https://github.com/black-forest-labs/flux) also lists
FLUX.1 schnell as Apache-2.0 and lists its autoencoder weights as Apache-2.0.
The card contains use restrictions in addition to the licence label; the
release manifest must preserve both.

This is a candidate, not an implicit download. The model repository is gated
and requires the user to accept its conditions. The installer must never bypass
that gate, use a mirror, silently choose a third-party quantization, or call a
hosted endpoint. The user supplies the exact revision and file hashes, or the
installer stops.

The official BF16 files are not expected to fit the 14.5 GiB runtime budget.
The Pocket Rocket candidate therefore needs a locally verified GGUF
quantization (or a separately verified official artifact). It is not valid to
call this “lossless”: the quantized model must be benchmarked against the
selected source checkpoint and its measured error and memory peak recorded.
Until that measurement exists, FLUX.1 schnell is **not** a 16 GiB PASS.

Stable Diffusion 1.x/2.x and SDXL are useful engineering fallback fixtures
because stable-diffusion.cpp supports them, but their model cards use
CreativeML/OpenRAIL variants rather than Apache-2.0. They are not selected for
the permissive v1 model slot. A model with an unknown, missing, or incompatible
licence is rejected.

## Worker contract

The worker receives one bounded JSON request over a private Unix-domain socket
or inherited pipe. It does not listen on a network interface. Suggested v1
request fields:

```json
{
  "request_id": "uuid-or-local-counter",
  "prompt": "a small copper spacecraft above a quiet ocean",
  "negative_prompt": "",
  "width": 512,
  "height": 512,
  "steps": 4,
  "seed": 0,
  "sampler": "euler",
  "model_path": "/absolute/path/to/verified-model.gguf",
  "output": "png"
}
```

The supervisor validates dimensions, step count, seed range, sampler name,
path ownership, model hash, and output size before spawning the worker. The
worker returns either a bounded error or:

```json
{
  "request_id": "uuid-or-local-counter",
  "status": "ok",
  "image_path": "/private/session/result.png",
  "image_sha256": "...",
  "certificate": {
    "runtime": "stable-diffusion.cpp@de298c225bed97c3f9026b73cd7b71e7879bd41b",
    "model_sha256": "...",
    "model_revision": "...",
    "arithmetic_mode": "cpu_fixed_order",
    "seed": 0,
    "sampler": "euler",
    "steps": 4,
    "weight_spans": [{"offset": 0, "length": 0, "sha256": "..."}],
    "ternary_decision": "ALLOW",
    "renderer_signature": "..."
  }
}
```

`weight_spans` must contain the actual GGUF tensor/page ranges consumed by the
worker. An empty placeholder is invalid in a qualified build; the example is
schema-only. If the backend cannot expose exact consumed ranges, the image
certificate is marked `unqualified` and the UI must say so.

For repeatability, the worker fixes the seed, sampler, step count, dimensions,
thread count, CPU backend, and compiler/runtime manifest. The output digest is
the reproducibility check. A certificate proves provenance and arithmetic
configuration; it does not prove that the prompt is true or that image
semantics are correct.

## Memory and privilege boundary

No part of installation or operation uses `sudo`, root-only sysctls, HugeTLB
mounts, or system-wide services. The supervisor and worker use user-space
controls only:

1. Apply `RLIMIT_AS`/`RLIMIT_DATA` where supported before worker startup.
2. Keep an application-wide admission ledger based on measured process-tree
   RSS; do not treat an address-space limit as a physical-RAM guarantee.
3. Refuse image generation while the chat worker's reservation plus the image
   worker's measured high-water mark would exceed 14.5 GiB.
4. Use ordinary `mmap` and bounded scratch buffers. Huge pages are an optional
   best-effort optimization and never a requirement.
5. Treat `mlockall` and NUMA APIs as optional diagnostics. Failure is reported,
   not repaired with elevated privileges.
6. Kill the worker process group on timeout, reset, malformed output, or memory
   breach, then remove only the session-owned temporary files.

The GTK process remains a small client. It never maps the model and never
executes arbitrary generated code. Prompt text and output paths are bounded,
NUL-safe, and restricted to a private session directory.

## GTK and Rendr integration

The native GTK4 surface has three real modes: Chat, Image, and Local Git
Workspace. Image mode owns prompt controls, seed, dimensions, steps, a
Generate button, Cancel button, Open Result button, and a certificate panel.
Buttons are disabled during an admitted request and re-enabled after a
verified response or explicit error. There is no Electron shell and no remote
web UI.

The Rendr boundary accepts only decoded local RGBA/PNG data plus a signed
render signature. It may composite layers, scale, colour-convert, and display
the result. Its exact dependency signature is part of the result certificate.
It must not be used as a neural sampler, a cache-equivalence shortcut without
exact signature equality, or evidence that different floating-point backends
are identical. These rules follow the recovered accelerator evidence in
`docs/RECOVERED_ACCELERATOR_FACTS.md`.

## Licence and supply-chain gates

The eventual `IMAGE_THIRD_PARTY_NOTICES.md` must include, for each component:

- repository URL, pinned commit or model revision;
- SPDX licence identifier and the complete licence text or a stable source URL;
- SHA-256 for source archive, executable, model files, and every generated
  conversion;
- model-card use restrictions and acknowledgement requirements;
- transitive runtime and GTK dependencies.

The release is blocked when a component is GPL/AGPL/copyleft, has an unknown
licence, or is pulled from an unverified mirror. Apache-2.0 does not erase
model-card restrictions. No contact information, access token, or hosted API
key is committed. Runtime networking is disabled after installation, and an
attempt to use a remote URL is a hard error.

## Milestones and current blockers

- [x] Source review: stable-diffusion.cpp CPU/GGUF capability and MIT top-level
  licence recorded at a pinned commit.
- [x] Model review: official FLUX.1 schnell Apache-2.0 label, 12B size, gated
  access, and use restrictions recorded.
- [x] Process boundary and JSON certificate shape specified.
- [x] Rendr constrained to exact local compositing/display.
- [ ] Audit the pinned runtime's complete submodule licence tree.
- [ ] Obtain the user's legally accepted model files; verify revision, file
  hashes, and conversion provenance without uploading or re-hosting them.
- [ ] Build CPU-only worker and prove the requested model's peak process-tree
  RSS under 14.5 GiB on the target machine.
- [ ] Implement the GTK4 client and local Git workspace against the `/ask` and
  `/reset` lifecycle, with image generation as a separate admitted job.
- [ ] Run sanitizer, malformed-request, timeout, certificate, reproducibility,
  and fresh-process reset gates; only then label the image path qualified.

Until the unchecked milestones pass, the image tab must display “candidate /
unqualified” and must not imply that a model was downloaded, generated, or
validated.

## Primary sources reviewed

- [stable-diffusion.cpp repository and README](https://github.com/leejet/stable-diffusion.cpp)
- [stable-diffusion.cpp pinned MIT licence](https://github.com/leejet/stable-diffusion.cpp/blob/de298c225bed97c3f9026b73cd7b71e7879bd41b/LICENSE)
- [BFL official FLUX inference repository](https://github.com/black-forest-labs/flux)
- [FLUX.1 schnell official model card](https://huggingface.co/black-forest-labs/FLUX.1-schnell)
- [Pocket Rocket recovered Rendr/DPU boundary](RECOVERED_ACCELERATOR_FACTS.md)
