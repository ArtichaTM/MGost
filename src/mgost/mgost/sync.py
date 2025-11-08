from asyncio import Task, create_task, gather
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from rich.progress import BarColumn, Progress, TaskID, TextColumn

from mgost.api.actions import (
    Action, DoNothing, DownloadFileAction, FileMovedLocally,
    MGostCompletableAction, MoveAction, UploadFileAction
)
from mgost.console import Console

from .progress_utils import BytesOrIntColumn

if TYPE_CHECKING:
    from .mgost import MGost


__all__ = ('sync', 'sync_file')
CURRENT_TIMEZONE = datetime.now().astimezone().tzinfo


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
                Console\
                    .echo("Требуется файл ")\
                    .echo(f"{path}", fg="cyan")\
                    .echo(", однако он не найден ни локально")\
                    .echo(", ни в облаке")
                return DoNothing()
            return FileMovedLocally(project_id, path, new_path)


async def complete_with_progress(
    mgost: 'MGost',
    action: MGostCompletableAction,
    progress: Progress,
    main_task: TaskID
) -> None:
    assert isinstance(action, MGostCompletableAction)
    await action.complete_mgost(mgost, progress)
    progress.advance(main_task)


async def _sync_non_requirements_file(
    mgost: 'MGost',
    file: Literal['md'] | Literal['docx'],
    progress: Progress,
    main_task: TaskID
) -> None:
    assert file in {'md', 'docx'}
    project_id = mgost.info.settings.project_id
    assert project_id is not None
    assert await mgost.api.is_project_available(project_id)
    project = await mgost.api.project(project_id)
    match file:
        case 'md':
            cloud_path = project.path_to_markdown
        case 'docx':
            cloud_path = project.path_to_docx
        case _:
            raise RuntimeError(file)
    action = await sync_file(
        mgost, project_id, cloud_path
    )
    assert isinstance(action, MGostCompletableAction)
    await action.complete_mgost(mgost)
    if isinstance(action, MoveAction):
        match file:
            case 'md':
                mgost.info.settings.md_path = action.new_path
            case 'docx':
                mgost.info.settings.docx_path = action.new_path
            case _:
                raise RuntimeError((file, action))
    progress.advance(main_task)


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

    with Progress(
        TextColumn('{task.description}'),
        BarColumn(),
        BytesOrIntColumn()
    ) as progress:
        main_task = progress.add_task(
            description="Синхронизация",
            total=2,
            start=True
        )

        # Reusable variable
        await _sync_non_requirements_file(
            mgost, 'md', progress, main_task
        )

        project_requirements = await mgost.api.project_requirements(
            project_id
        )
        progress.update(
            main_task,
            total=2 + len(project_requirements),
            refresh=True,
        )

        actions: list[Action] = []
        for requirement in project_requirements:
            actions.append(await sync_file(
                mgost, project_id, Path(requirement)
            ))

        tasks: list[Task] = []
        for action in actions:
            assert isinstance(action, MGostCompletableAction)
            task = create_task(
                complete_with_progress(
                    mgost=mgost,
                    action=action,
                    progress=progress,
                    main_task=main_task
                ),
                name=f"Action {action}"
            )
            tasks.append(task)
        tasks.append(create_task(_sync_non_requirements_file(
            mgost, 'docx', progress, main_task
        )))

        await gather(*tasks)
