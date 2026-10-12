# Release process

1. Update `VERSION` and `CHANGELOG.md`.
2. Run `make clean check` on a clean checkout.
3. Run `scripts/package_release.sh`.
4. Verify the generated SHA-256 manifest.
5. Tag the tested commit as `vX.Y.Z`.
6. Attach the generated source archive and checksum to the GitHub release.

A release should never claim a target, backend, safety property or compatibility guarantee that was not exercised by the corresponding release gate.
