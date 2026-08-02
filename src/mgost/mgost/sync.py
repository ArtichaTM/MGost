from asyncio import Task, create_task, gather
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING

from rich.progress import BarColumn, Progress, TaskID, TextColumn

from mgost.api.actions import (
    DoNothing, DownloadFileAction, FileMovedAndEditedLocally, FileMovedLocally,
    MGostCompletableAction, PostProgressAction, PostProgressMessageAction,
    UploadFileAction
)
from mgost.console import Console

from .matching import Match, Matcher, collect_candidates, file_digest
from .progress_utils import BytesOrIntColumn

if TYPE_CHECKING:
    from mgost.api.schemas.mgost import ProjectFile

    from .mgost import MGost


__all__ = ('sync', 'sync_file')

logger = getLogger(__name__)


class SyncError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Question:
    """A move the matcher proposes but will not perform unasked."""

    text: str
    on_yes: MGostCompletableAction
    on_no: MGostCompletableAction
    interactive_only: bool


@dataclass(slots=True)
class SyncPlan:
    actions: list[MGostCompletableAction] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)


def _local_is_newer(
    mgost: 'MGost', local_path: Path, cloud_modified: datetime
) -> bool:
    local_mt = datetime.fromtimestamp(
        (mgost.project_root / local_path).lstat().st_mtime,
        tz=timezone.utc
    )
    return (local_mt - cloud_modified).total_seconds() > 0


def _move_action(
    mgost: 'MGost',
    project_id: int,
    match: Match,
    cloud_modified: datetime,
) -> MGostCompletableAction:
    if match.rung == 1:
        return FileMovedLocally(
            mgost.project_root, project_id,
            match.cloud_path, match.local_path
        )
    return FileMovedAndEditedLocally(
        mgost.project_root, project_id,
        match.cloud_path, match.local_path,
        local_newer=_local_is_newer(
            mgost, match.local_path, cloud_modified
        )
    )


async def sync_file(
    mgost: 'MGost',
    project_id: int,
    path: Path,
    plan: SyncPlan,
    match: Match | None = None,
) -> None:
    """Append the action for `path` to `plan`.

    `match` is the matcher's proposal for a cloud file with no local
    file at its own path, or None when nothing was proposed.
    """
    assert isinstance(project_id, int)
    assert isinstance(path, Path)
    assert not path.is_absolute()
    project_files = await mgost.api.project_files(project_id)
    full_path = mgost.project_root / path
    local_exists = full_path.exists()
    cloud_exists = path in project_files
    match local_exists, cloud_exists:
        case True, False:
            logger.info(f'File "{path}" exists only locally')
            plan.actions.append(UploadFileAction(
                mgost.project_root, project_id, path, False
            ))
        case False, True:
            plan.actions.append(_cloud_only_action(
                mgost, project_id, path, project_files[path], match, plan
            ))
        case True, True:
            plan.actions.append(_both_present_action(
                mgost, project_id, path, project_files[path], full_path
            ))
        case False, False:
            plan.actions.append(_missing_everywhere_action(
                mgost, project_id, path
            ))


def _cloud_only_action(
    mgost: 'MGost',
    project_id: int,
    path: Path,
    cloud_file: 'ProjectFile',
    match: Match | None,
    plan: SyncPlan,
) -> MGostCompletableAction:
    download = DownloadFileAction(
        mgost.project_root, project_id, path, False
    )
    if match is None:
        logger.info(f'File "{path}" exists only on cloud')
        return download
    action = _move_action(mgost, project_id, match, cloud_file.modified)
    if match.rung == 1:
        return action
    plan.questions.append(Question(
        text=(
            f'Файл "{path.as_posix()}" перемещён '
            f'в "{match.local_path.as_posix()}"?'
        ),
        on_yes=action,
        on_no=download,
        interactive_only=match.rung == 3,
    ))
    return DoNothing()


def _both_present_action(
    mgost: 'MGost',
    project_id: int,
    path: Path,
    cloud_file: 'ProjectFile',
    full_path: Path,
) -> MGostCompletableAction:
    if full_path.lstat().st_size == cloud_file.size:
        # Sizes match, so a digest is cheap and settles it outright.
        # Hashing is skipped entirely when the sizes already differ.
        if file_digest(full_path) == cloud_file.hash:
            logger.info(f'File "{path}" identical on both sides')
            return DoNothing()
    cloud_mt = cloud_file.modified
    local_mt = datetime.fromtimestamp(
        full_path.lstat().st_mtime,
        tz=timezone.utc
    )
    assert cloud_mt.tzinfo is not None
    assert local_mt.tzinfo is not None
    difference = (local_mt - cloud_mt).total_seconds()
    # Difference < 0: cloud newer
    # Difference > 0: local newer
    if abs(difference) < 1:
        # Does not update <1s changes
        return DoNothing()
    elif difference < 0:
        logger.info(
            f'File "{path}" newer in cloud ('
            f'{difference}'
            ')'
        )
        return DownloadFileAction(
            mgost.project_root, project_id,
            path, True
        )
    elif difference > 0:
        logger.info(
            f'File "{path}" newer locally ('
            f'{difference}'
            ')'
        )
        return UploadFileAction(
            mgost.project_root, project_id,
            path, True
        )
    return DoNothing()


