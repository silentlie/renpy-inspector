"""Non-destructive check of an extracted Ren'Py Inspector game installation.

Invoke on the *game installation root* (the directory containing game/).
This checks files and browser references; it cannot prove that F8, actual
gameplay or the Ren'Py callbacks work in a real running game.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

try:
    from .build_release import REQUIRED_FILES
except ImportError:
    from build_release import REQUIRED_FILES


def check_install(root: Path) -> dict:
    root = Path(root)
    if not (root / 'game').is_dir():
        raise ValueError('No game/ directory; pass the installation root, not game/')
    if (root / 'game' / 'game' / 'renpy_inspector.rpy').exists():
        raise ValueError('Installer extracted one directory too deep (game/game/); '
                         're-extract the engine ZIP at the installation root')
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        raise ValueError('Missing inspector installer files: ' + ', '.join(missing))
    ui = root / 'game' / 'renpy_inspector_web'
    index = ui / 'index.html'
    if not index.is_file():
        raise ValueError('Missing browser UI index.html; extract the inner engine ZIP')
    html = index.read_text(encoding='utf-8')
    references = re.findall(r'(?:src|href)=[\'"]/?(assets/[^\'"]+)[\'"]', html)
    if not any(name.endswith('.js') for name in references) or not any(
            name.endswith('.css') for name in references):
        raise ValueError('Browser index.html lacks compiled JS/CSS references')
    for asset in references:
        if not (ui / asset).is_file():
            raise ValueError('Missing browser asset referenced by index: ' + asset)
    allowed_game = set(Path(name).name for name in REQUIRED_FILES
                       if name.endswith('.rpy'))
    extras = sorted(path.name for path in (root / 'game').glob('renpy_inspector*.rpy')
                    if path.name not in allowed_game)
    if extras:
        raise ValueError('Unexpected legacy inspector screen(s): ' + ', '.join(extras))
    warnings = []
    for bytecode in (root / 'game').glob('renpy_inspector*.rpyc'):
        if not bytecode.with_suffix('.rpy').exists():
            warnings.append('Orphan legacy bytecode: ' + bytecode.name)
    return {'verified_sources': len(REQUIRED_FILES), 'browser_assets': len(references),
            'warnings': warnings}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game_root', type=Path)
    args = parser.parse_args()
    report = check_install(args.game_root)
    print('Inspector install layout OK: {verified_sources} sources, '
          '{browser_assets} browser references'.format(**report))
    for warning in report['warnings']:
        print('WARNING: ' + warning)


if __name__ == '__main__':
    main()
