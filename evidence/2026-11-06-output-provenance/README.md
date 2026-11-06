# Output and receipt provenance review

Reviewed on 2026-11-06 against upstream commit
`459c023e7a96eef0ee5325274337a58a41dd697a`.

## Corrected behavior

The guarded native transport previously merged stderr into stdout. A successful
process writing diagnostics only could therefore be accepted as an inference
answer, and diagnostics could enter recursive proposals and their answer hashes.
The transport now drains both pipes concurrently, returns stdout only, rejects
empty or whitespace-only stdout, and keeps a bounded 12,000-character stderr tail
for failed execution. The existing timeout and process-tree RSS limits remain in
place. This is a channel-separation fix, not a general subprocess-tree hardening
claim.

Receipt construction previously accepted explicit model/request roots different
from roots already committed in the verified source transcript. It now rejects
either mismatch, including CLI overrides. Matching roots and explicit metadata
for transcripts that omit the roots remain supported. Supplying absent metadata
does not independently authenticate its external meaning. No hash collision or
cryptographic forgery is claimed.

`tests/test_output_provenance.py` adds 17 executable tests. These use real Python
subprocesses, CLI calls, receipt construction, and recursive execution. The
processes exercise transport contracts; they are not model inference. Coverage
includes stderr-only output, whitespace-only stdout, Unicode without a final
newline, concurrent 1 MiB writes on both pipes, bounded error diagnostics,
proposal/answer hashing, and receipt identity through both API and CLI.

## Results

Logs are included in this directory.
Workspace prefixes in logs are replaced with `<workspace>`; other output is
preserved. SHA-256 values cover the changed source, tests, this report and logs.

| Check | Observed result |
| --- | --- |
| Same 17 regressions against unchanged upstream source | 10 failing test methods, 11 assertion failures including two CLI subtests; 7 methods pass; no errors |
| Same regressions against patched source | 17/17 pass |
| Full Python discovery | 186/186 pass, including the new 17 |
| GTK source contracts | 6/6 pass; this is not an interactive GTK test |
| Shell syntax and runtime surface audit | Pass |
| Native GCC normal, ASan and UBSan targets | Pass; upstream native ASan target disables leak detection |
| Native Clang and AVX2 TCAM targets | Pass |
| Aegis 2.4.3 standard check | 105 base, 33 native-profile, 40 strict and 20 DXL source groups pass; structural gates pass |
| Additional Aegis Python target | 9/9 pass; these duplicate tests already in the 186 |
| Aegis-C2R official release gate | 36/37 pass; sanitizer corpus gate fails at LeakSanitizer initialization |
| Aegis-C2R optional Rust compile/run gate | Pass using rustc 1.85.1 |
| Supplemental C2R ASan+UBSan corpus, `detect_leaks=0` | 8 positive and 18 negative cases pass, expected exit codes and no sanitizer diagnostics |
| Aegis maintainer check | Fails at source-rebuilt versus shipped compiler byte identity, as already documented upstream |
| Editable package build/install | Pass with installed dependencies, `--no-deps --no-build-isolation` |
| Archive check | Pass |

**`make qualification` does not pass overall on this host.** Its final C2R
subtarget fails as recorded above. Supplemental sanitizer success must not be
reported as an official 37/37 result. The official gate and vendored binaries
have not been changed to hide either failure.

A standalone `int main(void) { return 0; }` compiled with GCC
`-fsanitize=address,undefined` also fails with
`ASAN_OPTIONS=detect_leaks=1:halt_on_error=1` and succeeds with `detect_leaks=0`.
The diagnostic says LeakSanitizer encountered a fatal error and mentions ptrace;
that message does not establish that this process was actually traced.
This isolates an environment limitation independently of the C2R source.
Leak detection remains unqualified and needs a compatible host.

Environment: Linux x86-64, AMD EPYC 9V74, Python 3.12.14, NumPy 2.3.5,
GCC 14.2.0, Debian Clang 19.1.7, rustc 1.85.1. Clang and Rust were extracted
locally from packages downloaded using authenticated Debian snapshot metadata;
system privileges were not available. Cargo was not required or installed.

## Reproduction

With the dependencies installed and `gcc`, `clang` and `rustc` on PATH:

```sh
PYTHONPATH=src python -m unittest tests.test_output_provenance -v
make qualification
make -C native test-clang test-avx2
make -C toolchains/aegis-language-suite-2.4.3 maintainer-check
python scripts/archive_check.py .
```

For the negative control, run this branch's test file from the repository root
with `PYTHONPATH` pointing at an unchanged checkout of the upstream SHA's `src`.
The test imports then come from that baseline, while the assertions stay identical.

## Unmeasured boundaries

Full pinned GGUF inference and the context ladder are **NOT_RUN**. The pinned
model requires 86,720,111,488 bytes; this workspace's entire filesystem is
smaller than that. No language-model throughput, time-to-first-token, answer
quality, target 16 GiB acceptance, or cross-machine reproducibility is claimed.
The separate native microbenchmarks are not model-generation measurements.

This patch does not modify model weights, native numerical kernels, routing
algorithms, toolchain certificates, vendored compiler bytes or the official
release gates. Historical release evidence remains historical; this review is
not a new fully qualified release.
