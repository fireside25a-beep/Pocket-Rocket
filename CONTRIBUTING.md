# Contributing

Changes are accepted only when the executable contract remains stricter than the prose. No mocks, placeholder implementations, silent fallbacks, hidden network backends, or unmeasured performance claims belong in the production tree.

Every new persisted format must have a Python reader, a bounded native reader when a native format path exists, a valid round-trip test, corrupted/truncated/oversized-input tests, and deterministic identity checks. Every new native API must have a declaration, definition, real test consumer, and sanitizer coverage. Every new runtime limit must have both validation and an execution-time test proving that the limit actually stops work.

Run before submitting:

```bash
python -m pip install -e .
make test
make -C native test
make -C native test-asan
make -C native test-ubsan
python scripts/runtime_surface_audit.py
python scripts/archive_check.py .
```

If a measurement was not run, write `NOT_RUN` with the reason. Do not convert an estimate, paper result, or result from another machine into a local benchmark claim.
