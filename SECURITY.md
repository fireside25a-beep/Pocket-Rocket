# Security and trust boundaries

## Untrusted inputs

Model files, manifests, page bytes, NPRQ/Flat32/Pocket Pack containers, prompts, proposal text, CLI JSON, checkpoint NPZ files, and any existing runtime directory are treated as untrusted. Readers validate lengths before allocation, enforce configured maxima, authenticate committed bytes, reject path traversal/symlink escapes where applicable, and fail closed on corruption or contract mismatch.

## Trusted anchors

The repository commits immutable SHA-256 identities for the selected model artifact and a fixed DS4 revision. These identifiers are trust anchors, not redistributed third-party content. DS4 remains separately licensed under MIT at its pinned upstream revision; this repository does not vendor its source or weights.

## Runtime installation

`install_ds4` checks an existing checkout's Git identity and dirty state before any clone/fetch operation. Build/update work occurs in `runtime/ds4.installing`; a verified tree is swapped into place transactionally, with `ds4.previous` used only as crash recovery. The install manifest is fsync'd to a temporary file and atomically published with `os.replace`.

## Process boundary

The DS4 transport is loopback/local only. Child and descendant RSS are measured through `/proc`, a hard timeout is enforced, and timeout/RSS violations send TERM to the process group followed by KILL after a bounded grace period. Non-zero exit and empty output fail closed.

## Recursive governance

Planning metadata is not trusted as enforcement. Before every model invocation the runtime independently checks maximum depth, executed nodes, and model-call count. Every invocation is recorded as `(depth, parent_node, child_node, cell_id, model_call_index)` and committed by a recursion-trace SHA-256. The outer run certificate commits the trace again.

## Cache and journal integrity

Canonical envelopes use stable JSON serialization and SHA-256 identity. Committed history is hash chained. A missing certificate, unknown coupling edge, inconsistent runtime contract, or corrupt storage object never authorizes a partial decision path.

Security issues should include a minimal reproducer, affected version, and whether the failure crosses a trust boundary. Do not attach proprietary model weights or secrets.
