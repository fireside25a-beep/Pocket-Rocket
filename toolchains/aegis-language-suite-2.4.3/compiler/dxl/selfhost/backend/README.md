# Backend object-writer foundation

This directory contains a DXL-authored writer for one fixed
ELF64 x86-64 relocatable fixture. It exercises checked byte emission, section
layout, symbols, relocations, and a minimal DWARF v4 line table.

The fixture is an implementation foundation and test oracle. It is not a
general native backend, linker, optimizer, or cross-target implementation.

## Diagnostic codes

| Code | Meaning |
|---|---|
| `AEG2501` | The caller-provided object buffer is smaller than the fixed writer capacity. |
| `AEG2502` | The completed object could not be written to the requested output path. |
| `AEG2503` | The fixture driver did not receive exactly one output path. |
