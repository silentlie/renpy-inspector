"""Build a deterministic, drop-in Ren'Py Inspector release ZIP."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "game/renpy_inspector.rpy",
    "game/renpy_inspector_screens.rpy",
    "game/renpy_inspector_styles.rpy",
    "game/renpy_inspector/__init__.py",
    "game/renpy_inspector/controller.py",
    "game/renpy_inspector/inspection.py",
    "game/renpy_inspector/favorites.py",
    "game/renpy_inspector/settings.py",
)
VERSION_PATTERN = re.compile(r"v\d+\.\d+\.\d+\Z")


def collect_files(project_root: Path) -> list[Path]:
    """Include only installable source, never compiled files or fixture saves."""
    game = project_root / "game"
    package = game / "renpy_inspector"
    missing = [p for p in REQUIRED_FILES if not (project_root / p).is_file()]
    if missing:
        raise ValueError("Missing required inspector source: " + ", ".join(missing))

    files = sorted(
        set(game.glob("renpy_inspector*.rpy")) | set(package.rglob("*.py")),
        key=lambda path: path.relative_to(project_root).as_posix(),
    )
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError("Release source is not a regular file: " + str(path))
    return files


def build_release(
    version: str,
    output_dir: Path,
    project_root: Path = PROJECT_ROOT,
) -> tuple[Path, Path]:
    """Return the ZIP and GNU sha256sum-compatible checksum paths."""
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("Release version must match vMAJOR.MINOR.PATCH")

    files = collect_files(project_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"renpy-inspector-{version}.zip"

    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as output:
        for path in files:
            info = ZipInfo(path.relative_to(project_root).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            output.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = output_dir / f"{archive.name}.sha256"
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return archive, checksum


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release tag, e.g. v0.2.0")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "dist")
    arguments = parser.parse_args()
    archive, checksum = build_release(arguments.version, arguments.output_dir)
    print(f"Built: {archive}")
    print(f"SHA-256: {checksum}")


if __name__ == "__main__":
    main()
