#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
rm -rf build/positive-oracle
mkdir -p build/positive-oracle
count=0
for f in tests/positive/*.c; do
  n="$(basename "$f" .c)"
  gcc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -Wno-strict-prototypes "$f" -o "build/positive-oracle/$n.gcc"
  clang -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -Wno-strict-prototypes "$f" -o "build/positive-oracle/$n.clang"
  set +e
  "build/positive-oracle/$n.gcc" > "build/positive-oracle/$n.gcc.out"; grc=$?
  "build/positive-oracle/$n.clang" > "build/positive-oracle/$n.clang.out"; crc=$?
  set -e
  [[ "$grc" -eq "$crc" ]]
  cmp "build/positive-oracle/$n.gcc.out" "build/positive-oracle/$n.clang.out"
  count=$((count+1))
done
printf 'POSITIVE_C_ORACLE_PASS files=%d gcc_clang_runtime_consensus=yes\n' "$count"