def _missing_everywhere_action(
    mgost: 'MGost',
    project_id: int,
    path: Path,
) -> MGostCompletableAction:
    logger.info(
        f'File "{path}" does not exist neither '
        'locally or on cloud'
    )

    def error_console():
        Console\
            .echo("Требуется файл ")\
            .echo(f"{path}", fg="cyan")\
            .echo(", однако он ")\
            .echo("не найден", fg="red")\
            .echo(" ни локально, ни в облаке")\
            .force_nl()
    assert mgost.info.settings.project_id is not None
    return PostProgressMessageAction(
        root_path=mgost.project_root,
        project_id=mgost.info.settings.project_id,
        path=path,
        progress_message=(
            f'Требуется файл {path}, '
            'однако он не найден '
            'ни локально, ни в облаке'
        ),
        console_message=error_console
    )


async def complete_with_progress(
    mgost: 'MGost',
    action: MGostCompletableAction,
    progress: Progress | None,
    main_task: TaskID | None
) -> None:
    assert isinstance(action, MGostCompletableAction)
    assert isinstance(progress, Progress)
    assert isinstance(main_task, int)
    await action.complete_mgost(mgost, progress)
    if progress:
        assert main_task is not None
        progress.advance(main_task)


async def plan_sync(mgost: 'MGost') -> SyncPlan:
    project_id = mgost.info.settings.project_id
    assert project_id is not None
    assert await mgost.api.is_project_available(project_id)
    project = await mgost.api.project(project_id)
    project_files = await mgost.api.project_files(project_id)
    requirements = await mgost.api.project_requirements(project_id)

    wanted = [
        project.path_to_markdown,
        project.path_to_docx,
        *(Path(r) for r in requirements),
    ]
    missing = {
        path: project_files[path]
        for path in wanted
        if path in project_files
        and not (mgost.project_root / path).exists()
    }
    matcher = Matcher(
        mgost.project_root,
        collect_candidates(mgost.project_root, tracked=project_files),
    )
    matches = {m.cloud_path: m for m in matcher.resolve(missing)}

    plan = SyncPlan()
    for path in wanted:
        await sync_file(
            mgost, project_id, path, plan, matches.get(path)
        )
    return plan


def confirm_sync(plan: SyncPlan) -> list[MGostCompletableAction]:
    """Answer pending questions before any progress display opens."""
    actions = list(plan.actions)
    for question in plan.questions:
        if question.interactive_only and not Console.is_prompts:
            # Console.confirm returns True unattended, which is the
            # opposite of what a no-evidence match needs.
            actions.append(question.on_no)
            continue
        answered = Console.confirm(question.text, default=True)
        actions.append(question.on_yes if answered else question.on_no)
    return actions


async def execute_sync(
    mgost: 'MGost', actions: list[MGostCompletableAction]
) -> None:
    with Progress(
        TextColumn('{task.description}'),
        BarColumn(),
        BytesOrIntColumn()
    ) as progress:
        if not Console.is_progress:
            main_task = None
            progress = None
        else:
            main_task = progress.add_task(
                description="Синхронизация",
                total=len(actions),
                start=True
            )
        tasks: list[Task] = []
        for action in actions:
            if progress:
                coro = complete_with_progress(
                    mgost=mgost, action=action,
                    progress=progress, main_task=main_task
                )
            else:
                coro = action.complete_mgost(mgost)
            tasks.append(create_task(coro, name=f"Action {action}"))
        await gather(*tasks)

    finished = [
        create_task(a.progress_finished())
        for a in actions
        if isinstance(a, PostProgressAction)
    ]
    if finished:
        await gather(*finished)


async def sync(mgost: 'MGost') -> None:
    Console.edit().echo(
        "Получение информации о проекте"
    ).nl().edit()
    plan = await plan_sync(mgost)
    actions = confirm_sync(plan)
    await execute_sync(mgost, actions)
