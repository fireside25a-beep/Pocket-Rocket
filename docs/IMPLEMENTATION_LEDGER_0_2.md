# Pocket Rocket 0.2 implementation ledger

| Workstream | State | Executable evidence |
| --- | --- | --- |
| Direct ternary semantic types | Complete | Sign-plane trits, exact popcount dot, exact triadic/rational arithmetic, Python/C tests |
| Gate and Choice | Complete | Real reject/abstain/accept, exact tie/margin rules, deterministic certificates |
| Ordered Score | Complete | Exact normalized distribution, expected ordinal score, confidence gate, CLI and adversarial tests |
| Local routing decision | Complete | `route-decide` binds exact Hamming routes to request/model evidence |
| Authenticated model identity | Complete | Canonical page manifest, complete source digest, domain-separated Merkle root |
| Static and demand pages | Complete | Same manifest/root, bounded range reads, per-page SHA-256 before return |
| Adaptive v2 page encoding | Complete | Raw/DEFLATE/shuffle2/shuffle4/shuffle8 exact competition and stable tie break |
| Legacy page compatibility | Complete | v1 raw and DEFLATE decode regression |
| Compression evidence | Complete for any supplied local source | `model-analyze` reauthenticates all pages and emits exact ratio, codec counts, decision root |
| Cache/input hardening | Complete | Bounded pre-read, regular/no-follow opens, shard containment, output alias tests |
| Deterministic source archive | Complete after release gate | Fixed metadata, source allow-list, no symlinks/model files/binaries, internal SHA-256 manifest |
| Full pinned-GGUF measurement | Requires local model | Run `model-manifest` then `model-analyze`; one complete authenticated read is mandatory |
| Fully ternary DeepSeek tensor graph | Not claimed | Upstream GGUF formats and ds4 kernels are not translated or relabelled |
| Target 16 GiB generation gate | Requires model and target hardware | Existing context ladder records real tokens and process-tree RSS |

Every public 0.2 command is connected to an implementation and test. There is
no placeholder compressor, hosted AI dependency, alternate chat backend, or
mock model path.
