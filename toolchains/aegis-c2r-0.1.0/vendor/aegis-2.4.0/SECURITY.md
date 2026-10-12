# Security

Please report security-sensitive issues privately to the repository maintainer rather than opening a public issue with exploit details.

The verified DXB3 profile is designed to fail closed on malformed containers, invalid opcodes, stack/resource violations, bounds violations, stale handles, arithmetic faults, undeclared capabilities and invalid termination. These properties apply to the implemented VM profile and are not a claim of formal verification or universal memory safety for every future DXL feature.
