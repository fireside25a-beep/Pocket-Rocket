#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="$(tr -d '[:space:]' < "$ROOT/VERSION")"
DIST="$ROOT/build/dist"
NAME="Aegis-Language-Suite-$VER"
rm -rf "$DIST"; mkdir -p "$DIST/$NAME"
rsync -a --exclude '.git' --exclude 'build' "$ROOT/" "$DIST/$NAME/"
(
  cd "$DIST"
  find "$NAME" -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > "$NAME/SHA256SUMS.txt"
  TZ=UTC find "$NAME" -exec touch -h -t 202601010000 {} +
  zip -X -qr "$NAME.zip" "$NAME"
  sha256sum "$NAME.zip" > "$NAME.zip.sha256"
)
printf '%s\n' "$DIST/$NAME.zip"
