# Security boundary

Aegis-C2R is a bounded research translator, not a sandbox for hostile C repositories. It performs no network access and has no plugin or dynamic-code execution path. Source size, parser nesting, AST storage, function/parameter/local counts and generated Aegis execution are bounded. Unsupported syntax fails closed.

Generated Rust is emitted with `#![forbid(unsafe_code)]` for the supported S0 profile. Signed arithmetic uses checked Rust operations. This prevents the emitter from silently relying on wrapping behavior where the admitted C operation would be undefined.

Report issues with a minimal reproducer, the input SHA-256, exact tool version, host/compiler versions and the failing release-gate line.
