# Modules, formatter, and source spans

`dxresolve24` reads a non-programmable project manifest with an entry and named modules. Paths must be relative and traversal-free. Duplicate names, unknown keys, missing modules, and cycles fail closed.

Resolution inserts stable `namespace:<name>` and `endnamespace` markers. These markers do not change runtime semantics but preserve module identity in flattened source and deterministic source checksums.

Commands:

```sh
dxresolve24 graph project.dxp
dxresolve24 watch project.dxp --once
dxresolve24 resolve project.dxp -o flattened.dxs
dxdev24 fmt flattened.dxs -o formatted.dxs
dxdev24 fmt formatted.dxs --check
```

The formatter is deterministic and idempotent for the supported DXS token grammar. `aegis2 compile --json` maps byte offsets to one-based line and column records. It is not yet an LSP or incremental parser.

`watch --once` emits a content fingerprint graph. A continuously running rebuild daemon is intentionally not claimed in this foundation.
