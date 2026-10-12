import tempfile
import unittest
from pathlib import Path

import numpy as np

from neuro_inverse.nprq import (
    NPRQMeta, decode_tensor, encode_tensor, pack_ternary, unpack_ternary, verify_tensor,
)
from neuro_inverse.pocket_pack import pack


class NPRQTests(unittest.TestCase):
    def test_pack_round_trip(self):
        source = np.array([-1, 0, 1, 1, 0, -1, 1], dtype=np.int8)
        self.assertTrue(np.array_equal(source, unpack_ternary(pack_ternary(source), source.size)))

    def test_ternary_payload_rejects_length_codes_and_noncanonical_padding(self):
        source = np.array([-1, 0, 1], dtype=np.int8)
        packed = pack_ternary(source)
        self.assertEqual(source.tolist(), unpack_ternary(packed, source.size).tolist())
        with self.assertRaises(ValueError):
            unpack_ternary(packed + b"\x01", source.size)
        with self.assertRaises(ValueError):
            unpack_ternary(bytes([0x03]), 1)
        # For three values the high two bits are padding and must encode zero.
        with self.assertRaises(ValueError):
            unpack_ternary(bytes([0x02 | (0x02 << 2) | (0x02 << 4) | (0x02 << 6)]), 3)
        with self.assertRaises(TypeError):
            unpack_ternary(packed, True)  # type: ignore[arg-type]

    def test_progressive_error_is_monotonic(self):
        rng = np.random.default_rng(7)
        source = rng.normal(size=(31, 19)).astype(np.float32)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            meta = encode_tensor(source, root, "tensor", stages=4, block_size=64)
            verify_tensor(root, meta)
            errors = []
            for stages in range(1, 5):
                restored = decode_tensor(root, meta, stage_count=stages)
                errors.append(float(np.mean((source - restored) ** 2)))
            self.assertTrue(all(right <= left + 1e-7 for left, right in zip(errors, errors[1:])), errors)
            self.assertLess(errors[-1], errors[0])
            self.assertTrue(all(right <= left for left, right in zip(meta.rmse, meta.rmse[1:])), meta.rmse)

            malformed = NPRQMeta(
                meta.format, meta.shape, meta.source_dtype, meta.block_size, meta.stages,
                meta.numel, meta.stage_files, meta.stage_sha256,
                (meta.rmse[0], meta.rmse[0] + 1.0, *meta.rmse[2:]),
            )
            with self.assertRaisesRegex(ValueError, "not monotonic"):
                verify_tensor(root, malformed)

    def test_hash_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            meta = encode_tensor(np.ones(32, dtype=np.float32), root, "x", stages=1, block_size=16)
            (root / meta.stage_files[0]).write_bytes(b"broken")
            with self.assertRaises(ValueError):
                verify_tensor(root, meta)

    def test_metadata_length_and_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            meta = encode_tensor(np.ones(32, dtype=np.float32), root, "x", stages=2, block_size=16)
            malformed = NPRQMeta(
                meta.format, meta.shape, meta.source_dtype, meta.block_size, meta.stages,
                meta.numel, meta.stage_files[:1], meta.stage_sha256, meta.rmse,
            )
            with self.assertRaises(ValueError):
                verify_tensor(root, malformed)
            traversal = NPRQMeta(
                meta.format, meta.shape, meta.source_dtype, meta.block_size, meta.stages,
                meta.numel, ("../escape.nprq", *meta.stage_files[1:]), meta.stage_sha256, meta.rmse,
            )
            with self.assertRaises(ValueError):
                decode_tensor(root, traversal)

    def test_nonfinite_source_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                encode_tensor(np.array([np.nan, 1.0], dtype=np.float32), Path(temp), "nan", stages=1, block_size=16)

    def test_chunked_encoding_handles_empty_and_large_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            empty = encode_tensor(np.empty((0, 4), dtype=np.float32), root, "empty", stages=2, block_size=16)
            self.assertEqual((0, 4), empty.shape)
            source = np.arange(16 * 4097, dtype=np.float32)
            meta = encode_tensor(source, root, "chunked", stages=2, block_size=16)
            verify_tensor(root, meta)
            self.assertEqual(source.shape, decode_tensor(root, meta).shape)

    def test_pocket_pack_stage_decodes_to_identical_tensor(self):
        rng = np.random.default_rng(23)
        source = rng.normal(size=(37, 19)).astype(np.float32)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            meta = encode_tensor(source, root, "packed", stages=3, block_size=64)
            packed_names = []
            for filename in meta.stage_files:
                packed_name = filename[:-len(".nprq")] + ".prk"
                pack(root / filename, root / packed_name, chunk_size=31)
                packed_names.append(packed_name)
            packed_meta = NPRQMeta(
                meta.format, meta.shape, meta.source_dtype, meta.block_size, meta.stages,
                meta.numel, tuple(packed_names), meta.stage_sha256, meta.rmse,
            )
            verify_tensor(root, packed_meta)
            for stage_count in range(1, meta.stages + 1):
                self.assertTrue(np.array_equal(
                    decode_tensor(root, meta, stage_count=stage_count),
                    decode_tensor(root, packed_meta, stage_count=stage_count),
                ))
            packed_path = root / packed_names[0]
            packed_path.write_bytes(packed_path.read_bytes()[:-1] + b"x")
            with self.assertRaises(ValueError):
                verify_tensor(root, packed_meta)


if __name__ == "__main__":
    unittest.main()
