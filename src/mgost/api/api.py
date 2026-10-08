from datetime import datetime, timezone
from os import replace, utime
from pathlib import Path
from typing import Awaitable, Literal

from aiopath import AsyncPath
from httpx import AsyncClient, ConnectError, HTTPStatusError, Response
from rich.progress import Progress

from . import schemas
from .caller import api_request
from .exceptions import ClientClosed
from .request import APIRequestInfo


class ArtichaAPI:
    __slots__ = (
        '_token',
        '_client',
        '_cache',
        '_base_url',
    )
    _host: str = 'https://articha.ru/api'
    RENDER_TIMEOUT: float = 300.
    _base_url: str
    _token: str
    _client: AsyncClient | None
    _cache: dict[tuple[str, str, tuple[tuple[str, str], ...]], Response]

    def __init__(
        self,
        api_token: str,
        /,
        base_url: str | None = None
    ) -> None:
        assert isinstance(api_token, str)
        assert base_url is None or isinstance(base_url, str)
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
        assert isinstance(request, APIRequestInfo)
        assert self._client is not None
        # Server error `detail` strings should match the language the
        # rest of the CLI speaks.
        params = request.params
        if params is None:
            params = {'lang': 'ru'}
        elif isinstance(params, dict):
            params = {**params, 'lang': 'ru'}
        else:
            params = params.merge({'lang': 'ru'})
        request.params = params
        return api_request(
            client=self._client,
            cache=self._cache,
            request=request
        )

    def _invalidate_cache(self) -> None:
        self._cache.clear()

    @staticmethod
    def _path_to_url(path: Path) -> str:
        return str(path).replace('\\', '/')

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
        except ConnectError as e:
            if e.args[0] == 'All connection attempts failed':
                raise TimeoutError
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
        assert isinstance(name, str)
        assert type in {'md', 'docx'}
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
        self, project_id: int
    ) -> list[schemas.FileRequirement]:
        assert isinstance(project_id, int)
        resp = await self.method(APIRequestInfo(
            'GET', f'/mgost/project/{project_id}/requirements'
        ))
        return [schemas.FileRequirement(**i) for i in resp.json()]

    async def _files(self, project_id: int) -> list[schemas.ProjectFile]:
        assert isinstance(project_id, int)
        resp = await self.method(APIRequestInfo(
            'GET', f'/mgost/project/{project_id}/files'
        ))
        return [schemas.ProjectFile(**i) for i in resp.json()]

    async def project_files(
        self, project_id: int
    ) -> dict[Path, schemas.ProjectFile]:
        """Files inside the project, by root-relative path"""
        return {
            Path(i.path): i
            for i in await self._files(project_id) if not i.fictional
        }

    async def fictional_files(
        self, project_id: int
    ) -> dict[int, schemas.ProjectFile]:
        """Files uploaded under a path outside the project, by id"""
        return {
            i.id: i for i in await self._files(project_id) if i.fictional
        }

    async def create_project(self, name: str) -> int:
        assert isinstance(name, str)
        resp = await self.method(APIRequestInfo(
            method='PUT',
            url='/mgost/project',
            params={'project_name': name}
        ))
        self._invalidate_cache()
        return resp.json()['id']

    async def upload(
        self,
        project_id: int,
        local_path: Path,
        remote_path: str,
        file_id: int | None,
        progress: Progress | None = None
    ) -> None:
        """POSTs a new file under `remote_path`, or PUTs over `file_id`"""
        assert isinstance(project_id, int)
        assert local_path.is_absolute()
        assert isinstance(remote_path, str)
        assert file_id is None or isinstance(file_id, int)
        if not local_path.is_file():
            raise FileNotFoundError
        params: dict = {
            'modify_time': datetime.fromtimestamp(
                local_path.lstat().st_mtime, timezone.utc
            ).isoformat()
        }
        files_url = f'/mgost/project/{project_id}/files'

        def send(method: str, url: str, params: dict) -> Awaitable[Response]:
            return self.method(APIRequestInfo(
                method, url,
                params=params,
                label=remote_path,
                request_file_path=AsyncPath(local_path),
                progress=progress
            ))

        if file_id is not None:
            await send('PUT', f'{files_url}/{file_id}', params)
            self._invalidate_cache()
            return
        try:
            await send('POST', files_url, {**params, 'path': remote_path})
        except HTTPStatusError as e:
            if e.response.status_code != 409:
                raise
            # Created on the server after our listing: overwrite it instead
            self._invalidate_cache()
            existing = next((
                i for i in await self._files(project_id)
                if i.path == remote_path
            ), None)
            if existing is None:
                raise
            await send('PUT', f'{files_url}/{existing.id}', params)
        self._invalidate_cache()

    async def download(
        self,
        project_id: int,
        file_id: int,
        root_path: Path,
        path: Path,
        overwrite_ok: bool = True,
        progress: Progress | None = None
    ) -> None:
        assert isinstance(project_id, int)
        assert isinstance(file_id, int)
        assert isinstance(root_path, Path)
        assert isinstance(path, Path)
        assert not path.is_absolute()
        assert isinstance(overwrite_ok, bool)
        full_path = root_path / path
        temp_path = full_path.parent / f'.{full_path.name}.mgost-tmp'
        full_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            resp = await self.method(APIRequestInfo(
                'GET', f'/mgost/project/{project_id}/files/{file_id}',
                label=self._path_to_url(path),
                response_file_path=AsyncPath(full_path),
                progress=progress
            ))
            resp.raise_for_status()
            if full_path.exists() and not overwrite_ok:
                # A stale action: something arrived while we downloaded.
                # Losing the download beats losing the user's file.
                return
            replace(temp_path, full_path)
        finally:
            temp_path.unlink(missing_ok=True)
        access_time = full_path.lstat().st_atime
        files = await self._files(project_id)
        project_file = next(i for i in files if i.id == file_id)
        utime(full_path, (access_time, project_file.modified.timestamp()))

    async def move_on_cloud(
        self,
        project_id: int,
        file_id: int,
        new_path: Path
    ) -> bool:
        assert isinstance(file_id, int)
        assert not new_path.is_absolute()
        resp = await self.method(APIRequestInfo(
            method='PATCH',
            url=f'/mgost/project/{project_id}/files/{file_id}',
            params={'target': self._path_to_url(new_path)}
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
            'GET', f'/mgost/project/{project_id}/render',
            timeout=self.RENDER_TIMEOUT
        ))
        resp.raise_for_status()
        self._invalidate_cache()
        return schemas.mgost.BuildResult(**resp.json())
