"""Exercise built static web UI inclusion in each engine ZIP."""
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.build_release import REQUIRED_FILES, build_release


class AntDesignPackagingTests(unittest.TestCase):
    def test_require_web_fails_closed_without_compiled_ui(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / 'repo'
            for name in REQUIRED_FILES:
                dest = repo / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text('# fixture\n', encoding='ascii')
            with self.assertRaisesRegex(ValueError, 'Missing built Ant Design UI'):
                build_release('v0.6.0', Path(temp) / 'dist', repo, 'renpy7', require_web=True)

    def test_web_build_is_included_without_node_modules(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / 'repo'
            for name in REQUIRED_FILES:
                dest = repo / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text('# generated test fixture\n', encoding='ascii')
            webroot = repo / 'game' / 'renpy_inspector_web'
            (webroot / 'assets').mkdir(parents=True)
            (webroot / 'index.html').write_text('<html>Ant Design</html>', encoding='ascii')
            (webroot / 'assets' / 'main.js').write_text('console.log(1)', encoding='ascii')
            (repo / 'web' / 'node_modules').mkdir(parents=True)
            (repo / 'web' / 'node_modules' / 'secret.txt').write_text('no', encoding='ascii')
            archive, _ = build_release('v0.6.0', Path(temp) / 'dist', repo, 'renpy7')
            with ZipFile(archive) as zf:
                names = zf.namelist()
                self.assertIn('game/renpy_inspector/edit_history.py', names)
                self.assertIn('game/renpy_inspector_web/index.html', names)
                self.assertIn('game/renpy_inspector_web/assets/main.js', names)
                self.assertFalse(any('node_modules' in n for n in names))


if __name__ == '__main__':
    unittest.main()
