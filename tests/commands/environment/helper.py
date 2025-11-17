import enum
from datetime import datetime
from os import utime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, NotRequired, TypedDict

import respx
from httpx import Request, Response

from mgost.api.schemas.mgost import (
    BuildResult, FileRequirement, Project, ProjectExtended, ProjectFile
)

from ...utils import BASE_URL
from .exit_checkers import assert_new_files_created, assert_synced
from .routes import Routes
from .side_effects import FileMethods


class CustomizableProjectFile(TypedDict):
    project_id: NotRequired[int]
    path: str
    created: NotRequired[datetime]
    modified: NotRequired[datetime]
    size: NotRequired[int]


class ExitChecks(enum.IntFlag):
    SYNCED = enum.auto()
    NEW_LOCAL_FILES_CREATED = enum.auto()

    NONE = 0


class EnvironmentHelper:
    __slots__ = (
        'respx_mock',
        'project',
        'local_files',
        'requirements',
        'temp_dir_local',
        'routes',
        'file_methods',
        'new_local_files',
        'new_projects',
        'exit_checks'
    )
    respx_mock: respx.MockRouter
    project: ProjectExtended
    local_files: dict[Path, ProjectFile]
    requirements: dict[Path, FileRequirement]
    temp_dir_local: TemporaryDirectory | None
    routes: Routes
    file_methods: FileMethods
    new_local_files: list[CustomizableProjectFile]
    new_projects: list[Project]
    exit_checks: ExitChecks

    MD_EXAMPLE_SIZE = 200

    def __init__(
        self,
        respx_mock: respx.MockRouter,
        project: ProjectExtended,
        local_files: Iterable[ProjectFile],
        requirements: list[FileRequirement] | None = None,
        new_local_files: list[CustomizableProjectFile] | None = None,
        exit_checks: ExitChecks = ExitChecks.SYNCED
    ) -> None:
        assert isinstance(respx_mock, respx.MockRouter)
        assert project is None or isinstance(project, ProjectExtended)
        if requirements is None:
            requirements = []
        assert isinstance(requirements, list)
        assert all((isinstance(r, FileRequirement) for r in requirements))
        if new_local_files is None:
            new_local_files = []
        assert isinstance(new_local_files, list)
        assert all((isinstance(
            i, dict
        ) for i in new_local_files))
        assert isinstance(exit_checks, ExitChecks)
        self.respx_mock = respx_mock
        self.project = project
        self.local_files = {Path(f.path): f for f in local_files}
        self.requirements = {Path(k.path): k for k in requirements}
        self.temp_dir_local = None
        self.routes = Routes()
        self.file_methods = FileMethods(self)
        self.new_local_files = new_local_files
        self.new_projects = []
        self.exit_checks = exit_checks

    async def __aenter__(self) -> None:
        assert self.temp_dir_local is None
        self.temp_dir_local = TemporaryDirectory(delete=True)
        self.temp_dir_local.__enter__()
        await self.prepare_environment()

    async def __aexit__(self, exc, value, tb) -> None:
        assert self.temp_dir_local is not None
        if exc is None:
            if self.exit_checks & ExitChecks.SYNCED:
                assert_synced(self)
            if self.exit_checks & ExitChecks.NEW_LOCAL_FILES_CREATED:
                assert_new_files_created(self)

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

    async def route_project_render(self, request: Request) -> Response:
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
            ).model_dump(mode='json')
        )

    async def route_project_put(self, request: Request) -> Response:
        project_id = len(self.new_projects) + 2  # 0/1 reserved
        name = request.url.params.get('project_name', None)
        assert name is not None
        assert isinstance(name, str)
        return Response(
            status_code=200,
            json=Project(
                name=name,
                id=project_id,
                created=datetime.now(),
                modified=datetime.now()
            ).model_dump(mode='json')
        )

    async def _route_examples(self, request: Request) -> Response:
        name = request.url.params.get('name', None)
        assert name is not None, request.url
        assert name == 'init', request.url
        type = request.url.params.get('type', None)
        assert type is not None, request.url
        assert type == 'md', request.url
        return Response(
            status_code=200,
            content='0' * self.MD_EXAMPLE_SIZE
        )

    def _get_route_and_side_effect(
        self,
        type: str,
        method: str
    ):
        assert isinstance(type, str)
        assert isinstance(method, str)
        return (
            self.routes.file.route_dict(method, type),
            self.file_methods.get_side_effect(type, method)
        )

    async def prepare_environment(self) -> None:
        assert self.temp_dir_local is not None
        root_folder = Path(self.temp_dir_local.name)

        for local_file in self.local_files.values():
            file_path = root_folder / local_file.path
            file_path.parent.mkdir(exist_ok=True, parents=True)
            file_path.write_text(data='0' * local_file.size)
            utime(file_path, (
                local_file.created.timestamp(),
                local_file.modified.timestamp()
            ))

        self.routes._projects = self.respx_mock.get(
            f"{BASE_URL}/mgost/project"
        ).respond(status_code=200, json=[
            Project(
                name=self.project.name,
                id=self.project.id,
                created=self.project.created,
                modified=self.project.modified
            ).model_dump(mode='json')
        ])
        self.routes._project_put = self.respx_mock.put(
            f"{BASE_URL}/mgost/project"
        ).mock(side_effect=self.route_project_put)
        self.routes._project = self.respx_mock.get(
            f"{BASE_URL}/mgost/project/{self.project.id}"
        ).respond(status_code=200, json=self.project.model_dump(mode='json'))
        self.routes._project_files = self.respx_mock.get(
            f"{BASE_URL}/mgost/project/{self.project.id}/files"
        ).respond(status_code=200, json=[
            ProjectFile(
                project_id=self.project.id,
                path=str(cloud_file.path),
                created=cloud_file.created,
                modified=cloud_file.modified,
                size=cloud_file.size
            ).model_dump(mode='json') for cloud_file in self.project.files
        ])
        self.routes._project_requirements = self.respx_mock.get(
            f"{BASE_URL}/mgost/project/{self.project.id}/requirements"
        ).respond(status_code=200, json={
            str(path): {"path": str(path)} for path in self.requirements.keys()
        })
        self.routes._project_render = self.respx_mock.get(
            f"{BASE_URL}/mgost/project/{self.project.id}/render"
        ).mock(side_effect=self.route_project_render)
        self.routes._examples = self.respx_mock.get(
            f"{BASE_URL}/mgost/examples"
        ).mock(side_effect=self._route_examples)

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
                    f"{BASE_URL}/mgost/project/{self.project.id}"
                    f"/files/{path_str}"
                ).mock(side_effect=side_effect_func)

            routes_dict, side_effect_func = self._get_route_and_side_effect(
                'new', method
            )
            for path in new_to_cloud_paths:
                path_str = str(path).replace('\\', '/')
                routes_dict[path] = self.respx_mock.request(
                    method,
                    f"{BASE_URL}/mgost/project/{self.project.id}"
                    f"/files/{path_str}"
                ).mock(side_effect=side_effect_func)
