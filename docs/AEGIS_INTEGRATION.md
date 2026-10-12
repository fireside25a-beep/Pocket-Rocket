# Aegis integration guide

This integration runs the supplied, verified Aegis 2.4.3 tools. It does not
reimplement the language parser as Python or use mock interpreters.

## Component ownership

- `toolchains/aegis-language-suite-2.4.3/`: unchanged upstream language,
  compiler, runtime, tests, docs, Linux binaries and manifests; build outputs
  remain local and are excluded from source packaging.
- `src/neuro_inverse/aegis_runtime.py`: narrow glue that invokes real
  `dxlc`, `dxscc`, `dxasm`, `dxaudit` and `dxvm` without `shell=True`.
- `src/neuro_inverse/aegis_boundary.py`: optional storage-aware classification
  and external tool capability discovery. No hidden fallback compiler.
- `toolchains/aegis-c2r-0.1.0/`: independently versioned full S0 translator
  including its isolated, historical Aegis 2.4.0 source-bootstrap fixture.

## Running and building

Aegis shipped tools require Linux x86-64, glibc >= 2.34, and the ELF loader
at `/lib64/ld-linux-x86-64.so.2`. They are not run on macOS or other CPU
architectures. `prepare()` checks these requirements via Aegis setup. The
emitted native DXL executable is statically linked but is still Linux x86-64.

```bash
make aegis-test                 # unit + live compiler/VM integration suite
make aegis-full-test            # suite make check + maintainer source gates
make c2r-test                   # independent, full 37-gate C2R release corpus
PYTHONPATH=src python -m neuro_inverse aegis-run toolchains/aegis-language-suite-2.4.3/examples/loops/dxl/native_counter.dxl
PYTHONPATH=src python -m neuro_inverse aegis-c2r-check toolchains/aegis-c2r-0.1.0/tests/positive/basic.c
PYTHONPATH=src python -m neuro_inverse aegis-c2r-translate toolchains/aegis-c2r-0.1.0/tests/positive/basic.c /tmp/pocket-c2r-output
```

`aegis-run` returns JSON with executed stdout, backend, artifact SHA-256 and,
for VM execution, proof SHA-256. DXL is genuinely compiled and launched as
an executable, while DXS/DXASM generate audited DXB3 and run on the VM.
No Aegis stage is called by `/ask` or ds4 inference.

## Supported boundary

The Aegis 2.4.3 native DXL path implements the documented **bounded native
core profile**, not arbitrary DXL and not self-hosting. Its broader
check/emit-tir/fmt commands remain a compatibility-frontend profile. The
standalone Aegis docs explain exact grammar and diagnostic contracts.
Aegis-C2R admits the **S0-defined-i32** C subset; it is not a general C-to-Rust
migration engine.

Aegis's `maintainer-check` includes a byte-for-byte comparison between a
locally rebuilt native compiler and the shipped compiler. This exact identity
is environment-pinned to the upstream Ubuntu 24.04 validation environment.
If it fails on another toolchain/host, report it as a failure of *that gate*;
never replace or relabel the original checksum-pinned binaries.

Archive extraction: standard `unzip` preserves the executable flags in this
release. If an extraction program discards them (for example Python's
`zipfile.extractall`), `make aegis-test`, `make aegis-suite-check` and
`make c2r-test` automatically restore the known flags before running.
This restoration changes file mode bits only, not release-hashed bytes.
