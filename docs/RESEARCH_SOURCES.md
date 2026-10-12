# Primary sources

- Official model configuration:
  https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash/blob/main/config.json
- Pinned DwarfStar-compatible GGUF repository:
  https://huggingface.co/antirez/deepseek-v4-gguf
- Native DwarfStar runtime:
  https://github.com/antirez/ds4
- Pinned runtime revision:
  https://github.com/antirez/ds4/commit/84cc882352757baf628a1776badf7cc54d584e28
- Pinned runtime implementation (model shape and compressed KV allocation):
  https://github.com/antirez/ds4/blob/84cc882352757baf628a1776badf7cc54d584e28/ds4.c
- Pinned runtime CLI (32K default context contract):
  https://github.com/antirez/ds4/blob/84cc882352757baf628a1776badf7cc54d584e28/ds4_cli.c
- Pinned 8K speed-benchmark procedure:
  https://github.com/antirez/ds4/blob/84cc882352757baf628a1776badf7cc54d584e28/speed-bench/README.md
- Streaming layer-batch cache-pressure correctness report and workaround:
  https://github.com/antirez/ds4/issues/384
- Small SSD-streaming cache report:
  https://github.com/antirez/ds4/issues/439

Runtime facts are pinned in source and checked again at installation. Issue
reports motivate conservative gates; they are not proof that this package has
passed on the user's hardware.

## Pocket Rocket 0.2 design inputs

- TypeSafe AI, Jev primitives and patterns:
  <https://docs.typesafe.ai/primitives/advanced>,
  <https://docs.typesafe.ai/patterns/confidence-routing>, and
  <https://docs.typesafe.ai/patterns/composite-scoring>. Pocket Rocket adopts
  typed Choice/Score/gating as a local exact interface, not Jev's hosted model
  or source code.
- George C. Necula, *Proof-Carrying Code*, POPL 1997:
  <https://doi.org/10.1145/263699.263712>. Pocket Rocket's certificate is a
  machine-checkable evidence commitment; it is not a formal PCC safety proof.
- Wen Xia et al., *FastCDC*, USENIX ATC 2016:
  <https://www.usenix.org/conference/atc16/technical-sessions/presentation/xia>.
  The paper informed the storage review. Pocket Rocket deliberately selects
  fixed dyadic pages because deterministic range addressing matters more than
  cross-version deduplication for the pinned single model.
- Robert N. M. Watson et al., *Capsicum: Practical Capabilities for UNIX*,
  USENIX Security 2010:
  <https://research.google/pubs/capsicum-practical-capabilities-for-unix/>.
  Its least-authority principle motivates bounded page sources and explicit
  read capabilities; Pocket Rocket does not claim an OS sandbox on platforms
  where none is activated.

### Quantization and runtime format review

- NVIDIA Model Optimizer documentation:
  <https://nvidia.github.io/TensorRT-Model-Optimizer/>. It surveys PTQ/QAT,
  mixed precision, pruning, distillation, speculative decoding, and hardware-
  specific formats. Pocket Rocket does not import NVIDIA code or advertise a
  CUDA path; the useful portable lesson is explicit, measured format choice.
- AMD Quark documentation:
  <https://quark.docs.amd.com/latest/>. Quark covers integer, FP8, OCP MX,
  per-channel/group quantization, calibration, AWQ/GPTQ, and export. Pocket
  Rocket keeps its CPU-only exact control plane and does not relabel these
  floating formats as ternary.
- Microsoft BitNet repository and 1-bit LLM inference paper:
  <https://github.com/microsoft/BitNet> and
  <https://arxiv.org/abs/2502.11880>. Native packed ternary inference supports
  the architectural rule that trits should be consumed directly rather than
  translated through a binary/floating compatibility layer. Pocket Rocket's
  existing direct sign-plane kernel follows that rule; it does not claim a
  converted BitNet model.
- llama.cpp quantization documentation and source:
  <https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md>
  and <https://github.com/ggml-org/llama.cpp/tree/master/src>. The numerous
  K/I/TQ formats show why tensor-format conversion requires graph-aware,
  quality-measured implementation rather than byte-wrapper renaming.
- vLLM compressed-tensors documentation:
  <https://docs.vllm.ai/en/latest/features/quantization/>. Its unified format
  supports mixed precision, sparsity, transforms, and offloading. Pocket
  Rocket adopts only the general principle of explicit format metadata and
  measured selection, not its implementation.

### Lossless page transform review

- HDF5 shuffle filter documentation:
  <https://support.hdfgroup.org/documentation/hdf5/latest/group___h5_p.html>.
  Byte-lane shuffle is a reversible preconditioner that can improve a following
  compressor on fixed-width numeric data.
- Zstandard seekable format:
  <https://github.com/facebook/zstd/blob/dev/contrib/seekable_format/zstd_seekable_compression_format.md>.
  Independent frames support random access. Pocket Rocket already has fixed,
  independently authenticated pages, so v0.2 preserves that boundary and uses
  the standard-library DEFLATE implementation for zero new dependencies.

The review did not justify importing vendor GPU stacks, adding a second model
host, or copying external source. The implemented result is the smallest
license-clean intersection: direct ternary control math, exact ordered
decisions, and per-page lossless transform competition with authenticated
random access.

## Pocket Rocket 0.3 recursive-fabric review

- Yubin Kim et al., *Towards a Science of Scaling Agent Systems*:
  <https://arxiv.org/abs/2512.08296>. Its controlled study reports coordination
  overhead, capability saturation, and topology-dependent error amplification.
  Pocket therefore uses 1,024 cheap routing cells but activates only a bounded
  quorum, rather than treating agent count as a quality metric.
- Google DeepMind, *AlphaEvolve*:
  <https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/>.
  The transferable principle is generation followed by automated evaluation.
  Pocket implements deterministic routing and an exact agreement evaluator;
  it does not copy AlphaEvolve or claim algorithm-discovery results.
- Microsoft Agent Framework workflow concepts:
  <https://learn.microsoft.com/en-us/agent-framework/concepts/workflows/>.
  Explicit graph paths, typed executors, events, checkpoints, and bounded
  fan-out/fan-in informed Pocket's inspectable plan/transcript boundary. Pocket
  has no dependency on that framework.
- Pentti Kanerva, *Hyperdimensional Computing: An Introduction to Computing in
  Distributed Representation with High-Dimensional Random Vectors*, Cognitive
  Computation 2009: <https://doi.org/10.1007/s12559-009-9009-8>. Pocket uses a
  finite 1,024-bit vector-symbolic routing layer: token vectors are derived by
  SHAKE-256, bundled with integer majority, and compared by exact Hamming
  distance.
- Alex Graves, Greg Wayne, Ivo Danihelka, *Neural Turing Machines*:
  <https://arxiv.org/abs/1410.5401>. Memory-augmented differentiable machines
  were reviewed but not imported: Pocket's requirement is inspectable exact
  control, so its graph and transcript are ordinary bounded symbolic state,
  while neural generation remains inside the pinned model.

The resulting mechanism is an experimental architecture, not a proven
scientific breakthrough. Its novel combination is finite HDC/VSA capability
routing, direct three-state recursion control, a single locked model transport,
and content-addressed execution evidence. Answer quality still requires a
task-suite comparison against the single-agent baseline on the target model.
