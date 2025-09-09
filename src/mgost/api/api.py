from datetime import datetime
from functools import cache
from json import JSONDecodeError
from os import utime
from pathlib import Path
from typing import Literal

from httpx import Client, QueryParams, Response
from httpx._types import RequestFiles

from . import schemas

CURRENT_TIMEZONE = datetime.now().astimezone().tzinfo


class WrongToken(Exception):
    pass


class ClientClosed(Exception):
    pass


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
        '_client'
    )
    _host: str = 'https://articha.tplinkdns.com/api'
    _token: str
    _client: Client | None

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

    def _method(
        self,
        method: str,
        url: str,
        params: QueryParams | dict | None = None,
        files: RequestFiles | dict | None = None
    ) -> Response:
        assert url.startswith('/')
        assert isinstance(url, str)
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
        try:
            info = resp.json()
            if 'detail' in info:
                raise APIRequestError(
                    resp, info['detail']
                )
        except JSONDecodeError:
            pass
        return resp

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

    @cache
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

    @cache
    def project(self, project_id: int) -> schemas.ProjectExtended:
        assert isinstance(project_id, int)
        assert self.is_project_available(project_id)
        return schemas.ProjectExtended(
            **self._get(f'/mgost/project/{project_id}').json()
        )

    def project_files_requirements(
        self, project_id
    ) -> dict[str, schemas.FileRequirement]:
        return {
            k: schemas.FileRequirement(**v) for k, v in self._get(
                f'/mgost/project/{project_id}/requirements'
            ).json().items()
        }

    @cache
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

    def download(
        self,
        project_id: int,
        path: Path,
        overwrite_ok: bool = True
    ) -> None:
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
        return schemas.Message(**resp.json()).is_ok()

    def invalidate_cache(self) -> None:
        for attr in self.__dict__.values():
            if hasattr(attr, 'cache_clear'):
                attr.cache_clear()

    def close(self) -> None:
        if self._client is None:
            raise ClientClosed(f"{self.__qualname__} is closed")
        self._client.close()
        self._client = None
