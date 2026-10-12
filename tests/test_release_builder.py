import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_release import ARCHIVE_ROOT, build


class SourceReleaseBuilderTests(unittest.TestCase):
    def test_output_is_reproducible_source_only_and_self_verifying(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            (project / "scripts").mkdir(parents=True)
            (project / "models").mkdir()
            (project / "README.md").write_text("release\n", encoding="utf-8")
            (project / "scripts" / "tool.py").write_text(
                "#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8"
            )
            (project / "models" / "forbidden.gguf").write_bytes(b"weights")
            first = base / "first.zip"
            second = base / "second.zip"

            first_count, first_digest = build(project, first)
            second_count, second_digest = build(project, second)

            self.assertEqual(first_count, second_count)
            self.assertEqual(first_digest, second_digest)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                names = set(archive.namelist())
                self.assertIn(f"{ARCHIVE_ROOT}/README.md", names)
                self.assertIn(f"{ARCHIVE_ROOT}/scripts/tool.py", names)
                self.assertIn(f"{ARCHIVE_ROOT}/RELEASE_MANIFEST.sha256", names)
                self.assertFalse(any(name.endswith("forbidden.gguf") for name in names))
                manifest = archive.read(
                    f"{ARCHIVE_ROOT}/RELEASE_MANIFEST.sha256"
                ).decode("utf-8")
                self.assertIn("  README.md\n", manifest)
                self.assertIn("  scripts/tool.py\n", manifest)

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            (project / "README.md").write_text("release\n", encoding="utf-8")
            (project / "linked").symlink_to(project / "README.md")
            with self.assertRaisesRegex(RuntimeError, "symbolic links"):
                build(project, base / "release.zip")


if __name__ == "__main__":
    unittest.main()
