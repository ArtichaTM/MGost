from datetime import datetime
from os import utime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, TypedDict

import respx
from httpx import Request, Response

from mgost.api.schemas.mgost import (
    BuildResult, Project, ProjectExtended, ProjectFile
)

from .actions import Action
from .routes import Routes
from .side_effects import FileMethods
from .sync_check import assert_synced


class APIFileInfo(TypedDict):
    path: str


class EnvironmentHelper:
    __slots__ = (
        'respx_mock',
        'project',
        'local_files',
        'temp_dir_local',
        'routes',
        'file_methods',
        'cloud_actions_log',
    )
    respx_mock: respx.MockRouter
    project: ProjectExtended
    local_files: dict[Path, ProjectFile]
    temp_dir_local: TemporaryDirectory | None
    routes: Routes
    file_methods: FileMethods
    cloud_actions_log: list[Action]

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
        self.temp_dir_local = None
        self.file_methods = FileMethods(self)
        self.cloud_actions_log = []

    async def __aenter__(self) -> None:
        assert self.temp_dir_local is None
        self.temp_dir_local = TemporaryDirectory(delete=True)
        self.temp_dir_local.__enter__()
        await self.prepare_environment()

    async def __aexit__(self, exc, value, tb) -> None:
        assert self.temp_dir_local is not None
        assert_synced(self)
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

    def _file_from_path(
        self,
        path: str,
    ) -> ProjectFile | None:
        assert isinstance(path, str)
        for file in self.project.files:
            if file.path == path:
                return file

    async def project_render(self, request: Request) -> Response:
        p = 'output.docx'
        existing_file = self._file_from_path(p)
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

    def _get_route_and_side_effect(
        self,
        type: str,
        method: str
    ):
        assert isinstance(type, str)
        assert isinstance(method, str)
        return (
            self.routes.file.existing.route_dict(method),
            self.file_methods.existing.get_side_effect(method)
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

        cloud_paths: set[Path] = {Path(i.path) for i in self.project.files}
        local_paths: set[Path] = set(self.local_files.keys())
        new_to_cloud_paths = local_paths.difference(cloud_paths)
        for method in {'put', 'post', 'patch', 'delete', 'get'}:
            routes_dict, side_effect_func = self._get_route_and_side_effect(
                'existing', method
            )
            for cloud_file in self.project.files:
                path = Path(cloud_file.path)
                path_str = str(path).replace('\\', '/')
                routes_dict[path] = self.respx_mock.request(
                    method,
                    f"/mgost/project/{self.project.id}/files/{path_str}"
                ).mock(side_effect=side_effect_func)

            routes_dict, side_effect_func = self._get_route_and_side_effect(
                'new', method
            )
            for path in new_to_cloud_paths:
                routes_dict[path] = self.respx_mock.request(
                    method,
                    f"/mgost/project/{self.project.id}/files/{path}"
                ).mock(side_effect=side_effect_func)
