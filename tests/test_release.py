"""Release artifact tests that do not require the Ren'Py SDK."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.build_release import REQUIRED_FILES, build_release


class ReleaseBuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.out = Path(self.tmp.name) / "dist"
        for filename in REQUIRED_FILES:
            path = self.root / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {filename}\n", encoding="utf-8")

    def test_zip_contains_only_installable_sources(self):
        package = self.root / "game" / "renpy_inspector"
        (package / "extra.py").write_text("# extra\n", encoding="utf-8")
        (package / "extra.pyc").write_bytes(b"bytecode")
        (package / "__pycache__").mkdir()
        (package / "__pycache__" / "inspection.pyc").write_bytes(b"bytecode")
        (self.root / "game" / "savegame.save").write_bytes(b"private data")
        (self.root / "game" / "renpy_inspector_screens.rpyc").write_bytes(b"compiled")
        (self.root / "game" / "unrelated_story.rpy").write_text("# not ours\n")

        archive, checksum = build_release("v0.2.0", self.out, self.root)
        with ZipFile(archive) as zf:
            self.assertIsNone(zf.testzip())
            self.assertEqual(
                zf.namelist(),
                sorted([*REQUIRED_FILES, "game/renpy_inspector/extra.py"]),
            )
            self.assertEqual(zf.read(REQUIRED_FILES[0]), f"# {REQUIRED_FILES[0]}\n".encode())
        self.assertEqual(
            checksum.read_text(encoding="ascii"),
            f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n",
        )

    def test_reproducible_zip(self):
        a, _ = build_release("v0.2.0", self.out, self.root)
        original = a.read_bytes()
        b, _ = build_release("v0.2.0", self.out, self.root)
        self.assertEqual(original, b.read_bytes())

    def test_rejects_invalid_versions(self):
        for version in ["v0.2", "v0.2.0-dev", "../oops", "v0.2.0/other", ""]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                build_release(version, self.out, self.root)

    def test_required_sources_must_exist(self):
        (self.root / REQUIRED_FILES[0]).unlink()
        with self.assertRaisesRegex(ValueError, "Missing required inspector source"):
            build_release("v0.2.0", self.out, self.root)


if __name__ == "__main__":
    unittest.main()
