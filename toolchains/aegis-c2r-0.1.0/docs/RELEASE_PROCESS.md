# Release process

1. Run `make clean && make check`.
2. Keep `rustc` status explicit.
3. Render and visually inspect the engineering-manual PDF.
4. Commit the clean source tree with fixed release metadata.
5. Produce two deterministic inner ZIPs: Clean Git and Full AIO Linux x86-64.
6. Produce each ZIP twice from the same staging tree and require byte identity.
7. Test ZIP CRCs and safe relative paths.
8. Fresh-extract the Clean Git ZIP and require `git status --porcelain` to be empty.
9. Fresh-extract the Full AIO ZIP and run its included smoke verifier.
10. Seal both into the master handoff ZIP and publish SHA-256 values.
