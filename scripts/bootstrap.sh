#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[deepseek]'
python -m neuro_inverse init-store
python -m unittest discover -s tests -v
python -m neuro_inverse doctor

printf '\nBootstrap complete. Activate with: source .venv/bin/activate\n'
