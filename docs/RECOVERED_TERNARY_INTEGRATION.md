# Recovered ternary and OS evidence

This checkpoint records the exact prior artifacts used to design the unified
Pocket Rocket path, so an interruption cannot erase the integration basis.

## Dexr Aegis

- `Dexr_Language_Aegis_2.4.0_Ternary_Foundation_Complete_AIO.zip`
- Archive SHA-256:
  `f6bf317eed6530f98fd6d6c76339b5c5a695c3a3e53b2e736b07c2837d18be3d`
- 5,306/5,306 internal hashes passed; 92 named gates and 128/128 generated
  programs passed.
- Balanced ternary alphabet `{-1,0,+1}`; five trits/byte in the foundation
  format; checked 40-trit signed limit.
- DXT4/DXP4 uses T39, canonically packing 39 trits into eight octets.
- Exact T39 range:
  `-2,026,277,576,509,488,133 .. +2,026,277,576,509,488,133`.
- C/DXL compiler byte identity, VM/proof identity, native x86-64 result
  differentials, overflow/null/divide-by-zero rejection, and deterministic
  native object bytes passed in the recorded release.

## NeuroBSD-T3 RV64

- `NeuroBSD_T3_0.1.0_RV64_Ternary_Aegis_Research_AIO.zip`
- Kernel SHA-256:
  `96544835a6aaa9cdc69abf20594f883cab640445ffba478eeb3723f148a1bed1`
- Emulator SHA-256:
  `a8a6630c9ab61f2e558b6633cb45f742b61e714b3f304039a67465253fe799ec`
- Boot marker `NEUROBSD_T3_BOOT_OK` after 175,639 interpreted RV64
  instructions.
- T3V differential corpus 64/64 and Aegis generated corpus 32/32 passed.
- Invalid lane/trit, out-of-range, fuel exhaustion, malformed ELF, and DXB3
  tamper rejection passed; ASan/UBSan emulator boot passed.

## Integration decision

Pocket Rocket reuses T39's canonical checked scalar and differential vectors for
Lbit control decisions. It does not boot an OS or run a second VM for each
token. DwarfStar remains the only transformer engine. T39/DXT4, exact
binary32, and optional x87/assembly candidates converge at one conformance
boundary; only the fastest bit-equivalent candidate is selected.
