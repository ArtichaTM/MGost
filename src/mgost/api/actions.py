from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mgost.mgost import MGost

    from .api import ArtichaAPI


@dataclass(frozen=True, slots=True)
class Action(ABC):
    pass


@dataclass(frozen=True, slots=True)
class MGostCompletableAction(Action, ABC):
    @abstractmethod
    def complete_mgost(self, mgost: 'MGost') -> Action | None:
        raise NotImplementedError()


@dataclass(frozen=True, slots=True)
class APICompletableAction(MGostCompletableAction, ABC):
    def complete_mgost(self, mgost: 'MGost') -> Action | None:
        return self.complete_api(mgost.api)

    @abstractmethod
    def complete_api(self, api: 'ArtichaAPI') -> Action | None:
        raise NotImplementedError()


@dataclass(frozen=True, slots=True)
class PathAction(Action, ABC):
    project_id: int
    path: Path


@dataclass(frozen=True, slots=True)
class DoNothing(APICompletableAction):
    def complete_api(self, api):
        pass


@dataclass(frozen=True, slots=True)
class UploadFileAction(PathAction, APICompletableAction):
    overwrite: bool

    def complete_api(self, api):
        api.upload(
            project_id=self.project_id,
            path=self.path,
            overwrite=self.overwrite
        )


@dataclass(frozen=True, slots=True)
class DownloadFileAction(PathAction, APICompletableAction):
    overwrite_ok: bool

    def complete_api(self, api):
        api.download(
            project_id=self.project_id,
            path=self.path,
            overwrite_ok=self.overwrite_ok
        )


@dataclass(frozen=True, slots=True)
class FileMovedLocally(PathAction, APICompletableAction):
    new_path: Path

    def complete_api(self, api):
        api.move_on_cloud(
            project_id=self.project_id,
            old_path=self.path,
            new_path=self.new_path
        )


@dataclass(frozen=True, slots=True)
class FileSync(PathAction, MGostCompletableAction):
    def complete_mgost(self, mgost) -> Action:
        return mgost.sync_file(self.project_id, self.path)
