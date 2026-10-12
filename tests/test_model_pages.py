from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from neuro_inverse.model_pages import (
    CODEC_SHUFFLE4_ZLIB,
    CODEC_ZLIB,
    LEGACY_PAGE_MAGIC,
    MAX_MODEL_BYTES,
    PAGE_HEADER,
    PAGE_MAGIC,
    ModelManifest,
    ModelPageError,
    ModelPageStore,
    analyze_compression,
    byte_shuffle,
    byte_unshuffle,
    build_manifest,
    select_page_encoding,
)
from neuro_inverse.model_target import WEIGHT_SIZE_BYTES
from neuro_inverse.pocket_pack import DEFAULT_MAX_SOURCE_BYTES


class ModelPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "model.gguf"
        self.data = (b"GGUF" + b"ternary-page-pattern" * 12000 + bytes(range(251)))
        self.source.write_bytes(self.data)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_pinned_model_fits_all_outer_container_bounds(self) -> None:
        self.assertGreaterEqual(MAX_MODEL_BYTES, WEIGHT_SIZE_BYTES)
        self.assertGreaterEqual(DEFAULT_MAX_SOURCE_BYTES, WEIGHT_SIZE_BYTES)

    def test_static_and_demand_share_root_and_bytes(self) -> None:
        manifest = build_manifest(self.source, page_bytes=64 * 1024)
        path = self.root / "manifest.json"
        manifest.write(path)
        loaded = ModelManifest.read(path)
        self.assertEqual(manifest, loaded)

        static = ModelPageStore(self.root / "static", manifest, self.source)
        self.assertEqual(len(manifest.pages), static.materialize_all())
        self.assertEqual((len(manifest.pages), len(manifest.pages)), static.verify_cached())

        demand = ModelPageStore(self.root / "demand", manifest, self.source)
        offset = 60000
        length = 90000
        self.assertEqual(self.data[offset:offset + length], demand.read_range(offset, length))
        self.assertEqual(manifest.model_root, loaded.model_root)
        present, total = demand.verify_cached()
        self.assertGreater(present, 0)
        self.assertLessEqual(present, total)

    def test_changed_source_fails_before_cache_commit(self) -> None:
        manifest = build_manifest(self.source, page_bytes=64 * 1024)
        changed = bytearray(self.data)
        changed[100] ^= 1
        self.source.write_bytes(changed)
        store = ModelPageStore(self.root / "store", manifest, self.source)
        with self.assertRaisesRegex(ModelPageError, "does not match"):
            store.read_page(0)

    def test_corrupt_cached_page_fails_closed(self) -> None:
        manifest = build_manifest(self.source, page_bytes=64 * 1024)
        store = ModelPageStore(self.root / "store", manifest, self.source)
        object_path = store.materialize(0)
        encoded = bytearray(object_path.read_bytes())
        encoded[-1] ^= 1
        object_path.write_bytes(encoded)
        with self.assertRaises(ModelPageError):
            store.read_page(0)

    def test_range_and_manifest_bounds(self) -> None:
        manifest = build_manifest(self.source, page_bytes=64 * 1024)
        store = ModelPageStore(self.root / "store", manifest, self.source)
        with self.assertRaisesRegex(ModelPageError, "range"):
            store.read_range(len(self.data), 1)
        path = self.root / "manifest.json"
        manifest.write(path)
        payload = json.loads(path.read_text())
        payload["pages"][0]["raw_bytes"] += 1
        path.write_text(json.dumps(payload))
        with self.assertRaises(ModelPageError):
            ModelManifest.read(path)

    def test_compressed_page_expansion_is_bounded(self) -> None:
        manifest = build_manifest(self.source, page_bytes=64 * 1024)
        store = ModelPageStore(self.root / "store", manifest, self.source)
        object_path = store.materialize(0)
        page = manifest.pages[0]
        header = PAGE_HEADER.pack(PAGE_MAGIC, CODEC_ZLIB, page.raw_bytes, bytes.fromhex(page.sha256))
        object_path.write_bytes(header + zlib.compress(b"Z" * (256 * 1024)))
        with self.assertRaisesRegex(ModelPageError, "bound"):
            store.read_page(0)

    def test_shuffle_roundtrip_and_exact_smallest_candidate(self) -> None:
        for width in (2, 4, 8):
            for length in range(0, 33):
                raw = bytes((index * 29 + length) & 255 for index in range(length))
                self.assertEqual(raw, byte_unshuffle(byte_shuffle(raw, width), width))
        structured = b"".join(struct.pack("<I", index) for index in range(16384))
        selected = select_page_encoding(structured)
        self.assertEqual(CODEC_SHUFFLE4_ZLIB, selected.codec)
        sizes = dict(selected.candidates)
        self.assertEqual(min(sizes.values()), len(selected.payload))
        self.assertLess(len(selected.payload), sizes["deflate"])

    def test_analysis_is_deterministic_and_binds_codec_decisions(self) -> None:
        structured = b"".join(struct.pack("<I", index) for index in range(32768))
        self.source.write_bytes(structured)
        manifest = build_manifest(self.source, page_bytes=64 * 1024)
        first = analyze_compression(self.source, manifest)
        second = analyze_compression(self.source, manifest)
        self.assertEqual(first, second)
        self.assertEqual(2, first.pages)
        self.assertEqual(2, dict(first.codecs)["shuffle4-deflate"])
        self.assertLess(first.stored_bytes, first.source_bytes)
        self.assertEqual(64, len(first.decision_root))

    def test_legacy_v1_page_remains_readable(self) -> None:
        manifest = build_manifest(self.source, page_bytes=64 * 1024)
        store = ModelPageStore(self.root / "store", manifest, self.source)
        page = manifest.pages[0]
        destination = store._object_path(page)
        raw = self.data[:page.raw_bytes]
        destination.write_bytes(
            PAGE_HEADER.pack(
                LEGACY_PAGE_MAGIC, CODEC_ZLIB, page.raw_bytes, bytes.fromhex(page.sha256)
            )
            + zlib.compress(raw)
        )
        self.assertEqual(raw, store.read_page(0))

    def test_oversized_or_symlinked_cache_object_is_rejected_before_read(self) -> None:
        manifest = build_manifest(self.source, page_bytes=64 * 1024)
        store = ModelPageStore(self.root / "store", manifest, self.source)
        destination = store.materialize(0)
        destination.write_bytes(b"X" * (PAGE_HEADER.size + manifest.pages[0].raw_bytes + 1))
        with self.assertRaisesRegex(ModelPageError, "storage bound"):
            store.read_page(0)
        destination.unlink()
        destination.symlink_to(self.source)
        with self.assertRaisesRegex(ModelPageError, "regular file"):
            store.read_page(0)


if __name__ == "__main__":
    unittest.main()
