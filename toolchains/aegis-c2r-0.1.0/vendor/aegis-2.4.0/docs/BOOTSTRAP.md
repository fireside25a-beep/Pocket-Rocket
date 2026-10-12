# Bootstrap model

A fresh checkout has a chicken-and-egg problem: the DXS compiler, DXASM assembler and DXB3 VM are written in DXL, so a DXL compiler must exist before those DXL sources can become executables.

`bootstrap/dxlc_stage0.c` exists only to break that cycle. The normal build is:

1. build the small stage-zero `dxlc`;
2. use `dxlc` to compile DXL-authored DXS, DXASM and VM sources;
3. use those generated tools for DXS/DXASM compilation and execution tests.

The suite does not claim a completely self-hosted DXL frontend yet. Full self-hosting would require the complete lexer, parser, semantic checker, compile-time evaluator, IR/backend and project driver to be implemented in DXL and validated through reproducible stage comparison.
