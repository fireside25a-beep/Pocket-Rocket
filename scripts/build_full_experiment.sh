#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

python scripts/download_deepseek_v4.py
python scripts/install_ds4.py
python scripts/pocket_rocket_estimate.py
python scripts/run_16gb_gate.py
printf 'Pocket Rocket full build and measured 16-GiB gate PASS.\n'
