# Pocket Rocket GTK workspace

The repository includes an optional native GTK4 client in `ui/`. It is a
separate user-space process, not part of the inference binary. This keeps the
model's memory/certificate boundary explicit while providing a practical local
coding surface: repository file tree, bounded source editor, guarded save,
loopback chat, ephemeral reset, Git status/diff/stage/unstage/commit, local
tests, task recording, and this documentation panel.

## Build and launch

The client requires a GTK4 development package and `pkg-config` on the target
host. Build it from the repository root:

```bash
make -C ui
./ui/pocket_rocket_workspace "$PWD"
```

The root can also be supplied through `POCKET_ROCKET_WORKSPACE`. The program
refuses a missing or non-directory root. The current environment was checked
while assembling this artifact: GCC is available, but `pkg-config` and GTK4
development headers are not installed, so the GTK binary was not compiled in
this workspace. `make -C ui` reports that condition and exits nonzero rather
than presenting an unbuilt binary as a pass.

Start the local Lumus service separately, for example with the project's
existing `neuro-inverse serve` command. The client connects only to
`127.0.0.1`; the port spinner defaults to 8000 and refuses privileged ports.
The request shapes are the recovered pre-React `POST /ask` and `POST /reset`
routes. No cloud endpoint, model library, or browser runtime is linked.

## Actions and safety

- Refresh enumerates regular repository files while skipping `.git`, model
  weights, runtime checkouts, caches, and Python bytecode. Symlinks are skipped.
- Selecting a file opens a bounded editor. Canonical-path checking prevents a
  file outside the workspace from being opened. Save requires the explicit
  `Confirm save` check for that operation, accepts only valid UTF-8 text with
  no NUL and at most 4 MiB, preserves permission bits, writes a same-directory
  temporary file, `fsync`s it, atomically renames it, and `fsync`s the parent
  directory. Symlinks and non-regular files are refused at save time as well
  as during enumeration.
- Ask local and Reset use a small POSIX socket client with a fixed loopback
  address. Request JSON is escaped locally; output is capped.
- Git status, Git diff, Make tests, stage, and unstage use fixed `argv` vectors
  with `fork` and `execvp`, an explicit `chdir` to the selected root, and no
  shell strings. Stage/unstage apply only to the selected file. Commit accepts
  a 1–512 character message, operates on already staged changes, and requires
  the separate `Confirm commit` check. The Git commit button is intentionally
  not an implicit stage-all or checkout/reset operation.
- Record task appends to `ui/tasks.log`, within the selected workspace. There
  is no delete, checkout, hard reset, upload, or other destructive filesystem
  action in the UI. Git hooks may run when the user explicitly confirms a
  commit, as they do for a normal local Git commit.

The write path is intentionally narrow: it edits one already-existing regular
text file and does not create arbitrary paths. A future image panel should be
added only after the runtime implements the private worker contract specified
in `IMAGE_RUNTIME_V1.md` and passes its memory, licence, payload, cancellation,
and certificate gates. No image worker exists in the current local API, so the
client does not ship a button that cannot perform a real action.

## Tests

The dependency-free source contract test can run anywhere:

```bash
python ui/test_workspace_source.py
```

It is also discoverable by a normal Python test runner. With GTK4 installed,
`make -C ui check` compiles the actual application with warnings enabled and
checks that the executable exists. No claim of a GTK compile is made when the
host lacks GTK headers.
