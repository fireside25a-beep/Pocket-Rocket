# Experiment gates

## Local deterministic gates

Run the Python suite, synthetic identity proof, native C tests with sanitizers,
router benchmark, and archive audit. These validate code behavior without
pretending to measure the full model.

## Ternary and signed-quaternary gate

For every encoded stage:

1. Validate exact length and authenticated SHA-256 before decode.
2. Reject reserved ternary symbol `3`, malformed scale data, truncation, and
   trailing bytes.
3. Decode with the stored float16 scale—not an unrecorded higher-precision
   value.
4. Require `SSE(W, W_hat_m) <= SSE(W, W_hat_(m-1))` before committing a stage.
5. Decode again and require byte-identical reconstructed binary32 output.

The v2 signed-quaternary alphabet is `{-3,-1,+1,+3}` and uses all two-bit
symbols. The legacy ternary alphabet is `{-1,0,+1}` and reserves symbol `3` as
an error. The formats are never guessed from payload bytes.

## Full-model gate

The pinned GGUF must pass filename, byte-size, header, and complete SHA-256
validation. The pinned native engine must pass its upstream tests and CLI
contract. Then `scripts/run_16gb_gate.py` must generate real tokens while the
entire process tree stays within 14.5 GiB RSS.

Record exact runtime/model revisions, command hash, output hash, peak RSS,
elapsed time, and exit status. Only a real PASS supports a 16 GiB claim.

## Performance experiments

After correctness passes, measure tokens/second, time-to-first-token, peak RSS,
GPU memory if used, SSD bytes read, cache hit ratio, and output quality on a
fixed prompt set. Change one variable at a time: expert cache, context, output
length, or candidate math backend. Never infer a model compression ratio from
the included structured synthetic fixtures.
