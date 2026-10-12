# 2026-10-12 local validation evidence

- `qualification.log`: output of the root `make qualification`, including Python, GTK contract, GCC native sanitizer, Aegis suite standard checks and 37/37 independent C2R gates.
- `native-clang.log`: actual strict Clang, AddressSanitizer and UndefinedBehaviorSanitizer native test output.
- `aegis-maintainer-gate.log`: failed Aegis source-rebuild-vs-shipped-byte compiler identity gate. This failure is **not** suppressed.
- `archive-audit.log`: static source credential/model-archive audit result.
- `fresh-unzip-qualification.log`: the full qualification retested after GNU `unzip` from the packaged archive.
- `RESULTS.json`: machine-readable summary, with SHA-256 for these logs.

These logs are local observations, not externally signed attestations. Missing model weights and target hardware mean no inference benchmark or 16 GiB acceptance is claimed. Aegis 2.4.3 and C2R's historical isolated Aegis 2.4.0 are different version boundaries.
