from collections.abc import Iterable
from datetime import datetime
from json import JSONDecodeError
from os import utime
from pathlib import Path
from time import sleep
from typing import Generator, Literal, NamedTuple

from httpx import Client, QueryParams, Response
from httpx._types import RequestFiles
from rich.progress import (
    BarColumn, DownloadColumn, Progress, TransferSpeedColumn
)

from . import schemas

CURRENT_TIMEZONE = datetime.now().astimezone().tzinfo


class WrongToken(Exception):
    pass


class ClientClosed(Exception):
    pass


class ProgressInfo(NamedTuple):
    num_bytes_downloaded: float
    chunk: bytes


class StreamingDownload(Iterable):
    __slots__ = ('_resp', 'total')
    _resp: Response
    total: int | None

    def __init__(self, response: Response) -> None:
        super().__init__()
        assert isinstance(response, Response)
        self._resp = response
        total = response.headers.get('Content-Length', None)
        self.total = int(total) if total else None

    def __iter__(self) -> Generator[ProgressInfo]:
        for chunk in self._resp.iter_bytes():
            yield ProgressInfo(
                self._resp.num_bytes_downloaded,
                chunk
            )


class APIRequestError(Exception):
    __slots__ = (
        'response',
        'detail',
    )
    response: Response
    detail_: str

    def __init__(
        self,
        response: Response,
        detail: str
    ) -> None:
        super().__init__()
        assert isinstance(response, Response)
        assert isinstance(detail, str)
        self.response = response
        self.detail = detail


