import hashlib
import os
import random
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from neuro_inverse.pocket_pack import (
    CODEC_RAW,
    CODEC_ZLIB,
    ENTRY_STRUCT,
    HEADER_STRUCT,
    PocketRocketError,
    PocketRocketReader,
    pack,
)


class PocketRocketTests(unittest.TestCase):
    def test_roundtrip_random_chunk_access_and_range(self):
        source = (b"deterministic NPRQ stage bytes " * 97) + bytes(range(251))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stage.pkr"
            info = pack(source, path, chunk_size=127)
            self.assertEqual(len(source), info.source_bytes)
            with PocketRocketReader(path) as reader:
                self.assertEqual(info.source_sha256, hashlib.sha256(source).hexdigest())
                reader.verify()
                order = list(range(reader.info.chunk_count))
                random.Random(19).shuffle(order)
                for index in order:
                    start = index * reader.info.chunk_size
                    self.assertEqual(source[start:start + reader.info.chunk_size], reader.read_chunk(index))
                self.assertEqual(source[41:601], reader.read_range(41, 560))
                self.assertEqual(b"", reader.read_range(0, 0))

    def test_deterministic_bytes_and_codec_choice(self):
        compressible = b"A" * 10000
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first.pkr"
            second = Path(temp) / "second.pkr"
            pack(compressible, first, chunk_size=257)
            pack(compressible, second, chunk_size=257)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with PocketRocketReader(first) as reader:
                self.assertTrue(all(chunk.codec == CODEC_ZLIB for chunk in reader.chunks))

            random_source = b"".join(random.Random(index).randbytes(4096) for index in range(2))
            random_path = Path(temp) / "random.pkr"
            pack(random_source, random_path, chunk_size=4096)
            with PocketRocketReader(random_path) as reader:
                self.assertTrue(all(chunk.codec == CODEC_RAW for chunk in reader.chunks))

    def test_corruption_and_truncation_are_rejected(self):
        source = b"z" * 4096
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stage.pkr"
            pack(source, path, chunk_size=256)
            data = bytearray(path.read_bytes())
            with PocketRocketReader(path) as reader:
                data[reader.chunks[0].offset] ^= 1
            path.write_bytes(data)
            with PocketRocketReader(path) as reader:
                with self.assertRaises(PocketRocketError):
                    reader.read_chunk(0)
            path.write_bytes(data[:-1])
            with self.assertRaises(PocketRocketError):
                PocketRocketReader(path)

    def test_decompression_expansion_is_bounded(self):
        raw = b"A" * 64
        bomb = zlib.compress(b"B" * 4096)
        self.assertLess(len(bomb), len(raw))
        source_digest = hashlib.sha256(raw).digest()
        header = HEADER_STRUCT.pack(b"NRPQR001", 1, 0, 64, 64, 1, source_digest)
        entry = ENTRY_STRUCT.pack(
            HEADER_STRUCT.size + ENTRY_STRUCT.size, len(bomb), len(raw), zlib.crc32(raw) & 0xFFFFFFFF,
            CODEC_ZLIB, hashlib.sha256(raw).digest(),
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bomb.pkr"
            path.write_bytes(header + entry + bomb)
            with PocketRocketReader(path) as reader:
                with self.assertRaises(PocketRocketError):
                    reader.read_chunk(0)

    def test_strict_index_bounds_and_reader_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty.pkr"
            pack(b"", path, chunk_size=16)
            with PocketRocketReader(path) as reader:
                reader.verify()
                self.assertEqual(0, reader.info.chunk_count)
                with self.assertRaises(IndexError):
                    reader.read_chunk(0)
            data_path = Path(temp) / "data.pkr"
            pack(b"x" * 100, data_path, chunk_size=16)
            with self.assertRaises(PocketRocketError):
                PocketRocketReader(data_path, max_source_bytes=0)
            with self.assertRaises(PocketRocketError):
                PocketRocketReader(data_path, max_chunk_bytes=8)
            with PocketRocketReader(data_path, max_range_bytes=10) as reader:
                with self.assertRaises(PocketRocketError):
                    reader.read_range(0, 11)

    def test_trailing_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trailing.pkr"
            pack(b"payload", path, chunk_size=16)
            path.write_bytes(path.read_bytes() + b"junk")
            with self.assertRaises(PocketRocketError):
                PocketRocketReader(path)

    def test_output_alias_is_rejected_without_source_damage(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.bin"
            source.write_bytes(b"preserve me")
            with self.assertRaisesRegex(PocketRocketError, "aliases"):
                pack(source, source, chunk_size=16)
            self.assertEqual(b"preserve me", source.read_bytes())


if __name__ == "__main__":
    unittest.main()
