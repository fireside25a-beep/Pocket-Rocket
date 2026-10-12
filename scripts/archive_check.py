#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

FORBIDDEN_SUFFIXES = {".safetensors", ".gguf", ".pt", ".pth", ".onnx"}
SECRET = re.compile(rb"(?:hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    failures: list[str] = []
    for path in args.root.resolve().rglob("*"):
        if path.is_symlink():
            failures.append(f"symbolic link: {path}")
            continue
        if not path.is_file() or any(part in {".git", ".venv", "models", "runtime", "var"} for part in path.parts):
            continue
        if path.suffix.casefold() in FORBIDDEN_SUFFIXES:
            failures.append(f"model artifact: {path}")
        if path.stat().st_size <= 4 * 1024 * 1024 and SECRET.search(path.read_bytes()):
            failures.append(f"credential-like text: {path}")
    if failures:
        print("ARCHIVE CHECK FAILED")
        print("\n".join(failures))
        return 1
    print("ARCHIVE CHECK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
