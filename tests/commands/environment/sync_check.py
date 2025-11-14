from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

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
    # Relative path too rout project : full path
    local_paths: dict[Path, Path] = dict()
    for directory, _, files in local_path.walk():
        if directory.name == '.mgost':
            continue
        for file_path in files:
            full_path = directory / file_path
            relative_path = full_path.relative_to(local_path)
            local_paths[relative_path] = full_path

    diff = cloud_paths.symmetric_difference(local_paths.keys())
    assert not diff, diff

    for file in env.project.files:
        cloud_mt = file.modified
        local_mt = datetime.fromtimestamp(
            local_paths[Path(file.path)].lstat().st_mtime,
            tz=datetime.now().tzinfo
        )
        assert cloud_mt == local_mt, f"Time diff for {file.path}"

        cloud_size = file.size
        local_size = (local_path / file.path).lstat().st_size
        assert cloud_size == local_size, f"Size diff for {file.path}"
