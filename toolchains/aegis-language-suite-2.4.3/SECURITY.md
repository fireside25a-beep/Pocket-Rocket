# Security policy

## Supported release

Security updates apply to Aegis Language Suite 2.4.3 on the tested Linux x86-64 host profile.

## Reporting

Report vulnerabilities privately through GitHub private vulnerability reporting for the repository. Do not publish exploit details, malicious bytecode, or a working bypass in a public issue before a coordinated fix is available.

Include the affected tool, exact version, minimal reproducer, expected rejection, observed behavior, and whether the issue crosses a capability or resource boundary.

## Scope

High-priority areas include:

- malformed DXB3 accepted by the verifier;
- verifier/VM disagreement;
- capability-mask bypass;
- stack, heap, step, or nesting-bound bypass;
- stale-handle, double-release, or bounds-check bypass;
- nondeterministic proof or bytecode generation;
- native miscompilation or distinct source programs producing the wrong/equal executable behavior;
- checked arithmetic, narrowing, assertion, loop-fuel, lexical-scope, or reserved-exit-status bypass;
- malformed native executable headers, dynamic dependency introduction, or executable-stack policy deviation;
- failed native compilation deleting or overwriting a pre-existing output;
- checksum or release-package integrity failure.

The implemented safety claims are limited to the profile in [docs/SAFETY_MODEL.md](docs/SAFETY_MODEL.md) and the support boundary in [docs/SUPPORT.md](docs/SUPPORT.md).
