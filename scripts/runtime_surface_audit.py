#!/usr/bin/env python3
"""Fail a release with unresolved imports, simulated production dependencies, or orphan APIs."""
from __future__ import annotations

import ast
import importlib
import pkgutil
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "src" / "neuro_inverse"
NATIVE = PROJECT / "native"
FORBIDDEN_IMPORT_PARTS = {"mock", "magicmock", "stub", "fake"}


def _public_definitions(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return tuple(
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_") and node.name != "main"
    )


def _python_audit(failures: list[str]) -> None:
    corpus_paths = [
        *SOURCE.glob("*.py"), *PROJECT.glob("tests/*.py"), *PROJECT.glob("scripts/*.py"),
        *PROJECT.glob("benchmarks/*.py"), *PROJECT.glob("experiments/*.py"),
    ]
    text_by_path = {path: path.read_text(encoding="utf-8") for path in corpus_paths}
    for path in sorted(SOURCE.glob("*.py")):
        tree = ast.parse(text_by_path[path], filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                if any(part.casefold() in FORBIDDEN_IMPORT_PARTS
                       for module in modules for part in module.split(".")):
                    failures.append(f"{path.name}:{node.lineno}: simulated dependency")
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                if isinstance(node.exc.func, ast.Name) and node.exc.func.id == "NotImplementedError":
                    failures.append(f"{path.name}:{node.lineno}: incomplete production path")
        all_text = "\n".join(text_by_path.values())
        for name in _public_definitions(path):
            # One occurrence is the definition itself; a second means an internal call,
            # export, CLI path, test, script, or benchmark is connected to it.
            if len(re.findall(rf"\b{re.escape(name)}\b", all_text)) < 2:
                failures.append(f"{path.name}: public function {name!r} has no consumer/export/test")

    sys.path.insert(0, str(PROJECT / "src"))
    try:
        package = importlib.import_module("neuro_inverse")
        for module in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
            if module.name.endswith(".__main__"):
                continue
            try:
                importlib.import_module(module.name)
            except Exception as exc:  # importability is a release invariant
                failures.append(f"{module.name}: import failed: {type(exc).__name__}: {exc}")
    finally:
        sys.path.pop(0)


def _native_audit(failures: list[str]) -> None:
    header_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in NATIVE.glob("*.h"))
    production_c = {path: path.read_text(encoding="utf-8", errors="replace")
                    for path in NATIVE.glob("*.c") if not path.name.startswith("test_") and not path.name.startswith("bench_")}
    consumer_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in NATIVE.glob("*.c")
    )
    names = sorted(set(re.findall(r"\b(nr_[A-Za-z0-9_]+)\s*\(", header_text)))
    for name in names:
        definition = re.compile(rf"\b{re.escape(name)}\s*\([^;]*\)\s*\{{", re.S)
        if not any(definition.search(text) for text in production_c.values()):
            failures.append(f"native: declared API {name!r} has no production definition")
        if len(re.findall(rf"\b{re.escape(name)}\s*\(", consumer_text)) < 2:
            failures.append(f"native: API {name!r} has no production/test/benchmark call site")


def main() -> int:
    failures: list[str] = []
    _python_audit(failures)
    _native_audit(failures)
    if failures:
        print("RUNTIME SURFACE AUDIT FAILED")
        print("\n".join(failures))
        return 1
    print("RUNTIME SURFACE AUDIT PASS: imports resolve; no simulated production dependencies; public Python and nr_* C surfaces are connected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