class ArtichaAPI:
    __slots__ = (
        '_token',
        '_client',
        '_cache',
    )
    _host: str = 'https://articha.tplinkdns.com/api'
    _token: str
    _client: Client | None
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
        if base_url is None:
            base_url = self._host
        assert isinstance(api_token, str)
        assert isinstance(base_url, str)
        self._token = api_token
        self._client = Client(
            headers={
                'X-API-Key': self._token
            },
            base_url=base_url
        )
        self._cache = dict()

    def _method(
        self,
        method: str,
        url: str,
        params: QueryParams | dict | None = None,
        files: RequestFiles | dict | None = None
    ) -> Response:
        assert url.startswith('/')
        assert isinstance(url, str)
        key = (method, url, params, files)
        if (value := self._cache.get(key)) is not None:
            return value
        if params is None:
            params = QueryParams()
        assert isinstance(params, (dict, QueryParams))
        if self._client is None:
            raise ClientClosed(f"{self.__qualname__} is closed")
        resp = self._client.request(
            method, url,
            params=params,
            files=files
        )
        counter = 0
        while resp.status_code == 429:
            sleep(5)
            resp = self._client.request(
                method, url,
                params=params,
                files=files
            )
            counter += 1
            if counter > 2:
                return resp
        try:
            info = resp.json()
            if 'detail' in info:
                raise APIRequestError(
                    resp, info['detail']
                )
        except JSONDecodeError:
            pass
        self._cache[key] = resp
        return resp

    def _streaming_download(
        self,
        method: str,
        url: str,
        params: QueryParams | dict | None = None,
        files: RequestFiles | dict | None = None
    ) -> StreamingDownload:
        assert url.startswith('/')
        assert isinstance(url, str)
        if params is None:
            params = QueryParams()
        assert isinstance(params, (dict, QueryParams))
        if self._client is None:
            raise ClientClosed(f"{self.__qualname__} is closed")
        with self._client.stream(
            method, url,
            params=params,
            files=files
        ) as resp:
            return StreamingDownload(resp)

    def _get(
        self, url: str,
        params: QueryParams | dict | None = None,
        files: RequestFiles | dict | None = None
    ) -> Response:
        return self._method('GET', url, params, files)

    def _put(
        self, url: str,
        params: QueryParams | dict | None = None,
        files: RequestFiles | dict | None = None,
    ) -> Response:
        return self._method('PUT', url, params, files)

    def _post(
        self, url: str,
        params: QueryParams | dict | None = None,
        files: RequestFiles | dict | None = None,
    ) -> Response:
        return self._method('POST', url, params, files)

    def _patch(
        self, url: str,
        params: QueryParams | dict | None = None,
        files: RequestFiles | dict | None = None,
    ) -> Response:
        return self._method('PATCH', url, params, files)

    def _invalidate_cache(self) -> None:
        self._cache.clear()

    def validate_token(self) -> str | schemas.TokenInfo:
        resp = self._get('/me')
        info = resp.json()
        if resp.status_code != 200:
            assert 'detail' in info
            return info['detail']
        return schemas.TokenInfo(**info)

    def me(self) -> schemas.TokenInfo:
        return schemas.TokenInfo(**self._get('/me').json())

    def trust(self) -> int:
        return self._get('/trust').json()['trust']

    def trust_factors(self) -> dict[str, int]:
        return self._get('/trust/factors').json()

    def download_example(
        self,
        name: str = 'init',
        type: Literal['md', 'docx'] = 'md'
    ) -> bytes:
        return self._get(
            '/mgost/examples',
            {
                'name': name,
                'type': type
            }
        ).read()

    def is_project_available(self, project_id: int) -> bool:
        assert isinstance(project_id, int)
        try:
            response = self._get(
                f'/mgost/project/{project_id}'
            )
            return response.status_code == 200
        except APIRequestError:
            return False

    def projects(self) -> list[schemas.Project]:
        return [
            schemas.Project(**i) for i in self._get(
                '/mgost/project'
            ).json()
        ]

    def project(self, project_id: int) -> schemas.ProjectExtended:
        assert isinstance(project_id, int)
        assert self.is_project_available(project_id)
        return schemas.ProjectExtended(
            **self._get(
                f'/mgost/project/{project_id}'
            ).json(),
        )

    def project_files_requirements(
        self, project_id
    ) -> dict[str, schemas.FileRequirement]:
        return {
            k: schemas.FileRequirement(**v) for k, v in self._get(
                f'/mgost/project/{project_id}/requirements'
            ).json().items()
        }

    def project_files(
        self, project_id: int
    ) -> dict[Path, schemas.ProjectFile]:
        assert isinstance(project_id, int)
        return {
            Path(i['path']): schemas.ProjectFile(**i) for i in self._get(
                f'/mgost/project/{project_id}/files'
            ).json()
        }

    def create_project(self, name: str) -> int:
        assert isinstance(name, str)
        output = self._put(
            '/mgost/project',
            {'project_name': name}
        ).json()
        self._invalidate_cache()
        return output['id']

    def upload(
        self,
        project_id: int,
        path: Path,
        overwrite: bool
    ) -> None:
        assert isinstance(project_id, int)
        assert isinstance(path, Path)
        assert isinstance(overwrite, bool)
        if not (path.exists() and path.is_file()):
            raise FileNotFoundError
        with path.open('rb') as file:
            files = {'file': file}
            params: dict = {
                'project_id': project_id,
                'modify_time': datetime.fromtimestamp(
                    path.lstat().st_mtime, CURRENT_TIMEZONE
                )
            }
            if overwrite:
                self._post(
                    f'/mgost/project/{project_id}/files/{path}',
                    params=params, files=files
                )
            else:
                params['path'] = path
                self._put(
                    f'/mgost/project/{project_id}/files',
                    params=params, files=files
                )
        self._invalidate_cache()

    def download(
        self,
        project_id: int,
        path: Path,
        overwrite_ok: bool = True
    ) -> None:
        assert isinstance(project_id, int)
        assert isinstance(path, Path)
        assert isinstance(overwrite_ok, bool)
        if path.exists() and not overwrite_ok:
            raise FileExistsError
        with open(path, 'wb') as file:
            resp = self._get(
                f'/mgost/project/{project_id}/files/{path}',
            )
            file.write(resp.content)
        access_time = path.lstat().st_atime
        project_file = self.project_files(project_id)[path]
        utime(path, (access_time, project_file.modified.timestamp()))

    def download_with_progress(
        self,
        project_id: int,
        path: Path,
        overwrite_ok: bool = True
    ):
        assert isinstance(project_id, int)
        assert isinstance(path, Path)
        assert isinstance(overwrite_ok, bool)
        if path.exists() and not overwrite_ok:
            raise FileExistsError
        with Progress(
            "[progress.percentage]{task.percentage:>3.0f}%",
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
        ) as progress:
            streaming_download = self._streaming_download(
                'GET', f'/mgost/project/{project_id}/files/{path}',
            )
            download_task = progress.add_task(
                str(path),
                total=streaming_download.total
            )
            for chunk_info in streaming_download:
                progress.update(
                    download_task,
                    completed=chunk_info.num_bytes_downloaded
                )
        access_time = path.lstat().st_atime
        project_file = self.project_files(project_id)[path]
        utime(path, (access_time, project_file.modified.timestamp()))

    def move_on_cloud(
        self,
        project_id: int,
        old_path: Path,
        new_path: Path
    ) -> bool:
        resp = self._patch(
            f'/mgost/project/{project_id}/files/{old_path}',
            {'target': new_path}
        )
        self._invalidate_cache()
        return schemas.Message(**resp.json()).is_ok()

    def render(
        self,
        project_id: int
    ) -> schemas.mgost.BuildResult:
        """Requests api to render project
        :raises HTTPStatusError: Raised when got non-success code from the api
        """
        resp = self._get(
            f'/mgost/project/{project_id}/render'
        )
        resp.raise_for_status()
        self._invalidate_cache()
        return schemas.mgost.BuildResult(**resp.json())

    def close(self) -> None:
        if self._client is None:
            raise ClientClosed(f"{self.__qualname__} is closed")
        self._client.close()
        self._client = None
