#!/usr/bin/env python3
"""Restore known executable modes after unzip tools that discard POSIX modes.

Does not rewrite code or hashes. Refuses symlink files and directories.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    roots = [ROOT / "toolchains/aegis-language-suite-2.4.3",
             ROOT / "toolchains/aegis-c2r-0.1.0"]
    count = 0
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            raise ValueError(f"missing or linked toolchain directory: {root}")
        for p in root.rglob("*"):
            if p.is_symlink():
                raise ValueError(f"toolchain symlink rejected: {p}")
            if not p.is_file():
                continue
            rel = p.relative_to(root)
            executable = p.suffix == ".sh" or (
                root.name == "aegis-language-suite-2.4.3" and
                (str(rel).startswith("toolchain/linux-x86_64/bin/") or
                 rel.as_posix() in {
                     "toolchain/linux-x86_64/libexec/dxlc-front",
                     "toolchain/linux-x86_64/libexec/dxlc-native",
                 })
            )
            if executable and not p.stat().st_mode & stat.S_IXUSR:
                os.chmod(p, p.stat().st_mode | 0o111)
                count += 1
    print(f"Toolchain modes verified ({count} restored)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
