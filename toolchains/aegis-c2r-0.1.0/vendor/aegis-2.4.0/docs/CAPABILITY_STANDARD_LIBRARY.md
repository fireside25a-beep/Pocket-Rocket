# Capability-aware standard-library foundation

## Deterministic collections

`stdlib/deterministic_collections.dxl` provides a fixed-capacity ordered map over caller-owned parallel slices. Keys remain ascending and unique. There is no randomized hash seed and no iteration-order ambiguity.

## Serialization

- `stdlib/serialization.dxl` provides checked little-endian non-negative i63 primitives.
- `dxdev24 data-json` writes canonical `DXJSON1` integer arrays.
- `dxdev24 data-bin` writes canonical little-endian `DXBIN1` arrays with signed 64-bit values.

## Narrow capabilities

`dxdev24` requires the exact declaration `file-read,file-write` for data input/output. `fixed-time` requires the `time` capability and accepts an explicit Unix timestamp; it never reads the host wall clock. Process and network capabilities are reported as disabled and have no implementation path in this release.

## Packages and lockfiles

`dxdev24 lock` accepts a traversal-free list of package files, sorts paths, rejects duplicates, and records byte length plus SHA-256 in `DXLOCK1`. The lockfile is immutable content identity, not a remote registry client.

## Tests and snapshots

`tests/run_2_4_tests.sh` supports group filtering through its argument or `DX_TEST_FILTER`. The real CLI output is checked against `examples/apps/aegis24_cli.snapshot`; updates require the explicit `UPDATE_SNAPSHOTS=1` environment variable.

## Release-gate applications

- package utility: deterministic local lockfile generation;
- bounded data application: integer input to canonical JSON and binary output;
- both operate only through narrow declared file capabilities and perform no unrestricted process or network calls.
