"""Assemble a clean Ren'Py project with the current drop-in inspector source."""

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare_fixture(destination, root=ROOT):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('fixture output already exists: ' + str(destination))
    shutil.copytree(root / 'tests' / 'fixtures' / 'renpy-game', destination)
    game = destination / 'game'
    for path in (root / 'game').glob('renpy_inspector*.rpy'):
        shutil.copy2(path, game / path.name)
    shutil.copytree(root / 'game' / 'renpy_inspector', game / 'renpy_inspector',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(prepare_fixture(args.output))


if __name__ == '__main__':
    main()
