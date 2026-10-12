# Third-party notices

This repository is licensed under MIT (`LICENSE`). It does not redistribute the pinned GGUF model or the DS4 source tree.

The runtime installer refers to `antirez/ds4` at the immutable revision recorded in `src/neuro_inverse/ds4_runtime.py`. DS4 is an upstream MIT-licensed project; when fetched, its own `LICENSE` remains in that separate runtime checkout. Model artifact identity is recorded as repository/revision/size/SHA-256 only; model licensing remains with its upstream distributor.

Python installation requires NumPy. Optional download tooling may require additional dependencies declared separately under `project.optional-dependencies`.

## Bundled language components

`toolchains/aegis-language-suite-2.4.3/` retains its original MIT `LICENSE`,
copyright, compiler sources, test corpora and standalone release checksums.
`toolchains/aegis-c2r-0.1.0/` retains its own MIT `LICENSE`, C-to-Rust source,
negative corpus, and `vendor/aegis-2.4.0/` with its original MIT license.
The older 2.4.0 code is confined to C2R's independent provenance/test gate;
it is never silently substituted for the active 2.4.3 compiler/VM. No project
licenses are removed, combined, or relicensed.
