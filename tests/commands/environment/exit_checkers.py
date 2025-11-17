from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from .utils import walk_in_project_dir

if TYPE_CHECKING:
    from .helper import EnvironmentHelper


class ModifyInfo(NamedTuple):
    local: datetime | None
    cloud: datetime | None


def get_local_modify(
    env: 'EnvironmentHelper',
    path: Path
) -> datetime | None:
    assert env.temp_dir_local is not None
    local_file_path = Path(env.temp_dir_local.name) / path
    if local_file_path.exists():
        return datetime.fromtimestamp(
            local_file_path.lstat().st_mtime,
            tz=datetime.now().tzinfo
        )


def get_cloud_modify(
    env: 'EnvironmentHelper',
    path: Path
):
    cloud_file = env._file_from_path(str(path))
    return cloud_file.modified if cloud_file else None


def assert_synced(env: 'EnvironmentHelper') -> None:
    assert env.temp_dir_local is not None
    cloud_paths: set[Path] = {Path(i.path) for i in env.project.files}
    local_path = Path(env.temp_dir_local.name)
    local_paths: dict[Path, Path] = dict()
    for path in walk_in_project_dir(local_path):
        assert path.is_absolute()
        assert path.is_relative_to(local_path)
        local_paths[path.relative_to(local_path)] = path

    assert len(cloud_paths) == len(local_paths), (
        f"Different amount of files."
        f"\nLocal: {', '.join(str(i) for i in local_paths)}"
        f"\nCloud: {', '.join(str(i) for i in cloud_paths)}"
    )
    diff = cloud_paths.symmetric_difference(local_paths.keys())
    assert not diff, diff

    for file in env.project.files:
        full_path = local_path / file.path
        assert full_path.exists()
        assert full_path.is_file()
        cloud_mt = file.modified
        local_mt = datetime.fromtimestamp(
            local_paths[Path(file.path)].lstat().st_mtime,
            tz=cloud_mt.tzinfo
        )
        assert cloud_mt == local_mt, (
            f"Time diff for {file.path}, "
            f"{local_mt} vs {cloud_mt}"
        )

        cloud_size = file.size
        local_size = full_path.lstat().st_size
        assert local_size == cloud_size, (
            f"Size diff for {file.path}, "
            f"{local_size} vs {cloud_size}"
        )


def assert_new_files_created(env: 'EnvironmentHelper') -> None:
    assert env.temp_dir_local is not None
    local_path = Path(env.temp_dir_local.name)
    for new_local_file in env.new_local_files:
        path = new_local_file['path']
        full_path = local_path / path
        assert full_path.exists()
        assert full_path.is_file()
        stat = full_path.lstat()
        if (modified := new_local_file.get('modified', None)):
            assert stat.st_mtime == modified.timestamp()
        if (size := new_local_file.get('size', None)):
            assert stat.st_size == size
