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
from .paths import External, classify
from .progress_utils import BytesOrIntColumn

if TYPE_CHECKING:
    from mgost.api.schemas.mgost import ProjectFile

    from .mgost import MGost


__all__ = ('sync', )

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
    cloud_file: 'ProjectFile',
) -> MGostCompletableAction:
    if match.rung == 1:
        return FileMovedLocally(
            mgost.project_root, project_id,
            match.cloud_path, cloud_file.id, match.local_path
        )
    return FileMovedAndEditedLocally(
        mgost.project_root, project_id,
        match.cloud_path, cloud_file.id, match.local_path,
        local_newer=_local_is_newer(
            mgost, match.local_path, cloud_file.modified
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
                project_id, full_path, path.as_posix(), None
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
            plan.actions.append(_missing_everywhere_action(path.as_posix()))


def _cloud_only_action(
    mgost: 'MGost',
    project_id: int,
    path: Path,
    cloud_file: 'ProjectFile',
    match: Match | None,
    plan: SyncPlan,
) -> MGostCompletableAction:
    download = DownloadFileAction(
        mgost.project_root, project_id, path, cloud_file.id, False
    )
    if match is None:
        logger.info(f'File "{path}" exists only on cloud')
        return download
    action = _move_action(mgost, project_id, match, cloud_file)
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
            path, cloud_file.id, True
        )
    elif difference > 0:
        logger.info(
            f'File "{path}" newer locally ('
            f'{difference}'
            ')'
        )
        return UploadFileAction(
            project_id, full_path, path.as_posix(), cloud_file.id
        )
    return DoNothing()


def _message_action(
    label: str, *segments: str | tuple[str, str]
) -> PostProgressMessageAction:
    """Printed once progress output closes; a tuple is `(text, colour)`"""
    def console_message() -> None:
        for segment in segments:
            if isinstance(segment, tuple):
                Console.echo(segment[0], fg=segment[1])
            else:
                Console.echo(segment)
        Console.force_nl()
    return PostProgressMessageAction(
        label=label,
        progress_message=''.join(
            i[0] if isinstance(i, tuple) else i for i in segments
        ),
        console_message=console_message
    )


def _missing_everywhere_action(label: str) -> MGostCompletableAction:
    logger.info(
        f'File "{label}" does not exist neither '
        'locally or on cloud'
    )
    return _message_action(
        label,
        'Требуется файл ', (label, 'cyan'), ', однако он ',
        ('не найден', 'red'), ' ни локально, ни в облаке'
    )


def _external_actions(
    mgost: 'MGost',
    project_id: int,
    external: External,
    cloud_file: 'ProjectFile | None',
    md_dir: Path,
) -> list[MGostCompletableAction]:
    """Upload-only: nothing is ever written outside the project"""
    written = external.written
    local = external.local
    actions: list[MGostCompletableAction] = []
    if local is not None and local.is_relative_to(mgost.project_root):
        actions.append(_message_action(
            written,
            'Путь ', (written, 'cyan'), ' указывает внутрь папки проекта, '
            'запишите его относительно: ',
            (local.relative_to(md_dir, walk_up=True).as_posix(), 'green')
        ))
    if local is None or not local.is_file():
        if cloud_file is None:
            actions.append(_missing_everywhere_action(written))
        else:
            logger.info(f'External file "{written}" exists only on cloud')
            actions.append(_message_action(
                written,
                'Внешний файл ', (written, 'cyan'),
                ' не найден локально, в документ попадёт копия из облака'
            ))
        return actions
    if cloud_file is None:
        logger.info(f'External file "{written}" exists only locally')
        actions.append(UploadFileAction(project_id, local, written, None))
        return actions
    if (
        local.lstat().st_size == cloud_file.size
        and file_digest(local) == cloud_file.hash
    ):
        logger.info(f'External file "{written}" identical on both sides')
        return actions
    local_mt = datetime.fromtimestamp(local.lstat().st_mtime, tz=timezone.utc)
    if (cloud_file.modified - local_mt).total_seconds() >= 1:
        actions.append(_message_action(
            written,
            'Внешний файл ', (written, 'cyan'), ' в облаке ',
            ('новее', 'yellow'), ' локального, облачная копия заменена'
        ))
    logger.info(f'External file "{written}" differs, uploading')
    actions.append(UploadFileAction(
        project_id, local, written, cloud_file.id
    ))
    return actions


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
    root = mgost.project_root
    project = await mgost.api.project(project_id)
    # Requirements first: answering them may create files on the server
    requirements = await mgost.api.project_requirements(project_id)
    project_files = await mgost.api.project_files(project_id)
    fictional_files = await mgost.api.fictional_files(project_id)

    wanted = [project.path_to_markdown, project.path_to_docx]
    # Keyed by file id when uploaded: two spellings may name one file
    externals: dict[int | str, tuple[External, 'ProjectFile | None']] = {}
    for requirement in requirements:
        kind = classify(root, requirement.path)
        if isinstance(kind, Path):
            wanted.append(kind)
            continue
        cloud_file = None
        if requirement.file_id is not None:
            cloud_file = fictional_files.get(requirement.file_id)
        key = kind.written if cloud_file is None else cloud_file.id
        externals.setdefault(key, (kind, cloud_file))

    # An absolute path into the project is still external, so its local
    # file mustn't stand in for a moved ordinary one
    inside = {
        external.local.relative_to(root)
        for external, _ in externals.values()
        if external.local is not None and external.local.is_relative_to(root)
    }
    missing = {
        path: project_files[path]
        for path in wanted
        if path in project_files
        and not (root / path).exists()
    }
    matcher = Matcher(
        root, collect_candidates(root, tracked={*project_files, *inside}),
    )
    matches = {m.cloud_path: m for m in matcher.resolve(missing)}

    plan = SyncPlan()
    for path in wanted:
        await sync_file(
            mgost, project_id, path, plan, matches.get(path)
        )
    md_dir = root / project.path_to_markdown.parent
    for external, cloud_file in externals.values():
        plan.actions.extend(_external_actions(
            mgost, project_id, external, cloud_file, md_dir
        ))
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
