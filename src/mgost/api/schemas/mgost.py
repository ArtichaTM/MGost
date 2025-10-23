from datetime import datetime
from logging import ERROR, INFO
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Project(BaseModel):
    name: str
    id: int
    created: datetime
    modified: datetime


class ProjectFile(BaseModel):
    project_id: int
    path: str
    created: datetime
    modified: datetime
    size: int


class ProjectExtended(Project):
    path_to_markdown: Path
    path_to_docx: Path
    files: list[ProjectFile]


class ProjectFileUploadInfo(BaseModel):
    filename: str
    path: str


class ProjectBuildHistoryEntry(BaseModel):
    project: Optional[int]
    date: datetime
    maximum_status_code: int


class Message(BaseModel):
    message: str = Field(default='ok')

    def is_ok(self) -> bool:
        return self.message == 'ok'


class ErrorMessage(Message):
    code: int = Field(default=400)


class ListParameters(BaseModel):
    limit: int = Field(10, gt=1, le=100)
    offset: int = Field(0, ge=0)


class FileRequirement(BaseModel):
    path: str


class FileRename(BaseModel):
    source_path: Path = Field(
        description='Source file path',
    )
    target: Path = Field(
        ...,
        description="File target path"
    )


class LogEntry(BaseModel):
    level: int = Field(
        description=f"Level of log from {INFO} to {ERROR}"
    )
    message: str


class BuildResult(BaseModel):
    max_log_level: int = Field(
        description=(
            "Max level of logs during render."
            f"By default minimum is {INFO} and maximum is {ERROR}"
        )
    )
    logs: list[LogEntry]
    finished: bool
