"""Smoke the installed layout without requiring a running Ren'Py game."""
import tempfile
import unittest
from pathlib import Path

from scripts.build_release import REQUIRED_FILES
from scripts.check_install import check_install


class InstalledLayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'Example Game'
        for name in REQUIRED_FILES:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text('# fixture\n', encoding='utf-8')
        self.ui = self.root / 'game' / 'renpy_inspector_web'
        (self.ui / 'assets').mkdir(parents=True)
        (self.ui / 'assets' / 'index-123.js').write_text('1', encoding='utf-8')
        (self.ui / 'assets' / 'index-123.css').write_text('a{}', encoding='utf-8')
        (self.ui / 'index.html').write_text(
            '<script src="/assets/index-123.js"></script>'
            '<link href="/assets/index-123.css" rel="stylesheet">',
            encoding='utf-8')

    def test_valid_install(self):
        result = check_install(self.root)
        self.assertEqual(result['verified_sources'], len(REQUIRED_FILES))
        self.assertEqual(result['browser_assets'], 2)
        self.assertEqual(result['warnings'], [])

    def test_wrong_extraction_root(self):
        nested = self.root / 'game' / 'game' / 'renpy_inspector.rpy'
        nested.parent.mkdir(parents=True)
        nested.write_text('old', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'too deep'):
            check_install(self.root)

    def test_missing_web_asset_fails(self):
        (self.ui / 'assets' / 'index-123.js').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing browser asset'):
            check_install(self.root)

    def test_obsolete_drawer_source_is_rejected(self):
        old = self.root / 'game' / 'renpy_inspector_tree.rpy'
        old.write_text('screen renpy_inspector_drawer():\n    pass\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Unexpected legacy inspector screen'):
            check_install(self.root)

    def test_orphan_compiled_screen_is_flagged_without_deleting(self):
        old = self.root / 'game' / 'renpy_inspector_tree.rpyc'
        old.write_bytes(b'compiled')
        report = check_install(self.root)
        self.assertEqual(len(report['warnings']), 1)
        self.assertTrue(old.is_file())


if __name__ == '__main__':
    unittest.main()
