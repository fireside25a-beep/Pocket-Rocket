# Proofs and reproducibility

Aegis commits evidence artifacts that show what one exact source, toolchain, target/profile, policy, and execution produced. These are reproducibility records. Only the VM-generated DXB3 records use the `.proof` name; no artifact here is a general mathematical proof of arbitrary source behavior.

## Loop evidence set

The release compares four paths:

- [general DXL compile-time counter](../examples/loops/dxl/counter.dxl);
- [native DXL runtime counter](../examples/loops/dxl/native_counter.dxl);
- [DXS counter](../examples/loops/dxs/counter.dxs);
- [DXASM counter](../examples/loops/dxasm/counter.dxasm).

All runtime paths print exactly:

```text
10
```

Regenerate the evidence with:

```sh
make matrix
```

## Published artifacts

| Artifact | Meaning |
| --- | --- |
| `dxl-counter.check` | General DXL check transcript; compile-time assertion passed |
| `dxl-counter.tir` | Deterministic general DXL typed-IR text |
| `dxl-native-counter.bin` | Static native DXL executable |
| `dxl-native-counter.audit` | Checked executable format, loader/dependency, stack, and hash summary |
| `dxl-native-counter.out` | Exact native process output |
| `dxs-counter.dxb` | DXS-compiled DXB3 container |
| `dxasm-counter.dxb` | DXASM-assembled DXB3 container |
| `dxs-counter.audit`, `dxasm-counter.audit` | DXB3 auditor summaries |
| `dxs-counter.out`, `dxasm-counter.out` | Exact VM output |
| `dxs-counter.proof`, `dxasm-counter.proof` | Deterministic DXB3 VM proof records |
| `MATRIX_RESULTS.tsv` | Machine-readable path/result/evidence index |
| `SHA256SUMS.txt` | Source, fixture, and evidence integrity manifest |

## What the matrix establishes

- the general DXL compile-time loop reaches `10`, or its assertion rejects;
- repeated general DXL checks and typed-IR emissions are identical;
- repeated native DXL compilation is byte-identical;
- the native artifact is x86-64 ELF64 `ET_EXEC`, has one load segment, no interpreter or dynamic dependencies, and an explicit non-executable stack;
- repeated native executions have identical output equal to `10`;
- repeated DXS compilation and DXASM assembly are byte-identical;
- both DXB3 artifacts pass audit;
- repeated VM output and proof records are byte-identical;
- native DXL, DXS, and DXASM runtime output is identical;
- the normalized DXS and DXASM payloads and proof records match for this fixture.

The native executable is runtime and reproducibility evidence, not a DXB3 proof. It does not pass through the DXB3 verifier or capability policy.

## Verification

```sh
(cd proofs/loops && sha256sum -c SHA256SUMS.txt)
```

The repository has a separate root manifest. The release ZIP has another checksum published alongside it. Changing a committed source or evidence file invalidates the corresponding manifest.

## Scope

Evidence applies only to the exact source bytes, executable bytes, target/profile, policy, and supported host represented by this release. It does not establish equivalence for a different compiler, unsupported host, different policy, or arbitrary program.
