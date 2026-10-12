# Pocket Rocket 0.4.2 — qualification record

Validation date: 2026-10-12. Environment: this task's Linux x86-64 container.
A PASS is reported only for commands actually executed in this session.

| Gate | Observed result | Scope |
|---|---|---|
| Python unittest discovery | **169 PASS** | Project tests including six live Aegis VM/compiler tests and three live C2R tests |
| GTK source-contract tests | **6 PASS** | Static GTK code checks; not a GTK binary build |
| Runtime production-surface audit | **PASS** | Current Python/native exported surfaces |
| Pocket Rocket native | **PASS** | GCC **and Clang**, C11 normal, ASan, UBSan paths |
| Aegis 2.4.3 `make check` | **PASS** | 105 regression checks, 40 matrix checks, source/hygiene/release verification |
| Aegis-C2R 0.1.0 `make check` | **37/37 PASS** | GCC, Clang, analyzer, sanitizers, negative/mutation/certificate corpus, private 2.4.0 bootstrap |
| C2R optional `rustc` execution | **SKIP** | rustc unavailable on validation host |
| Aegis 2.4.3 `make maintainer-check` | **FAIL (environment-pinned byte-identity gate)** | Locally source-rebuilt DXL compiler differs bytewise from shipped seed; standard `make check` passes |
| Complete 86.72 GB model and RAM qualification | **NOT RUN** | Model weights and target hardware unavailable |
| Full qualification after fresh GNU unzip | **PASS** | Re-extracted release archive, reran real compiler and runtime tests |
| GTK4 binary | **NOT RUN** | GTK4 development dependencies absent |

The maintainer-check failure must remain visible. It does not imply the
shipped executable fails its real-language tests, but the stronger
source-to-shipped byte-reproducibility claim is not proven here. See the
standalone Aegis `docs/SELF_HOSTING.md` and reproducibility instructions.

**Separations:** Aegis 2.4.3 is the active language suite. Aegis-C2R 0.1.0
retains Aegis 2.4.0 only in its isolated historical bootstrap fixture;
this is not an active toolchain replacement. Verified DXB3 receipts do not
certify model correctness, hardware performance, or arbitrary DXL semantics.

Raw logs and machine-readable status: [`evidence/2026-10-12/`](../evidence/2026-10-12/).
