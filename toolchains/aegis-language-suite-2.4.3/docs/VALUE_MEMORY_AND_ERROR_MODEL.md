# Value, memory, UTF-8, and error model

## Owned buffers and immutable slices

`buffer:<hex>` creates an owned buffer. Ownership is linear at runtime:

- an owned buffer handle cannot be duplicated;
- stack movement transfers the handle;
- `buffer::freeze` consumes the mutable state by retagging the same generation-checked object as immutable;
- `bytes::slice` narrows the immutable view in place without allocating another heap object;
- `free` ends the lifetime;
- stale handles, double free, out-of-bounds access, and mutation through an immutable slice are rejected.

The verifier computes stack, step, embedded-data, and heap demand. Object-kind transfer restrictions are additionally enforced by both VMs at runtime.

## UTF-8 text

Text is not an implicit host string. `text:<hex>` is a typed byte payload accepted only when it is canonical valid UTF-8. `text::validate` can validate an existing byte value. `text::write` requires both a validated text object and the byte-output capability. Text slicing must begin and end on UTF-8 boundaries.

Normalization, locale collation, grapheme segmentation, and a complete Unicode database are not included.

## Structured errors

`error:<code>` creates a tagged structured error value. Supported operations are:

- `error::is`;
- `error::code`;
- `error::try`, which propagates by terminating the bounded run with deterministic error `2000 + code`.

This is a small deterministic error-value foundation, not exceptions, stack unwinding, or a complete algebraic result type for all DXL code.

## Exact accounting

Policy version 2 binds the header heap field to verifier-computed demand. Embedded byte/text literals contribute their exact byte count. Dynamic legacy allocation remains conservatively charged against the profile maximum when an exact size cannot be proven.
