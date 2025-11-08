from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rich.progress import Progress

if TYPE_CHECKING:
    from mgost.mgost import MGost

    from .api import ArtichaAPI


@dataclass(frozen=True, slots=True)
class Action(ABC):
    pass


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
    project_id: int
    path: Path


@dataclass(frozen=True, slots=True)
class MoveAction(PathAction, ABC):
    new_path: Path


@dataclass(frozen=True, slots=True)
class DoNothing(APICompletableAction):
    async def complete_api(self, api, progress=None):
        from asyncio import sleep
        from random import random
        await sleep(random())


@dataclass(frozen=True, slots=True)
class UploadFileAction(APICompletableAction, PathAction):
    overwrite: bool

    async def complete_api(self, api, progress=None):
        await api.upload(
            project_id=self.project_id,
            path=self.path,
            overwrite=self.overwrite,
            progress=progress
        )


@dataclass(frozen=True, slots=True)
class DownloadFileAction(APICompletableAction, PathAction):
    overwrite_ok: bool

    async def complete_api(self, api, progress=None):
        await api.download(
            project_id=self.project_id,
            path=self.path,
            overwrite_ok=self.overwrite_ok,
            progress=progress
        )


@dataclass(frozen=True, slots=True)
class FileMovedLocally(APICompletableAction, MoveAction):
    async def complete_api(self, api, progress=None):
        project_files = await api.project_files(
            self.project_id
        )
        if self.path in project_files:
            await api.move_on_cloud(
                project_id=self.project_id,
                old_path=self.path,
                new_path=self.new_path
            )
        else:
            await api.upload(
                self.project_id,
                path=self.new_path,
                overwrite=False,
                progress=progress
            )


@dataclass(frozen=True, slots=True)
class FileSync(MGostCompletableAction, PathAction):
    async def complete_mgost(self, mgost, progress=None) -> Action:
        return await mgost.sync_file(self.project_id, self.path)
