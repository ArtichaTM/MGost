from datetime import datetime
from os import utime
from pathlib import Path
from typing import Awaitable, Literal

from aiopath import AsyncPath
from httpx import (
    AsyncClient, ConnectError, HTTPStatusError, QueryParams, Response
)
from httpx._types import RequestFiles
from rich.progress import Progress

from . import schemas
from .caller import api_request
from .exceptions import ClientClosed
from .request import APIRequestInfo

CURRENT_TIMEZONE = datetime.now().astimezone().tzinfo


class ArtichaAPI:
    __slots__ = (
        '_token',
        '_client',
        '_cache',
        '_base_url',
    )
    _host: str = 'https://articha.ru/api'
    _base_url: str
    _token: str
    _client: AsyncClient | None
    _cache: dict[tuple[
        str,
        str,
        QueryParams | dict | None,
        RequestFiles | dict | None
    ], Response]

    def __init__(
        self,
        api_token: str,
        /,
        base_url: str | None = None
    ) -> None:
        assert base_url is None or isinstance(base_url, str)
        assert isinstance(api_token, str)
        if base_url is None:
            base_url = self._host
        assert base_url is not None
        self._base_url = base_url
        self._token = api_token
        self._cache = dict()
        self._client = None

    async def __aenter__[T: ArtichaAPI](self: T) -> T:
        assert self._base_url is not None
        assert self._client is None
        await self._client_refresh()
        return self

    async def __aexit__(self, *args) -> None:
        assert isinstance(self._client, AsyncClient)
        if self._client is None:
            raise ClientClosed(f"{self.__qualname__} is closed")
        await self._client.__aexit__()
        self._client = None

    async def _client_refresh(self) -> None:
        if self._client is not None:
            await self._client.__aexit__()
        self._client = AsyncClient(
            headers={
                'X-API-Key': self._token
            },
            base_url=self._base_url
        )
        await self._client.__aenter__()

    def method(
        self, request: APIRequestInfo
    ) -> Awaitable[Response]:
        assert self._client is not None
        return api_request(
            client=self._client,
            cache=self._cache,
            request=request
        )

    def _invalidate_cache(self) -> None:
        self._cache.clear()

    async def validate_token(self) -> str | schemas.TokenInfo:
        await self._client_refresh()
        try:
            resp = await self.method(APIRequestInfo(
                'GET', '/me'
            ))
            return schemas.TokenInfo(**resp.json())
        except HTTPStatusError as e:
            resp = e.response
            info = resp.json()
            assert 'detail' in info
            return info['detail']
        except ConnectError:
            return "Ошибка подключения: сайт недоступен"

    async def me(self) -> schemas.TokenInfo:
        return schemas.TokenInfo(**(await self.method(APIRequestInfo(
            'GET', '/me'
        ))).json())

    async def trust(self) -> int:
        return (await self.method(APIRequestInfo(
            'GET', '/trust'
        ))).json()['trust']

    async def trust_factors(self) -> dict[str, int]:
        return (await self.method(APIRequestInfo(
            'GET', '/trust/factors'
        ))).json()

    async def download_example(
        self,
        name: str = 'init',
        type: Literal['md', 'docx'] = 'md'
    ) -> bytes:
        resp = await self.method(APIRequestInfo(
            'GET', '/mgost/examples',
            {
                'name': name,
                'type': type
            }
        ))
        return resp.read()

    async def is_project_available(self, project_id: int) -> bool:
        assert isinstance(project_id, int)
        try:
            response = await self.method(APIRequestInfo(
                'GET', f'/mgost/project/{project_id}'
            ))
            return response.status_code == 200
        except HTTPStatusError:
            return False

    async def projects(self) -> list[schemas.Project]:
        resp = await self.method(APIRequestInfo(
            'GET', '/mgost/project'
        ))
        return [
            schemas.Project(**i) for i in resp.json()
        ]

    async def project(self, project_id: int) -> schemas.ProjectExtended:
        assert isinstance(project_id, int)
        assert await self.is_project_available(project_id)
        resp = await self.method(APIRequestInfo(
            'GET', f'/mgost/project/{project_id}'
        ))
        return schemas.ProjectExtended(
            **resp.json(),
        )

    async def project_requirements(
        self, project_id
    ) -> dict[str, schemas.FileRequirement]:
        resp = await self.method(APIRequestInfo(
            'GET', f'/mgost/project/{project_id}/requirements'
        ))
        return {
            k: schemas.FileRequirement(
                **v
            ) for k, v in resp.json().items()
        }

    async def project_files(
        self, project_id: int
    ) -> dict[Path, schemas.ProjectFile]:
        assert isinstance(project_id, int)
        resp = await self.method(APIRequestInfo(
            'GET', f'/mgost/project/{project_id}/files'
        ))
        return {
            Path(i['path']): schemas.ProjectFile(**i) for i in resp.json()
        }

    async def create_project(self, name: str) -> int:
        assert isinstance(name, str)
        resp = await self.method(APIRequestInfo(
            'GET', '/mgost/project',
            {'project_name': name}
        ))
        self._invalidate_cache()
        return resp.json()['id']

    async def upload(
        self,
        project_id: int,
        path: Path,
        overwrite: bool,
        progress: Progress | None = None
    ) -> None:
        assert isinstance(project_id, int)
        assert isinstance(path, Path)
        assert isinstance(overwrite, bool)
        if not (path.exists() and path.is_file()):
            raise FileNotFoundError
        params: dict = {
            'project_id': project_id,
            'modify_time': datetime.fromtimestamp(
                path.lstat().st_mtime, CURRENT_TIMEZONE
            )
        }
        if overwrite:
            await self.method(APIRequestInfo(
                'POST',
                f'/mgost/project/{project_id}/files/{path}',
                params=params,
                request_file_path=AsyncPath(path),
                progress=progress
            ))
        else:
            params['path'] = path
            await self.method(APIRequestInfo(
                'PUT',
                f'/mgost/project/{project_id}/files/{path}',
                params=params,
                request_file_path=AsyncPath(path),
                progress=progress
            ))
        self._invalidate_cache()

    async def download(
        self,
        project_id: int,
        path: Path,
        overwrite_ok: bool = True,
        progress: Progress | None = None
    ) -> None:
        assert isinstance(project_id, int)
        assert isinstance(path, Path)
        assert isinstance(overwrite_ok, bool)
        resp = await self.method(APIRequestInfo(
            'GET', f'/mgost/project/{project_id}/files/{path}',
            response_file_path=AsyncPath(path),
            progress=progress
        ))
        resp.raise_for_status()
        access_time = path.lstat().st_atime
        project_files = await self.project_files(project_id)
        project_file = project_files[path]
        utime(path, (access_time, project_file.modified.timestamp()))

    async def move_on_cloud(
        self,
        project_id: int,
        old_path: Path,
        new_path: Path
    ) -> bool:
        resp = await self.method(APIRequestInfo(
            'PATCH',
            f'/mgost/project/{project_id}/files/{old_path}',
            {'target': new_path}
        ))
        self._invalidate_cache()
        return schemas.Message(**resp.json()).is_ok()

    async def render(
        self,
        project_id: int
    ) -> schemas.mgost.BuildResult:
        """Requests api to render project
        :raises HTTPStatusError: Raised when got non-success code from the api
        """
        resp = await self.method(APIRequestInfo(
            'GET', f'/mgost/project/{project_id}/render'
        ))
        resp.raise_for_status()
        self._invalidate_cache()
        return schemas.mgost.BuildResult(**resp.json())
