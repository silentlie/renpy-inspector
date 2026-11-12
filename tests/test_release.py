"""Release artifact tests that do not require the Ren'Py SDK."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.build_release import REQUIRED_FILES, build_release, build_both


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
        # A stray historical Python module must never enter the installer.
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
                sorted(REQUIRED_FILES) + ["COMPATIBILITY.txt"],
            )
            self.assertEqual(zf.read(REQUIRED_FILES[0]), f"# {REQUIRED_FILES[0]}\n".encode())
        self.assertEqual(
            checksum.read_text(encoding="ascii"),
            f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n",
        )

    def test_two_engine_packages_have_same_installable_source(self):
        builds = build_both("v0.4.0", self.out, self.root)
        self.assertEqual(len(builds), 2)
        names = [a.name for a, _ in builds]
        self.assertEqual(names, ["renpy-inspector-v0.4.0-renpy7.zip",
                                 "renpy-inspector-v0.4.0-renpy8.zip"])
        with ZipFile(builds[0][0]) as a, ZipFile(builds[1][0]) as b:
            for path in REQUIRED_FILES:
                self.assertEqual(a.read(path), b.read(path))
            self.assertIn(b"Python 2.7", a.read("COMPATIBILITY.txt"))
            self.assertIn(b"Python 3", b.read("COMPATIBILITY.txt"))

    def test_reproducible_zip(self):
        a, _ = build_release("v0.2.0", self.out, self.root)
        original = a.read_bytes()
        b, _ = build_release("v0.2.0", self.out, self.root)
        self.assertEqual(original, b.read_bytes())

    def test_rejects_invalid_versions(self):
        for version in ["v0.2", "v0.2.0-dev", "../oops", "v0.2.0/other", ""]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                build_release(version, self.out, self.root)

    def test_rejects_extra_source_modules_and_legacy_overlay_files(self):
        package = self.root / 'game' / 'renpy_inspector'
        extra = package / 'unexpected.py'
        extra.write_text('# should not ship\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Unlisted inspector source'):
            build_release('v0.7.0', self.out, self.root)
        extra.unlink()
        legacy = self.root / 'game' / 'renpy_inspector_tree.rpy'
        legacy.write_text('screen renpy_inspector_drawer():\n    pass\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'renpy_inspector_tree.rpy'):
            build_release('v0.7.0', self.out, self.root)

    def test_rejects_incomplete_or_symlinked_web_assets(self):
        ui = self.root / 'game' / 'renpy_inspector_web'
        (ui / 'assets').mkdir(parents=True)
        (ui / 'index.html').write_text('<html></html>', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'JS and CSS'):
            build_release('v0.7.0', self.out, self.root, require_web=True)
        (ui / 'assets' / 'index.js').write_text('console.log(1)', encoding='utf-8')
        (ui / 'assets' / 'index.css').write_text('body{}', encoding='utf-8')
        build_release('v0.7.0', self.out, self.root, require_web=True)
        try:
            (ui / 'assets' / 'evil.js').symlink_to(ui / 'assets' / 'index.js')
        except (OSError, NotImplementedError):
            return
        with self.assertRaisesRegex(ValueError, 'regular file'):
            build_release('v0.7.0', self.out, self.root, require_web=True)

    def test_unknown_engine_is_rejected(self):
        with self.assertRaises(ValueError):
            build_release("v0.4.0", self.out, self.root, engine="mystery")

    def test_required_sources_must_exist(self):
        (self.root / REQUIRED_FILES[0]).unlink()
        with self.assertRaisesRegex(ValueError, "Missing required inspector source"):
            build_release("v0.2.0", self.out, self.root)


if __name__ == "__main__":
    unittest.main()
