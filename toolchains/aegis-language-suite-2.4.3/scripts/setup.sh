#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
system="$(uname -s)"
machine="$(uname -m)"

if [[ "$system" != Linux || "$machine" != x86_64 ]]; then
  printf 'No bundled toolchain for %s-%s. This release bundle supports Linux-x86_64.\n' "$system" "$machine" >&2
  exit 2
fi

libc_report="$(getconf GNU_LIBC_VERSION 2>/dev/null || true)"
if [[ ! "$libc_report" =~ ^glibc[[:space:]]+([0-9]+)\.([0-9]+) ]]; then
  printf 'Bundled tools require glibc 2.34 or newer; this host did not report a compatible glibc.\n' >&2
  exit 2
fi
libc_major="${BASH_REMATCH[1]}"
libc_minor="${BASH_REMATCH[2]}"
if (( libc_major < 2 || (libc_major == 2 && libc_minor < 34) )); then
  printf 'Bundled tools require glibc 2.34 or newer; this host reports %s.\n' "$libc_report" >&2
  exit 2
fi
if [[ ! -e /lib64/ld-linux-x86-64.so.2 ]]; then
  printf 'Bundled tools require the x86-64 glibc dynamic loader at /lib64/ld-linux-x86-64.so.2.\n' >&2
  exit 2
fi

source_dir="$ROOT/toolchain/linux-x86_64/bin"
destination="$ROOT/build/bin"
libexec_destination="$ROOT/build/libexec"
mkdir -p "$destination" "$libexec_destination"

(
  cd "$ROOT/toolchain/linux-x86_64"
  sha256sum -c SHA256SUMS.txt >/dev/null
)

for tool in dxlc dxscc dxasm dxvm dxaudit dxs24cc dxvm24; do
  install -m 0755 "$source_dir/$tool" "$destination/$tool"
done
install -m 0755 "$ROOT/toolchain/linux-x86_64/libexec/dxlc-front" "$libexec_destination/dxlc-front"
install -m 0755 "$ROOT/toolchain/linux-x86_64/libexec/dxlc-native" "$libexec_destination/dxlc-native"
install -m 0644 "$ROOT/toolchain/linux-x86_64/libexec/dxlc-native-diagnostics.tsv" "$libexec_destination/dxlc-native-diagnostics.tsv"

printf 'Aegis toolchain ready: %s\n' "$destination"
