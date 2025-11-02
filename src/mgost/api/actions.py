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
class DoNothing(APICompletableAction):
    async def complete_api(self, api, progress=None):
        pass


@dataclass(frozen=True, slots=True)
class UploadFileAction(PathAction, APICompletableAction):
    overwrite: bool

    async def complete_api(self, api, progress=None):
        await api.upload(
            project_id=self.project_id,
            path=self.path,
            overwrite=self.overwrite,
            progress=progress
        )


@dataclass(frozen=True, slots=True)
class DownloadFileAction(PathAction, APICompletableAction):
    overwrite_ok: bool

    async def complete_api(self, api, progress=None):
        await api.download(
            project_id=self.project_id,
            path=self.path,
            overwrite_ok=self.overwrite_ok,
            progress=progress
        )


@dataclass(frozen=True, slots=True)
class FileMovedLocally(PathAction, APICompletableAction):
    new_path: Path

    async def complete_api(self, api, progress=None):
        await api.move_on_cloud(
            project_id=self.project_id,
            old_path=self.path,
            new_path=self.new_path
        )


@dataclass(frozen=True, slots=True)
class FileSync(PathAction, MGostCompletableAction):
    async def complete_mgost(self, mgost, progress=None) -> Action:
        return await mgost.sync_file(self.project_id, self.path)
