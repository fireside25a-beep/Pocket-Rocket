# Determinism contract

For identical admitted input bytes and the same Aegis-C2R version/profile, Rust, canonical AST, JSON proof and DXL/DXS/DXASM certificates must be byte-identical. The release gate performs repeated translation and exact byte comparison.

Canonical AST identity deliberately ignores comments and formatting, while the JSON retains the original source SHA-256 separately. Therefore semantically identical source can have the same AST/Rust identities while preserving distinct source provenance.

The deterministic mutation gate executes 256 byte substitutions twice. The 0.1.0 fixed corpus yields 11 accepted whitespace mutations and 245 deterministic rejections. This is an adversarial reproducibility test, not a fuzzing-completeness claim.
