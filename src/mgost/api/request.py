from dataclasses import dataclass

from aiopath import AsyncPath
from httpx import QueryParams
from rich.progress import Progress


@dataclass(slots=True, match_args=False)
class APIRequestInfo:
    method: str
    url: str
    params: QueryParams | dict | None = None
    progress: Progress | None = None
    request_file_path: AsyncPath | None = None
    response_file_path: AsyncPath | None = None

    def with_progress(self) -> bool:
        return self.progress is not None
