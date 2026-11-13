"""Build deterministic, engine-labelled drop-in Ren'Py Inspector release ZIPs."""
from __future__ import annotations
import argparse
import hashlib
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    'game/renpy_inspector.rpy',
    'game/renpy_inspector_screens.rpy',
    'game/renpy_inspector_styles.rpy',
    'game/renpy_inspector/__init__.py',
    'game/renpy_inspector/controller.py',
    'game/renpy_inspector/inspection.py',
    'game/renpy_inspector/favorites.py',
    'game/renpy_inspector/settings.py',
    'game/renpy_inspector/search.py',
    'game/renpy_inspector/runtime.py',
    'game/renpy_inspector/runtime_history.py',
    'game/renpy_inspector/compat.py',
    'game/renpy_inspector/bridge.py',
    'game/renpy_inspector/edit_values.py',
    'game/renpy_inspector/bridge_snapshot.py',
    'game/renpy_inspector/bridge_paging.py',
    'game/renpy_inspector/bridge_search.py',
    'game/renpy_inspector/bridge_scripts.py',
    'game/renpy_inspector/browser_favourites.py',
)
ENGINES = {
    'renpy7': "Ren'Py 7.4.11 / 7.8.7 (Python 2.7)",
    'renpy8': "Ren'Py 8.4.1 / 8.5.3 (Python 3)",
}
VERSION_PATTERN = re.compile(r'v\d+\.\d+\.\d+\Z')


def collect_files(project_root: Path, require_web=False) -> list[Path]:
    """Collect installable source and optional *built* GUI assets, never project tooling."""
    game = project_root / 'game'
    package = game / 'renpy_inspector'
    missing = [p for p in REQUIRED_FILES if not (project_root / p).is_file()]
    if missing:
        raise ValueError('Missing required inspector source: ' + ', '.join(missing))
    # A release must not silently ship legacy in-game drawers or developer
    # helpers just because their names happen to start with renpy_inspector.
    allowed = set(project_root / path for path in REQUIRED_FILES)
    source_candidates = set(game.glob('renpy_inspector*.rpy')) | set(package.rglob('*.py'))
    extra_sources = sorted(
        path.relative_to(project_root).as_posix()
        for path in source_candidates - allowed)
    if extra_sources:
        raise ValueError('Unlisted inspector source(s); review/remove before release: ' +
                         ', '.join(extra_sources))
    files = set(allowed)
    ui = game / 'renpy_inspector_web'
    if ui.is_symlink() or package.is_symlink():
        raise ValueError('Inspector package and UI folders must not be symlinks')
    if (ui / 'index.html').is_file():
        ui_files = set(path for path in ui.rglob('*') if path.is_file())
        if require_web:
            # Fail closed on an incomplete build. The browser can return HTML
            # successfully yet remain blank when hashed JS/CSS are missing.
            js_assets = [p for p in ui_files if p.parent == ui / 'assets'
                         and p.suffix == '.js']
            css_assets = [p for p in ui_files if p.parent == ui / 'assets'
                          and p.suffix == '.css']
            if not js_assets or not css_assets:
                raise ValueError('Built Ant Design UI must include JS and CSS assets')
        files.update(ui_files)
    elif require_web:
        raise ValueError('Missing built Ant Design UI: game/renpy_inspector_web/index.html')
    files = sorted(files, key=lambda path: path.relative_to(project_root).as_posix())
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError('Release source is not a regular file: ' + str(path))
    return files


def _write_entry(output: ZipFile, name: str, content: bytes) -> None:
    info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    output.writestr(info, content, compress_type=ZIP_DEFLATED, compresslevel=9)


def build_release(version: str, output_dir: Path, project_root: Path = PROJECT_ROOT,
                  engine: str = 'renpy8', require_web=False) -> tuple[Path, Path]:
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError('Release version must match vMAJOR.MINOR.PATCH')
    if engine not in ENGINES:
        raise ValueError('Unknown Ren\'Py engine build: ' + engine)
    files = collect_files(project_root, require_web=require_web)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f'renpy-inspector-{version}-{engine}.zip'
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED, compresslevel=9) as output:
        for path in files:
            _write_entry(output, path.relative_to(project_root).as_posix(), path.read_bytes())
        note = (f"Ren'Py Inspector {version}\nTarget: {ENGINES[engine]}\n"
                'Extract this archive into the Ren\'Py game installation root.\n'
                'Only game/ contains installable files. This remains a prerelease;\n'
                'interactive save/load/rollback and FPS checks are not certified.\n')
        _write_entry(output, 'COMPATIBILITY.txt', note.encode('utf-8'))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = output_dir / f'{archive.name}.sha256'
    checksum.write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    return archive, checksum


def build_both(version: str, output_dir: Path, project_root: Path = PROJECT_ROOT, require_web=False):
    return tuple(build_release(version, output_dir, project_root, engine, require_web=require_web)
                 for engine in ENGINES)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version', help='Release tag, e.g. v0.7.0')
    parser.add_argument('--output-dir', type=Path, default=PROJECT_ROOT / 'dist')
    parser.add_argument('--engine', choices=('both',) + tuple(ENGINES), default='both')
    parser.add_argument('--require-web', action='store_true', help='Fail if compiled browser UI is missing')
    args = parser.parse_args()
    packages = (build_both(args.version, args.output_dir, require_web=args.require_web)
                if args.engine == 'both' else (build_release(args.version, args.output_dir, engine=args.engine, require_web=args.require_web),))
    for archive, checksum in packages:
        print('Built: {} (checksum: {})'.format(archive, checksum))


if __name__ == '__main__':
    main()
