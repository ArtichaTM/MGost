from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True, frozen=True)
class Action:
    path: Path


@dataclass(slots=True, frozen=True)
class DeleteAction(Action):
    pass


@dataclass(slots=True, frozen=True)
class _UploadAction(Action):
    modified: datetime | None
    size: int


@dataclass(slots=True, frozen=True)
class OverwriteAction(_UploadAction):
    pass


@dataclass(slots=True, frozen=True)
class NewFileAction(_UploadAction):
    pass


@dataclass(slots=True, frozen=True)
class DownloadAction(Action):
    target: Path


@dataclass(slots=True, frozen=True)
class Move(Action):
    target: Path
