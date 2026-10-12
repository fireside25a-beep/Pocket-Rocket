# DXB3 safety and execution model

The verified DXB3 profile uses an intentionally bounded execution surface. The verifier checks container structure, declared resource metrics, stack behavior, instruction validity and capability requirements before execution.

The implemented runtime includes checked signed arithmetic, bounded stack/heap resources, structured bounded control flow, generation-checked memory handles, bounds checking, stale-handle/double-free rejection, explicit capability checks and leak-free successful termination requirements.

There is no general native-call opcode, ambient filesystem/network/process authority or JIT code generation in the verified profile. This is a concrete runtime boundary, not a claim of formal proof for arbitrary native programs.
