"""Installer acceptance without requiring a Ren'Py runtime or npm."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from scripts.build_release import REQUIRED_FILES, build_both, build_release
from scripts.verify_release import verify_archive, verify_pair


class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'
        self.out = Path(self.tmp.name) / 'dist'
        for name in REQUIRED_FILES:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('# fixture\n', encoding='utf-8')
        self.ui = self.root / 'game' / 'renpy_inspector_web'
        (self.ui / 'assets').mkdir(parents=True)
        (self.ui / 'index.html').write_text(
            '<html><link rel="stylesheet" href="/assets/main-xyz.css">'
            '<script type="module" src="/assets/main-xyz.js"></script></html>',
            encoding='utf-8')
        (self.ui / 'assets' / 'main-xyz.js').write_text('console.log(1)', encoding='utf-8')
        (self.ui / 'assets' / 'main-xyz.css').write_text('body{}', encoding='utf-8')

    def build_pair(self):
        releases = build_both('v0.7.0', self.out, self.root, require_web=True)
        return releases[0][0], releases[1][0]

    def test_valid_built_assets_and_two_engine_parity(self):
        renpy7, renpy8 = self.build_pair()
        report = verify_pair(renpy7, renpy8)
        self.assertEqual(report['version'], 'v0.7.0')
        self.assertEqual([x['engine'] for x in report['packages']], ['renpy7', 'renpy8'])
        self.assertGreater(report['packages'][0]['entries'], len(REQUIRED_FILES))

    def test_tampered_zip_fails_checksum_before_distribution(self):
        renpy7, _ = self.build_pair()
        with renpy7.open('ab') as out:
            out.write(b'tamper')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            verify_archive(renpy7)

    def test_checksum_manifest_cannot_point_to_another_filename(self):
        renpy7, _ = self.build_pair()
        checksum = Path(str(renpy7) + '.sha256')
        checksum.write_text('0' * 64 + '  other.zip\n', encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'wrong format or filename'):
            verify_archive(renpy7)

    def test_html_referenced_asset_missing_is_rejected(self):
        self.ui.joinpath('index.html').write_text(
            '<link href="/assets/not-built.css"><script src="/assets/main-xyz.js"></script>',
            encoding='utf-8')
        renpy7, _ = self.build_pair()
        with self.assertRaisesRegex(ValueError, 'referenced but missing'):
            verify_archive(renpy7)

    def test_engine_archive_drift_is_rejected(self):
        renpy7, renpy8 = self.build_pair()
        (self.ui / 'assets' / 'main-xyz.js').write_text('console.log(2)', encoding='utf-8')
        build_release('v0.7.0', self.out, self.root, 'renpy8', require_web=True)
        with self.assertRaisesRegex(ValueError, 'package bytes differ'):
            verify_pair(renpy7, renpy8)

    def test_zip_traversal_member_rejected_even_with_fresh_checksum(self):
        renpy7, _ = self.build_pair()
        with ZipFile(renpy7, 'a') as out:
            extra = ZipInfo('../escape.txt')
            extra.external_attr = 0o100644 << 16
            out.writestr(extra, b'bad')
        digest = hashlib.sha256(renpy7.read_bytes()).hexdigest()
        Path(str(renpy7) + '.sha256').write_text(
            '{}  {}\n'.format(digest, renpy7.name), encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'Unsafe ZIP member'):
            verify_archive(renpy7)


if __name__ == '__main__':
    unittest.main()
