# Aegis and Pocket Rocket: enforced separation

Pocket Rocket ships **real, local Aegis 2.4.3 compiler and VM implementations** under
`toolchains/aegis-language-suite-2.4.3/`. These are the complete Aegis source,
tests, specifications, release checksums and pinned Linux x86-64 tools, retained
as a separately versioned component. The source is not merged or translated
into Pocket Rocket's model backend.

| Layer | Implementation | Input | Output |
|---|---|---|---|
| DXL native core | Aegis `dxlc build` | `.dxl` | native static Linux x86-64 ELF |
| DXS | Aegis `dxscc` | `.dxs` | `.dxb` (DXB3) |
| DXASM | Aegis `dxasm` | `.dxasm` | `.dxb` (DXB3) |
| Audit | Aegis `dxaudit` | emitted DXB3 | rejection or audit success |
| VM | Aegis `dxvm` | audited DXB3 and bundled policy | stdout and `.proof` |
| Pocket Rocket | local pinned ds4 model transport | authenticated GGUF | proposals |
| Lumus ARH | local WSGI `/ask`, `/reset` | bounded local JSON | guarded response |

The public Pocket Rocket API is `neuro_inverse.aegis_runtime.AegisRuntime`.
`prepare()` verifies the pinned toolchain's SHA256SUMS and installs to its
private `build/` directory. `execute(path)` rejects all but a real existing
`.dxl`, `.dxs`, or `.dxasm` source, compiles, audits where applicable, and
**executes** the result. Both DXB3 bytecode and VM proof hashes are returned.
Native DXL ELF does not claim DXB3 auditing; it uses its distinct checked
native compiler boundary. Toolchain setup never fetches dependencies online.

```bash
PYTHONPATH=src python -m neuro_inverse aegis-doctor
PYTHONPATH=src python -m neuro_inverse aegis-run toolchains/aegis-language-suite-2.4.3/examples/loops/dxs/counter.dxs
make aegis-test
```

## Isolation and versioning

`toolchains/aegis-c2r-0.1.0/` is a **separate**, source-complete, S0-profile
C-to-Rust translator. It retains its own older Aegis 2.4.0 bootstrap *inside
its private vendor directory* only to reproduce its original, independent
37-check release gate. **Do not** set Pocket Rocket's Aegis 2.4.3 toolchain
path to that 2.4.0 bootstrap. No test silently substitutes one for the other.
The translator is not a drop-in full C compiler and has no authority over
Pocket Rocket or Flat32 bytes. Its optional Rust compile/run gate needs rustc.

**Storage and weights never become compiler inputs.** `.gguf`,
`.safetensors`, `.pt`, `.pth`, `.onnx`, `.ckpt`, `.bin`, `.pkr`, `.pocket`,
`.flat32` and `.f32` are rejected by the source admission function. The VM's
only permitted `.bin` is the bundled Aegis policy whose exact one-byte
contents are checked separately (`03` hex). This is an explicit format-aware
exception for the VM's authorization input, not a general source exception.
The optional legacy `AegisBoundary` adapter remains for inspecting/hashing
Pocket Rocket storage or discovering an explicitly external executable tree.

The VM's policy and audit establish Aegis profile conformance within the
implemented toolchain; they are **not** proof of absence of malicious behavior
in arbitrary source. Execute untrusted programs only in an OS sandbox.
