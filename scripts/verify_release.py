"""Verify release ZIP safety, web asset completeness, checksums and engine parity.

Run before distributing an archive. This validates packaging, not interactive
Ren'Py compatibility, FPS or save/rollback semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

try:
    from .build_release import REQUIRED_FILES
except ImportError:  # direct: python scripts/verify_release.py ...
    from build_release import REQUIRED_FILES

ARCHIVE_NAME = re.compile(r'renpy-inspector-(v\d+\.\d+\.\d+)-(renpy7|renpy8)\.zip\Z')
CHECKSUM_LINE = re.compile(r'([a-f0-9]{64})  ([^\r\n]+)\n?\Z')
WEB_ROOT = 'game/renpy_inspector_web/'
WEB_INDEX = WEB_ROOT + 'index.html'
MAX_ENTRY_BYTES = 4 * 1024 * 1024
MAX_UNPACKED_BYTES = 16 * 1024 * 1024


def verify_archive(archive: Path, checksum: Path | None = None,
                   require_web: bool = True) -> dict:
    archive = Path(archive)
    match = ARCHIVE_NAME.fullmatch(archive.name)
    if not match:
        raise ValueError('Invalid engine/version archive name: ' + archive.name)
    version, engine = match.groups()
    checksum = Path(checksum) if checksum is not None else Path(str(archive) + '.sha256')
    checksum_match = CHECKSUM_LINE.fullmatch(checksum.read_text(encoding='ascii'))
    if checksum_match is None or checksum_match.group(2) != archive.name:
        raise ValueError('Checksum manifest has wrong format or filename')
    digest = hashlib.sha256()
    with archive.open('rb') as source:
        for chunk in iter(lambda: source.read(65536), b''):
            digest.update(chunk)
    if digest.hexdigest() != checksum_match.group(1):
        raise ValueError('Release archive checksum mismatch')

    with ZipFile(archive) as bundle:
        infos = bundle.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP entries')
        total = 0
        for info in infos:
            name = info.filename
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith('/') or '\\' in name or
                    any(part in ('.', '..') for part in parts) or name.endswith('/')):
                raise ValueError('Unsafe ZIP member: ' + name)
            if (name not in REQUIRED_FILES and name != 'COMPATIBILITY.txt' and
                    name != WEB_INDEX and
                    not (name.startswith(WEB_ROOT + 'assets/') and
                         len(parts) == 4)):
                raise ValueError('Non-installable ZIP member: ' + name)
            if ((info.external_attr >> 16) & 0o170000) != 0o100000:
                raise ValueError('ZIP member is not a regular file: ' + name)
            total += info.file_size
            if info.file_size > MAX_ENTRY_BYTES or total > MAX_UNPACKED_BYTES:
                raise ValueError('ZIP exceeds the installable size budget')
        missing = set(REQUIRED_FILES) - set(names)
        if missing:
            raise ValueError('Missing source from ZIP: ' + ', '.join(sorted(missing)))
        note = bundle.read('COMPATIBILITY.txt').decode('utf-8')
        expected_engine = 'Python 2.7' if engine == 'renpy7' else 'Python 3'
        if 'Ren\'Py Inspector ' + version not in note or expected_engine not in note:
            raise ValueError('Incorrect engine/version compatibility note')
        if require_web:
            if WEB_INDEX not in names:
                raise ValueError('Browser index.html missing from ZIP')
            html = bundle.read(WEB_INDEX).decode('utf-8')
            # Vite produces a hashed asset referenced by each src/href; do
            # not mistake an empty assets directory for a working application.
            references = re.findall(r'(?:src|href)=[\'"]/?(assets/[^\'"]+)[\'"]', html)
            scripts = [item for item in references if item.endswith('.js')]
            styles = [item for item in references if item.endswith('.css')]
            if not scripts or not styles:
                raise ValueError('Browser index does not reference compiled JS and CSS')
            for asset in scripts + styles:
                if WEB_ROOT + asset not in names:
                    raise ValueError('Browser asset referenced but missing: ' + asset)
        corrupt = bundle.testzip()
        if corrupt is not None:
            raise ValueError('Corrupt ZIP member: ' + corrupt)
    return {'version': version, 'engine': engine, 'entries': len(names),
            'unpacked_bytes': total, 'archive': str(archive)}


def verify_pair(renpy7: Path, renpy8: Path, require_web: bool = True) -> dict:
    results = [verify_archive(renpy7, require_web=require_web),
               verify_archive(renpy8, require_web=require_web)]
    if [item['engine'] for item in results] != ['renpy7', 'renpy8']:
        raise ValueError('Pass the Ren\'Py 7 and Ren\'Py 8 archives in order')
    if results[0]['version'] != results[1]['version']:
        raise ValueError('Dual-engine package versions differ')
    with ZipFile(renpy7) as left, ZipFile(renpy8) as right:
        common = set(left.namelist()) - {'COMPATIBILITY.txt'}
        if common != set(right.namelist()) - {'COMPATIBILITY.txt'}:
            raise ValueError('Engine package file manifests differ')
        for name in common:
            if left.read(name) != right.read(name):
                raise ValueError('Engine package bytes differ: ' + name)
    return {'version': results[0]['version'], 'packages': results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('renpy7', type=Path, help='Ren\'Py 7 archive')
    parser.add_argument('renpy8', type=Path, help='Ren\'Py 8 archive')
    args = parser.parse_args()
    report = verify_pair(args.renpy7, args.renpy8)
    print('Verified {version}: both engine ZIPs, checksums, files and web assets'.format(**report))


if __name__ == '__main__':
    main()
