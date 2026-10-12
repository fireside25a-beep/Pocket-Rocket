#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 tools/generate_semantic_vectors.py
python3 tools/release_gate.py
printf '\nFINAL_VERIFY: PASS\n'
