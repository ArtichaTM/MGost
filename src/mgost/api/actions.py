from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rich.progress import Progress

if TYPE_CHECKING:
    from mgost.api import ArtichaAPI
    from mgost.mgost import MGost


@dataclass(frozen=True, slots=True)
class Action(ABC):
    pass


@dataclass(frozen=True, slots=True)
class PostProgressAction(ABC):
    @abstractmethod
    async def progress_finished(self) -> None:
        raise NotImplementedError()


@dataclass(frozen=True, slots=True)
class MGostCompletableAction(Action, ABC):
    @abstractmethod
    async def complete_mgost(
        self, mgost: 'MGost',
        progress: Progress | None = None
    ) -> Action | None:
        raise NotImplementedError()


@dataclass(frozen=True, slots=True)
class APICompletableAction(MGostCompletableAction, ABC):
    async def complete_mgost(
        self, mgost, progress=None
    ) -> Action | None:
        return await self.complete_api(mgost.api, progress)

    @abstractmethod
    async def complete_api(
        self,
        api: 'ArtichaAPI',
        progress: Progress | None = None
    ) -> Action | None:
        raise NotImplementedError()


@dataclass(frozen=True, slots=True)
class PathAction(Action, ABC):
    root_path: Path
    project_id: int
    path: Path

    def __post_init__(self) -> None:
        assert self.root_path.is_absolute()
        assert not self.path.is_absolute()


@dataclass(frozen=True, slots=True)
class MoveAction(PathAction, ABC):
    file_id: int
    new_path: Path


@dataclass(frozen=True, slots=True)
class DoNothing(APICompletableAction):
    async def complete_api(self, api, progress=None):
        pass


@dataclass(frozen=True, slots=True)
class PostProgressMessageAction(APICompletableAction, PostProgressAction):
    label: str
    progress_message: str
    console_message: Callable[[], None]

    async def complete_api(self, api: 'ArtichaAPI', progress=None):
        if progress is not None:
            progress.add_task(
                description=f"? {self.label}",
                visible=True,
                refresh=True,
                bytes=False,
                total=0,
                completed=0
            )

    async def progress_finished(self) -> None:
        self.console_message()


@dataclass(frozen=True, slots=True)
class UploadFileAction(APICompletableAction):
    """POSTs under `remote_path` without `file_id`, PUTs over it with one"""

    project_id: int
    local_path: Path
    remote_path: str
    file_id: int | None

    def __post_init__(self) -> None:
        assert self.local_path.is_absolute()

    async def complete_api(self, api: 'ArtichaAPI', progress=None):
        await api.upload(
            project_id=self.project_id,
            local_path=self.local_path,
            remote_path=self.remote_path,
            file_id=self.file_id,
            progress=progress
        )


@dataclass(frozen=True, slots=True)
class DownloadFileAction(APICompletableAction, PathAction):
    file_id: int
    overwrite_ok: bool

    async def complete_api(self, api: 'ArtichaAPI', progress=None):
        await api.download(
            project_id=self.project_id,
            file_id=self.file_id,
            root_path=self.root_path,
            path=self.path,
            overwrite_ok=self.overwrite_ok,
            progress=progress
        )


@dataclass(frozen=True, slots=True)
class FileMovedLocally(APICompletableAction, MoveAction):
    """The file moved and its bytes are unchanged.

    PATCH is not one option among several: the server updates the
    project's markdown and docx pointers when the moved path matches
    one of them, and no other operation does. POST+DELETE would move
    the bytes while leaving the project pointing at a path that no
    longer exists.
    """

    async def complete_api(self, api: 'ArtichaAPI', progress=None):
        assert self.path != self.new_path
        await api.move_on_cloud(
            project_id=self.project_id,
            file_id=self.file_id,
            new_path=self.new_path
        )


@dataclass(frozen=True, slots=True)
class FileMovedAndEditedLocally(APICompletableAction, MoveAction):
    """The file moved and its content differs.

    Two strictly ordered calls: PATCH establishes where the file is,
    then one transfer settles what is in it. They cannot be gathered.
    The id survives the move, so the transfer addresses the same file.
    """

    local_newer: bool

    async def complete_api(self, api: 'ArtichaAPI', progress=None):
        assert self.path != self.new_path
        await api.move_on_cloud(
            project_id=self.project_id,
            file_id=self.file_id,
            new_path=self.new_path
        )
        if self.local_newer:
            await api.upload(
                project_id=self.project_id,
                local_path=self.root_path / self.new_path,
                remote_path=self.new_path.as_posix(),
                file_id=self.file_id,
                progress=progress
            )
        else:
            await api.download(
                project_id=self.project_id,
                file_id=self.file_id,
                root_path=self.root_path,
                path=self.new_path,
                overwrite_ok=True,
                progress=progress
            )
