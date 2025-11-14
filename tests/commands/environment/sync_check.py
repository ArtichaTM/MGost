from datetime import datetime
from itertools import product
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from .helper import EnvironmentHelper


logger = getLogger(__name__)


class ModifyInfo(NamedTuple):
    local: datetime | None
    cloud: datetime | None


def get_local_modify(
    env: 'EnvironmentHelper',
    path: Path
) -> datetime | None:
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
    cloud_paths: set[Path] = {Path(i.path) for i in env.project.files}
    local_paths: set[Path] = set(env.local_files.keys())
    should_be_uploaded = cloud_paths.difference(local_paths)
    should_be_downloaded = local_paths.difference(cloud_paths)
    same_files_different_paths: set[tuple[Path, Path]] = set()
    for local, cloud in product(should_be_uploaded, should_be_downloaded):
        local_mt = get_local_modify(env, local)
        cloud_mt = get_cloud_modify(env, cloud)
        if local_mt == cloud_mt:
            same_files_different_paths.add((local, cloud))
