from pathlib import Path
from typing import Generator


def walk_in_project_dir(project_root: Path) -> Generator[Path, None, None]:
    """Iterates over a path and yields FULL PATH"""
    for directory, _, files in project_root.walk():
        if directory.name == '.mgost':
            continue
        for file_path in files:
            full_path = directory / file_path
            assert full_path.is_absolute()
            yield full_path
