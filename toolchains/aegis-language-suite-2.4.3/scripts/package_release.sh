#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '\r\n' < "$ROOT/VERSION")"
NAME="Aegis-Language-Suite-$VERSION"
DIST="$ROOT/dist"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$DIST"
archive="$DIST/$NAME.zip"
stage="$TMP/$NAME"
mkdir -p "$stage"

(
  cd "$ROOT"
  while IFS= read -r -d '' source; do
    relative="${source#./}"
    mkdir -p "$stage/$(dirname "$relative")"
    cp -p "$source" "$stage/$relative"
  done < <(find . \
    -path './build' -prune -o \
    -path './dist' -prune -o \
    -path './.git' -prune -o \
    -type f -print0)
)

epoch="${SOURCE_DATE_EPOCH:-1786060800}"
find "$stage" -exec touch -h -d "@$epoch" {} +

archive_tmp="$TMP/$NAME.zip"
(
  cd "$TMP"
  find "$NAME" -type f -print | LC_ALL=C sort | zip -X -q "$archive_tmp" -@
)

cp "$archive_tmp" "$archive"
(cd "$DIST" && sha256sum "$NAME.zip" >"$NAME.zip.sha256")

unzip -tq "$archive" >/dev/null
extract="$TMP/extracted"
mkdir -p "$extract"
unzip -q "$archive" -d "$extract"
test -f "$extract/$NAME/VERSION"
test "$(tr -d '\r\n' < "$extract/$NAME/VERSION")" = "$VERSION"

if find "$extract/$NAME" -type l -print -quit | grep -q .; then
  printf 'release archive verification failed: symbolic link found\n' >&2
  exit 1
fi

if find "$extract/$NAME" -type f \( \
    -iname '*.zip' -o -iname '*.7z' -o -iname '*.rar' -o \
    -iname '*.tar' -o -iname '*.tgz' -o -iname '*.gz' -o \
    -iname '*.bz2' -o -iname '*.xz' \) -print -quit | grep -q .; then
  printf 'release archive verification failed: nested archive found\n' >&2
  exit 1
fi

(cd "$extract/$NAME" && make check >/dev/null)

printf 'release archive: %s\n' "$archive"
printf 'release checksum: %s\n' "$archive.sha256"
printf 'clean extraction gate: PASS\n'
