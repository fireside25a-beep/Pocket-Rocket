import hashlib
import tempfile
import unittest
from pathlib import Path

from neuro_inverse.flat_dictionary import (
    BLOCK_SIZE,
    HEADER,
    Dictionary32,
    FlatDictionaryError,
    decode,
    encode,
    encode_file,
    metrics,
    read_dictionary,
    serialize_dictionary,
    train_dictionary,
    train_dictionary_bounded,
    write_dictionary,
)


class FlatDictionaryTests(unittest.TestCase):
    def test_exact_roundtrip_tail_and_wrong_dictionary(self):
        dictionary = Dictionary32((b"A" * 32, b"B" * 32))
        source = b"A" * 32 + hashlib.sha256(b"raw").digest() + b"B" * 32 + b"tail"
        encoded = encode(source, dictionary)
        self.assertEqual(source, decode(encoded, dictionary))
        wrong = Dictionary32((b"A" * 32, b"C" * 32))
        with self.assertRaises(FlatDictionaryError):
            decode(encoded, wrong)

    def test_corruption_tail_framing_and_bounds_fail_closed(self):
        dictionary = Dictionary32((b"A" * 32,))
        encoded = encode(b"A" * 32 + b"tail", dictionary)
        corrupted = bytearray(encoded)
        corrupted[-1] ^= 1
        with self.assertRaises(FlatDictionaryError):
            decode(corrupted, dictionary)
        fields = list(HEADER.unpack(encoded[:HEADER.size]))
        fields[8] += 1  # body_bytes no longer matches exact framing
        malformed = HEADER.pack(*fields) + encoded[HEADER.size:]
        with self.assertRaises(FlatDictionaryError):
            decode(malformed, dictionary)
        with self.assertRaises(FlatDictionaryError):
            decode(encoded[:-1], dictionary)
        with self.assertRaises(FlatDictionaryError):
            decode(encoded, dictionary, max_source_bytes=1)

    def test_trainer_is_deterministic_and_tie_ordered(self):
        first = b"A" * 32 + b"B" * 32 + b"A" * 32
        second = b"B" * 32 + b"A" * 32
        one = train_dictionary([first, second], max_entries=2)
        two = train_dictionary([first, second], max_entries=2)
        self.assertEqual(one, two)
        self.assertEqual((b"A" * 32, b"B" * 32), one.entries)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "train.bin"
            path.write_bytes(first)
            self.assertEqual(one, train_dictionary([path, second], max_entries=2))

    def test_reported_hybrid_ratio_and_dictionary_cost(self):
        dictionary = Dictionary32(tuple(bytes([value]) * BLOCK_SIZE for value in range(256)))
        registered = 81_873
        raw_count = 100_000 - registered
        blocks = [dictionary.entries[index % 256] for index in range(registered)]
        blocks.extend(hashlib.sha256(b"raw-block" + index.to_bytes(4, "little")).digest() for index in range(raw_count))
        source = b"".join(blocks)
        encoded = encode(source, dictionary)
        result = metrics(encoded, dictionary)
        self.assertAlmostEqual(result.coverage, 0.81873, places=5)
        self.assertAlmostEqual(result.hybrid_ratio, 4.744675, delta=0.001)
        self.assertEqual(result.registered_blocks, registered)
        self.assertEqual(result.raw_fallback_blocks, raw_count)
        self.assertEqual(result.dictionary_bytes, 256 * 32)
        self.assertLess(result.dictionary_inclusive_ratio, result.hybrid_ratio)
        self.assertEqual(source, decode(encoded, dictionary))

    def test_dictionary_limits_and_immutable_identity(self):
        with self.assertRaises(ValueError):
            Dictionary32(tuple(bytes([value % 256]) * 32 for value in range(257)))
        dictionary = Dictionary32((b"A" * 32,))
        with self.assertRaises((AttributeError, TypeError)):
            dictionary.entries += (b"B" * 32,)
        self.assertEqual(64, len(dictionary.sha256))

    def test_standalone_dictionary_serialization_is_exact(self):
        dictionary = Dictionary32((b"A" * 32, b"B" * 32))
        encoded = serialize_dictionary(dictionary)
        self.assertEqual(dictionary, Dictionary32.deserialize(encoded))
        corrupted = bytearray(encoded)
        corrupted[-1] ^= 1
        with self.assertRaises(FlatDictionaryError):
            Dictionary32.deserialize(corrupted)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "shared.dict"
            write_dictionary(dictionary, path)
            self.assertEqual(dictionary, read_dictionary(path))
            self.assertEqual(encoded, path.read_bytes())

    def test_streaming_file_encoder_matches_memory_format(self):
        dictionary = Dictionary32((b"A" * 32, b"B" * 32))
        source = b"A" * 32 + hashlib.sha256(b"raw-file").digest() + b"B" * 32 + b"tail"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path = root / "source.bin"
            output_path = root / "source.f32"
            source_path.write_bytes(source)
            result = encode_file(source_path, output_path, dictionary)
            self.assertEqual(encode(source, dictionary), output_path.read_bytes())
            self.assertEqual(source, decode(output_path.read_bytes(), dictionary))
            self.assertEqual(len(source), result.source_bytes)
            with self.assertRaises(FlatDictionaryError):
                encode_file(source_path, source_path, dictionary)

    def test_bounded_trainer_uses_only_configured_prefix(self):
        stream = b"B" * 32 + b"A" * 32 + b"C" * 32 + b"C" * 32
        dictionary = train_dictionary_bounded([stream], max_entries=2, max_sample_blocks=2)
        self.assertEqual((b"A" * 32, b"B" * 32), dictionary.entries)
        self.assertEqual(dictionary, train_dictionary_bounded(
            [stream], max_entries=2, max_sample_blocks=2
        ))
        with self.assertRaises(ValueError):
            train_dictionary_bounded([stream], max_sample_blocks=0)


if __name__ == "__main__":
    unittest.main()
