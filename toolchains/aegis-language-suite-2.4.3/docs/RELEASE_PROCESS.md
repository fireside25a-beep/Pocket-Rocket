# Release process

The archive is produced from the same standalone tree that passes the release gate. Generated build files, repository metadata, and previously generated archives are excluded.

## Pre-release checklist

1. Confirm that `VERSION`, `CITATION.cff`, `CHANGELOG.md`, and `RELEASE_NOTES.md` name the same release.
2. Confirm that [Support](SUPPORT.md) and [Implementation status](IMPLEMENTATION_STATUS.md) describe only behavior exercised by a gate.
3. Synchronize the native diagnostic registry and refresh `toolchain/linux-x86_64/SHA256SUMS.txt` after any bundled-tool change.
4. Regenerate committed loop evidence with `make matrix`.
5. Refresh the repository manifest after every tracked-file change with `make manifest`.
6. Run `make clean && make check` on the supported host profile.
7. In the pinned Ubuntu 24.04 x86-64 maintainer environment, run `make maintainer-check` to rebuild and compare all reproducible shipped tools.
8. Run `make release` and compare a second package build byte for byte.

## Packaging behavior

`make release` reruns the maintainer gate, stages only release files, normalizes timestamps, orders archive members lexically, removes extra ZIP metadata, and writes:

```text
dist/Aegis-Language-Suite-2.4.3.zip
dist/Aegis-Language-Suite-2.4.3.zip.sha256
```

The packaging script tests the ZIP container, rejects symbolic links and nested archives, extracts it into a temporary clean directory, and runs the installed `make check` gate again from the extracted copy. Source reproduction remains the outer maintainer gate because it is pinned to the release-builder environment.

## Publication

1. Inspect the generated file list with `unzip -Z1`.
2. Verify the archive checksum with `sha256sum -c`.
3. Tag the exact tested commit as `v2.4.3`.
4. Publish the ZIP and its checksum with the text from `RELEASE_NOTES.md`.
5. Present the tested ZIP prominently and state that automatically generated repository snapshots are not the release-tested artifact.

A release should never claim a target, backend, safety property or compatibility guarantee that was not exercised by the corresponding release gate.
