import enum
from asyncio import Task, create_task, gather
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn

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
        # If it some variable suffix, return True without compare
        # If not, compare suffix
        if path.suffix not in {
            'md', 'docx', 'xlsx'
        }:
            return True
        extensions = (
            path.suffix,
            Path(filename).suffix
        )
        return extensions[0] == extensions[1]
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
    assert filename is None or isinstance(filename, str)
    assert birth_time is None or isinstance(birth_time, datetime)
    assert size is None or isinstance(size, int)
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


async def sync_file(
    mgost: 'MGost',
    project_id: int,
    path: Path
) -> Action:
    """Calculating required action to sync files
        cloud<->local by path
    :raises FileNotFoundError: Exception raised when file can't be found
        nor in cloud nor locally
    :return: Returns action required to sync passed path
    """
    assert isinstance(project_id, int)
    assert isinstance(path, Path)
    project_files = await mgost.api.project_files(project_id)
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


async def sync(mgost: 'MGost') -> None:
    project_id = mgost.info.settings.project_id
    assert project_id is not None
    assert await mgost.api.is_project_available(project_id)

    Console\
        .edit()\
        .echo(
            "Получение информации о проекте"
        )\
        .nl()\
        .edit()

    project = await mgost.api.project(project_id)

    Console\
        .edit()\
        .echo(
            "Обновление md файла"
        )\
        .nl()\
        .edit()

    md_action = await sync_file(
        mgost,
        project_id,
        Path(project.path_to_markdown)
    )
    if isinstance(md_action, MGostCompletableAction):
        await md_action.complete_mgost(mgost)
    else:
        raise RuntimeError(f"How to complete {md_action}?")

    Console\
        .edit()\
        .echo(
            "Получение списка необходимых"
            " файлов для рендера проекта"
        )\
        .nl()\
        .edit()

    project_requirements = await mgost.api.project_requirements(
        project_id
    )

    actions: list[Action] = []
    for requirement in project_requirements:
        actions.append(await sync_file(mgost, project_id, Path(requirement)))

    tasks: list[Task] = []
    with Progress(
        TextColumn('Синхронизация'),
        BarColumn(),
        MofNCompleteColumn(),
        auto_refresh=True
    ) as progress:
        for action in actions:
            if isinstance(action, MGostCompletableAction):
                task = create_task(action.complete_mgost(
                    mgost, progress=progress
                ))
                tasks.append(task)
            else:
                raise RuntimeError(f"How to complete {action}?")

    await gather(*tasks)
