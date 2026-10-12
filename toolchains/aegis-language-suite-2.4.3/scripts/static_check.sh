#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() {
  printf 'static check failed: %s\n' "$1" >&2
  exit 1
}

[[ "$(tr -d '\r\n' < "$ROOT/VERSION")" == '2.4.3' ]] || fail 'VERSION is not 2.4.3'
grep -qx 'version: 2.4.3' "$ROOT/CITATION.cff" || fail 'CITATION.cff version mismatch'
grep -q '^# Aegis Language Suite 2\.4\.3$' "$ROOT/README.md" || fail 'README release title mismatch'
grep -q '^# Aegis Language Suite 2\.4\.3$' "$ROOT/RELEASE_NOTES.md" || fail 'release-notes title mismatch'
grep -q '^## 2\.4\.3' "$ROOT/CHANGELOG.md" || fail 'CHANGELOG release entry missing'

if find "$ROOT" \
    -path "$ROOT/build" -prune -o \
    -path "$ROOT/dist" -prune -o \
    -type l -print -quit | grep -q .; then
  fail 'symbolic link found'
fi

if find "$ROOT" \
    -path "$ROOT/build" -prune -o \
    -path "$ROOT/dist" -prune -o \
    -type f \( \
    -iname '*.zip' -o -iname '*.7z' -o -iname '*.rar' -o \
    -iname '*.tar' -o -iname '*.tgz' -o -iname '*.gz' -o \
    -iname '*.bz2' -o -iname '*.xz' \) -print -quit | grep -q .; then
  fail 'nested archive found'
fi

if find "$ROOT" \
    -path "$ROOT/build" -prune -o \
    -path "$ROOT/dist" -prune -o \
    -type f \( \
    -name '*.c' -o -name '*.h' -o -name '*.cc' -o -name '*.cpp' -o \
    -name '*.py' -o -name '*.pyc' -o -name '*.rs' -o -name '*.zig' -o \
    -name '*.go' -o -name '*.java' -o -name '*.js' -o -name '*.ts' \) -print -quit | grep -q .; then
  fail 'foreign implementation source found'
fi

if rg -n -i \
    --glob '*.md' --glob '*.dxl' --glob '*.sh' --glob '*.yml' \
    --glob '*.cff' --glob 'Makefile' \
    --glob '!scripts/static_check.sh' \
    --glob '!build/**' --glob '!dist/**' \
    '(2\.4\.0|2\.4\.1|2\.4\.2|2\.5\.0|2\.5\.0-dev|dxlc_stage0|dualpath|emit-c|source bootstrap)' \
    "$ROOT" >/dev/null; then
  fail 'historical or unsupported implementation reference found'
fi

if rg -n '[[:blank:]]+$' \
    --glob '*.md' --glob '*.dxl' --glob '*.dxs' --glob '*.dxasm' \
    --glob '*.sh' --glob '*.yml' --glob '*.yaml' --glob '*.cff' \
    --glob '*.txt' --glob '*.tsv' --glob 'Makefile' \
    --glob '!build/**' --glob '!dist/**' "$ROOT" >/dev/null; then
  fail 'trailing whitespace found'
fi

if rg -n '^(<<<<<<<|=======|>>>>>>>)' \
    --glob '!build/**' --glob '!dist/**' "$ROOT" >/dev/null; then
  fail 'merge-conflict marker found'
fi

unexpected_files="$(
  cd "$ROOT"
  find . \
    -path './build' -prune -o \
    -path './dist' -prune -o \
    -type f -printf '%p\n' |
    awk '
      /^\.\/toolchain\/linux-x86_64\/(bin|libexec)\// { next }
      /^\.\/\.(editorconfig|gitattributes|gitignore)$/ { next }
      /^\.\/(LICENSE|Makefile|VERSION)$/ { next }
      /\.(audit|bin|cff|check|dxb|dxasm|dxl|dxs|md|out|proof|sh|tir|tsv|txt|ya?ml)$/ { next }
      { print }
    '
)"
[[ -z "$unexpected_files" ]] || {
  printf '%s\n' "$unexpected_files" >&2
  fail 'unexpected file type found'
}

while IFS= read -r -d '' script; do
  bash -n "$script"
done < <(find "$ROOT" \
  -path "$ROOT/build" -prune -o \
  -path "$ROOT/dist" -prune -o \
  -type f -name '*.sh' -print0)
bash -n "$ROOT/toolchain/linux-x86_64/bin/dxlc"

link_fail=0
while IFS= read -r -d '' markdown; do
  while IFS= read -r token; do
    target="${token#](}"
    target="${target%)}"
    target="${target%%#*}"
    case "$target" in
      ''|http://*|https://*|mailto:*|'#'*) continue ;;
    esac
    if [[ ! -e "$(dirname "$markdown")/$target" ]]; then
      printf 'broken link: %s -> %s\n' "${markdown#"$ROOT/"}" "$target" >&2
      link_fail=1
    fi
  done < <(rg -o '\]\([^)]*\)' "$markdown" || true)
done < <(find "$ROOT" \
  -path "$ROOT/build" -prune -o \
  -path "$ROOT/dist" -prune -o \
  -type f -name '*.md' -print0)
[[ "$link_fail" -eq 0 ]] || fail 'local Markdown link check failed'

(cd "$ROOT/toolchain/linux-x86_64" && sha256sum -c SHA256SUMS.txt >/dev/null)
(cd "$ROOT" && sha256sum -c SHA256SUMS.txt >/dev/null)
[[ "$($ROOT/toolchain/linux-x86_64/bin/dxlc version)" == 'dxlc 2.4.3' ]] || fail 'public compiler version mismatch'
cmp "$ROOT/compiler/dxl/native/diagnostics.tsv" \
  "$ROOT/toolchain/linux-x86_64/libexec/dxlc-native-diagnostics.tsv" >/dev/null || \
  fail 'native diagnostic maps differ'
awk -F '\t' '
  NR == 1 { next }
  NF != 3 || $1 !~ /^[0-9]+$/ || seen[$1]++ || $3 == "" { exit 1 }
' "$ROOT/compiler/dxl/native/diagnostics.tsv" || fail 'native diagnostic map is malformed or contains duplicate codes'

help="$($ROOT/toolchain/linux-x86_64/bin/dxlc --help)"
for command in check build run test emit-tir fmt targets version; do
  grep -q "dxlc $command" <<<"$help" || fail "public command missing from help: $command"
done
[[ "$($ROOT/toolchain/linux-x86_64/bin/dxlc targets)" == $'native -> x86_64-unknown-linux-gnu\nx86_64-linux -> x86_64-unknown-linux-gnu' ]] || \
  fail 'public target list mismatch'

"$ROOT/scripts/check_sources.sh"

printf 'static repository hygiene: PASS\n'
printf 'local documentation links: PASS\n'
printf 'toolchain checksums: PASS\n'
printf 'repository manifest: PASS\n'
printf 'public DXL command and target boundary: PASS\n'
