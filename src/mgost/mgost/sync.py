import enum
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from mgost.api.actions import (
    Action, DoNothing, DownloadFileAction, FileMovedLocally,
    MGostCompletableAction, UploadFileAction
)
from mgost.console import Console

if TYPE_CHECKING:
    from .mgost import MGost


__all__ = ('sync', 'sync_file')
CURRENT_TIMEZONE = datetime.now().astimezone().tzinfo


class FilesCompare(enum.IntEnum):
    # Local file is newer than cloud file
    LOCAL_NEWER = enum.auto()

    # Cloud file is newer than local file
    CLOUD_NEWER = enum.auto()

    # Both files have the same modification time
    SAME_TIME = enum.auto()

    # File exists only locally
    LOCAL_ONLY = enum.auto()

    # File exists only in cloud
    CLOUD_ONLY = enum.auto()

    # Files have same modification time but different sizes/content
    SAME_TIME_DIFFERENT_CONTENT = enum.auto()

    # Error occurred during comparison
    COMPARISON_ERROR = enum.auto()


class SyncError(Exception):
    pass


def _compare_file_to(
    path: Path,
    filename: str | None = None,
    birth_time: datetime | None = None,
    size: int | None = None
) -> bool:
    stat = path.lstat()
    if filename is not None and path.name == filename:
        return True
    if birth_time is not None and stat.st_birthtime == birth_time:
        return True
    if size is not None and stat.st_size == size:
        return True
    return False


def _search_file(
    root_path: Path,
    filename: str | None = None,
    birth_time: datetime | None = None,
    size: int | None = None
) -> Path | None:
    assert isinstance(root_path, Path)
    assert isinstance(birth_time, datetime)
    assert isinstance(size, int)
    for directory, _, files in root_path.walk():
        if directory.name.startswith('.'):
            continue
        for file in files:
            current_file_path = directory / file
            result = _compare_file_to(
                current_file_path,
                filename=filename,
                birth_time=birth_time,
                size=size
            )
            if result:
                return current_file_path


def sync_file(
    mgost: 'MGost',
    project_id: int,
    path: Path
) -> Action:
    assert isinstance(project_id, int)
    assert isinstance(path, Path)
    project_files = mgost.api.project_files(project_id)
    local_md_exists = path.exists()
    cloud_md_exists = path in project_files
    match local_md_exists, cloud_md_exists:
        case True, False:
            return UploadFileAction(project_id, path, False)
        case False, True:
            project_file = project_files[path]
            new_path = _search_file(
                mgost._root_path,
                filename=path.name,
                birth_time=project_file.created,
                size=project_file.size
            )
            if new_path is None:
                return DownloadFileAction(project_id, path, False)
            return FileMovedLocally(project_id, path, new_path)
        case True, True:
            cloud_mt = project_files[path].modified
            local_mt = datetime.fromtimestamp(
                path.lstat().st_mtime,
                tz=CURRENT_TIMEZONE
            )
            if cloud_mt > local_mt:
                return DownloadFileAction(project_id, path, True)
            elif cloud_mt < local_mt:
                return UploadFileAction(project_id, path, True)
            return DoNothing()
        case False, False:
            new_path = _search_file(
                mgost._root_path,
                filename=path.name
            )
            if new_path is None:
                raise FileNotFoundError
            return FileMovedLocally(project_id, path, new_path)


def _sync_main_md(
    mgost: 'MGost',
    project_id: int
) -> Action:
    assert isinstance(project_id, int)
    path = mgost.api.project(project_id).path_to_markdown
    try:
        action = sync_file(mgost, project_id, path)
    except FileNotFoundError:
        # TODO: What to do if file not found
        return DoNothing()
    return action


def sync(mgost: 'MGost') -> None:
    project_id = mgost.info.settings.project_id
    assert project_id is not None
    assert mgost.api.is_project_available(project_id)

    # pb = progressbar(length=3)
    action = _sync_main_md(mgost, project_id)
    while action is not None:
        Console\
            .edit()\
            .echo(
                "Синхронизация главного md файла"
            )\
            .nl()
        if isinstance(action, MGostCompletableAction):
            action = action.complete_mgost(mgost)
        else:
            raise RuntimeError(f"How to complete {action}?")

    Console\
        .echo(
            "Получение списка необходимых"
            " файлов для рендера проекта"
        )\
        .nl()

    # print(action)
    # project = mgost.api.project(project_id)
    # cloud_files = mgost.api.project_files(project_id)
    # local_files = mgost.info.files
