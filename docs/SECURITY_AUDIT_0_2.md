# Security and architecture audit — 0.2

## Scope and reported issue

The reported signed/unsigned heap overwrite was in another product's CLI and
is not part of this MIT source tree. No code from that release is linked,
copied, or packaged here. Pocket Rocket's own path-list processing has no
corresponding `calloc(argc)`/unchecked append construct.

## Findings resolved in Pocket Rocket

| Severity | Finding | Resolution and regression |
| --- | --- | --- |
| High | A cache object was read with an unbounded `read_bytes()` before its authenticated raw length was enforced. | Object size is checked from an open regular-file descriptor before a bounded read. Oversized objects fail before decode/allocation. |
| High | A cache shard or object could be replaced with a symbolic link. | Store root, object directory, shards, and object files are checked; object reads use `O_NOFOLLOW` where available and `fstat` regular-file validation. |
| High | `model-read` could target its source or manifest and replace a protected input. | Resolved-path and device/inode alias checks reject source/manifest aliases, and outputs inside the page store are forbidden. |
| Medium | A manifest output could alias and replace its source. | `model-manifest` applies the same protected-input alias gate before hashing or writing. |
| Medium | Manifest and source terminal symlinks weakened path intent. | Both are opened through regular-file/no-follow checks. |
| Architectural | Raw/DEFLATE-only pages missed reversible structure in fixed-width tensor bytes. | v2 adds exact competition among raw, DEFLATE, and 2/4/8-byte shuffle+DEFLATE; every decode remains bounded and SHA-256 authenticated. |
| Architectural | Typed Gate/Choice lacked Jev-like ordered scoring while preserving a true third state. | Exact `ordered_score` emits a rational distribution and expected ordinal value, and abstains on ties or inadequate exact confidence. |

## Fail-closed properties

- Manifest schemas, digests, page order, sizes, codec IDs, and roots are closed.
- Decompression rejects overflow, underflow, unfinished streams, and trailing
  compressed data before page SHA-256 acceptance.
- Codec selection tries every admitted candidate and uses `(payload bytes,
  codec ID)` ordering; no content heuristic or floating estimate chooses it.
- Page writes and user output writes are unique same-directory temporaries,
  synced, then atomically replaced.
- Legacy v1 raw and DEFLATE cache pages remain readable, but v1 cannot claim a
  v2-only codec.

## Hard scientific boundary

The 86,720,111,488-byte pinned GGUF is not included. Therefore its actual
codec distribution and compression ratio, native DwarfStar generation,
context ladder, quality comparison, SSD traffic, and 16 GiB RSS gate require
the target machine. `model-analyze` performs the complete authenticated
measurement when that local file is present; no fixture result substitutes for
it.
