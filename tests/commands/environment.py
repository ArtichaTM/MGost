from dataclasses import dataclass, field
from datetime import datetime, timedelta
from os import utime
from pathlib import Path
from random import randbytes
from tempfile import TemporaryDirectory
from typing import Iterable, TypedDict

import respx
from httpx import Request, Response

from mgost.api.schemas.mgost import (
    BuildResult, ErrorMessage, Message, Project, ProjectExtended, ProjectFile
)


class APIFileInfo(TypedDict):
    path: str


@dataclass(slots=True, frozen=False)
class Routes:
    _projects: respx.Route | None = None
    _project: respx.Route | None = None
    _project_files: respx.Route | None = None
    _project_render: respx.Route | None = None
    file_put: dict[str, respx.Route] = field(default_factory=dict)
    file_post: dict[str, respx.Route] = field(default_factory=dict)
    file_patch: dict[str, respx.Route] = field(default_factory=dict)
    file_delete: dict[str, respx.Route] = field(default_factory=dict)
    file_get: dict[str, respx.Route] = field(default_factory=dict)

    @property
    def projects(self) -> respx.Route:
        assert self._projects is not None
        return self._projects

    @property
    def project(self) -> respx.Route:
        assert self._project is not None
        return self._project

    @property
    def project_files(self) -> respx.Route:
        assert self._project_files is not None
        return self._project_files

    @property
    def project_render(self) -> respx.Route:
        assert self._project_render is not None
        return self._project_render


