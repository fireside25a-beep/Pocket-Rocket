# Capability-aware standard library

The verified execution profile has no ambient filesystem, process, network, native-call, or dynamic-loading operation. Observable effects must be declared in the DXB3 header and permitted by the policy supplied to the VM.

The current capability mask covers integer output and bounded byte output. Verification derives the required mask from the instruction stream; execution fails before the program starts when policy does not grant every required capability.

The DXL library modules are deterministic and caller-owned:

- `stdlib/deterministic_collections.dxl` implements a fixed-capacity ordered map over parallel slices;
- `stdlib/serialization.dxl` implements checked little-endian non-negative integer primitives;
- `stdlib/validation.dxl` provides bounded validation helpers.

Collections use stable ordering and no randomized hash seed. Serialization has one canonical byte order. The modules do not acquire host capabilities themselves.

Filesystem, time, process, and network interfaces are outside the implemented 2.4.3 standard-library surface.
