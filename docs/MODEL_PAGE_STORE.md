# Authenticated model page store

## Why it exists

The pinned GGUF is 86,720,111,488 bytes. The former 64 GiB bounds in Pocket
Pack, Flat32, and their native readers made the selected model structurally
unrepresentable. Version 0.2 keeps the whole-model ceiling at 128 GiB;
the page and range bounds remain 64 MiB and 256 MiB.

The page store provides one identity for two installation modes:

- **static** materializes and verifies every page up front;
- **demand** authenticates and caches a page only when a bounded range needs
  it.

Both modes consume the same manifest and expose the same `model_root`.

## Identity and encoding

Pages are fixed power-of-two extents, one MiB by default. Dyadic page sizing is
intentional: it matches file and virtual-memory alignment, while computation
uses triadic values. Every raw page has a SHA-256 digest. Domain-separated
leaf and internal hashes form a Merkle tree; the final root also commits the
source size, page size, page count, and complete-source SHA-256.

A cached v2 page evaluates five real encodings: raw, DEFLATE, and 2-, 4-, or
8-byte shuffle followed by DEFLATE. Byte shuffle groups equal byte lanes from
fixed-width words, which can expose structure in numeric tensors without
changing a bit. The smallest measured payload wins; codec ID is the canonical
tie break. Codec choice is not part of model identity, so v1 raw/DEFLATE pages
remain readable and static and demand stores retain the same model root.

`model-analyze` runs the same selector without populating the cache. It reports
source bytes, complete stored bytes including every page header, codec counts,
a reduced exact source/stored ratio, and a SHA-256 decision root that commits
the per-page candidate sizes and selected codec. It also reauthenticates every
page and the complete source digest.

This is a secure page transform, not a compression-ratio promise. An already
quantized GGUF may be incompressible.

## Workflow

```sh
PYTHONPATH=src python -m neuro_inverse model-manifest MODEL.gguf MODEL.pages.json

PYTHONPATH=src python -m neuro_inverse model-analyze \
  MODEL.pages.json MODEL.gguf

PYTHONPATH=src python -m neuro_inverse model-import \
  MODEL.pages.json MODEL.gguf STORE --mode static

PYTHONPATH=src python -m neuro_inverse model-import \
  MODEL.pages.json MODEL.gguf STORE --mode demand

PYTHONPATH=src python -m neuro_inverse model-read \
  MODEL.pages.json MODEL.gguf STORE OFFSET LENGTH OUTPUT

PYTHONPATH=src python -m neuro_inverse model-verify-cache MODEL.pages.json STORE
```

The manifest command must finish one complete read of the source. A remote
demand installer needs this precomputed trusted manifest; a whole-file hash by
itself cannot authenticate an arbitrary range without reading all other bytes.

## Security properties

- Manifest schemas and page order are closed and canonical.
- Object paths derive only from validated lowercase SHA-256 text.
- Writes use same-directory unique temporary files, `fsync`, and atomic
  replacement.
- A changed source, corrupted cache object, decompression overrun, trailing
  compressed bytes, range overflow, or root mismatch fails closed.
- Cache objects are size-bounded before allocation and must be regular files;
  store roots, object directories, shards, manifests, and sources reject
  terminal symbolic links.
- `model-read` refuses outputs that alias the source or manifest or reside in
  the store. Output replacement is same-directory, synced, and atomic.
- The source remains read-only; static and demand operations never modify it.