class EnvironmentHelper:
    __slots__ = (
        'respx_mock',
        'project',
        'local_files',
        'temp_dir_local',
        'routes',
    )
    respx_mock: respx.MockRouter
    project: ProjectExtended
    local_files: dict[Path, ProjectFile]
    temp_dir_local: TemporaryDirectory | None
    routes: Routes

    def __init__(
        self,
        respx_mock: respx.MockRouter,
        project: ProjectExtended,
        local_files: Iterable[ProjectFile],
        requirements: dict[str, APIFileInfo],
    ) -> None:
        assert isinstance(respx_mock, respx.MockRouter)
        assert project is None or isinstance(project, ProjectExtended)
        assert isinstance(requirements, dict)
        assert all((isinstance(r, str) for r in requirements.keys()))
        assert all((isinstance(r, str) for r in requirements.values()))
        self.respx_mock = respx_mock
        self.project = project
        self.local_files = {Path(f.path): f for f in local_files}
        assert len({
            f.size for f in self.local_files.values()
        }) == len(self.local_files)
        self.routes = Routes()
        assert isinstance(self.routes.file_patch, dict)
        self.temp_dir_local = None

    async def __aenter__(self) -> None:
        assert self.temp_dir_local is None
        self.temp_dir_local = TemporaryDirectory(delete=True)
        self.temp_dir_local.__enter__()
        await self.prepare_environment()

    async def __aexit__(self, exc, value, tb) -> None:
        assert self.temp_dir_local is not None
        self.temp_dir_local.__exit__(exc, value, tb)
        self.temp_dir_local = None

    def _file_path_from_url(
        self,
        url: str,
    ) -> str:
        anchor = '/files/'
        index = url.find(anchor)
        assert index != -1
        index = index + len(anchor)
        assert index < len(url)
        return url[index:]

    def _file_from_url(
        self,
        url: str,
    ) -> ProjectFile | None:
        path = self._file_path_from_url(url)
        for file in self.project.files:
            if file.path == path:
                return file

    async def put_file_existing(self, request: Request) -> Response:
        return Response(status_code=409, json=ErrorMessage(
            message='ProjectFile with this path already exists'
        ))

    async def post_file_existing(self, request: Request) -> Response:
        file = self._file_from_url(request.url.path)
        assert file
        modify_time = request.url.params.get('modify_time', datetime.now())
        file.modified = modify_time
        file.size = len(request.read())
        return Response(
            status_code=200,
            json=Message().model_dump(mode='json')
        )

    async def patch_file_existing(self, request: Request) -> Response:
        file = self._file_from_url(request.url.path)
        assert file
        assert 'target' in request.url.params
        target = request.url.params['target']
        file.path = target
        return Response(
            status_code=200,
            json=Message().model_dump(mode='json')
        )

    async def delete_file_existing(self, request: Request) -> Response:
        path = self._file_path_from_url(request.url.path)
        assert path
        found = False
        _i = None
        for _i, file in enumerate(self.project.files):
            if file.path == path:
                found = True
                break
        assert _i is not None
        assert found
        self.project.files.pop(_i)
        return Response(
            status_code=200,
            json=Message().model_dump(mode='json')
        )

    async def get_file_existing(self, request: Request) -> Response:
        file = self._file_from_url(request.url.path)
        assert file
        return Response(status_code=200, content=randbytes(file.size))

    async def project_render(self, request: Request) -> Response:
        p = 'output.docx'
        existing_file = self._file_from_url(p)
        if existing_file:
            existing_file.modified = datetime.now()
        else:
            self.project.files.append(ProjectFile(
                project_id=self.project.id,
                path=p,
                created=datetime.now(),
                modified=datetime.now(),
                size=1
            ))
        return Response(
            status_code=200,
            json=BuildResult(
                max_log_level=0,
                finished=True,
                logs=[]
            )
        )

    async def prepare_environment(self) -> None:
        assert self.temp_dir_local is not None
        root_folder = Path(self.temp_dir_local.name)

        for local_file in self.local_files.values():
            file_path = root_folder / local_file.path
            file_path.touch(exist_ok=False)
            utime(file_path, (
                local_file.created.timestamp(),
                local_file.modified.timestamp()
            ))

        self.routes._projects = self.respx_mock.get(
            "/mgost/project"
        ).respond(status_code=200, json=[
            Project(
                name=self.project.name,
                id=self.project.id,
                created=self.project.created,
                modified=self.project.modified
            ).model_dump(mode='json')
        ])
        self.routes._project = self.respx_mock.get(
            f"/mgost/project/{self.project.id}"
        ).respond(status_code=200, json=self.project.model_dump(mode='json'))
        self.routes._project_files = self.respx_mock.get(
            f"/mgost/project/{self.project.id}/files"
        ).respond(status_code=200, json=[
            ProjectFile(
                project_id=self.project.id,
                path=str(cloud_file.path),
                created=cloud_file.created,
                modified=cloud_file.modified,
                size=cloud_file.size
            ).model_dump(mode='json') for cloud_file in self.project.files
        ])
        self.routes._project_render = self.respx_mock.get(
            f"/mgost/project/{self.project.id}/render"
        ).mock(side_effect=self.project_render)
        for cloud_file in self.project.files:
            for method in {'PUT', 'POST', 'PATCH', 'DELETE', 'GET'}:
                routes_dict = getattr(self.routes, f"file_{method.lower()}")
                side_effect_method = getattr(
                    self,
                    f"{method.lower()}_file_existing"
                )
                routes_dict[cloud_file.path] = self.respx_mock.request(
                    method,
                    f"/mgost/project/{self.project.id}/files/{cloud_file.path}"
                ).mock(side_effect=side_effect_method)


def create_simple_environment(
    respx_mock: respx.MockRouter
) -> EnvironmentHelper:
    project_id = 1
    now = datetime.now()
    second_ago = now - timedelta(seconds=1)
    project_files = [
        ProjectFile(
            project_id=project_id,
            path='main.md',
            created=second_ago,
            modified=now,
            size=20
        ),
        ProjectFile(
            project_id=project_id,
            path='output.docx',
            created=second_ago,
            modified=now,
            size=200
        ),
    ]
    return EnvironmentHelper(
        respx_mock=respx_mock,
        project=ProjectExtended(
            name='Test',
            id=project_id,
            created=second_ago,
            modified=now,
            path_to_markdown=Path('main.md'),
            path_to_docx=Path('output.docx'),
            files=project_files
        ),
        local_files=project_files,
        requirements=dict()
    )
