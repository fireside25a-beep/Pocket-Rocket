# Architecture

```text
C source
  -> deterministic preprocessor gate
  -> lexer
  -> recursive-descent parser + S0 semantic checks
  -> arena AST
       |-> canonical AST
       |-> safe Rust
       |-> proof JSON (source/AST/Rust SHA-256)
       `-> structural certificate
             |-> DXL
             |-> DXS -> DXB3 verifier/VM
             `-> DXASM -> DXB3 verifier/VM
```

The C front end is independent of the Aegis VM path. Aegis is used as a cross-language certificate witness, not as a substitute for semantic differential testing. The certificate packs bounded AST metrics into one deterministic i32; DXL, DXS and DXASM must independently reproduce the same number.
