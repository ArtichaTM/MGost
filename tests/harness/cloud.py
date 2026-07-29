import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import respx
from httpx import Request, Response

from mgost.api import ArtichaAPI
from mgost.api.schemas import TokenInfo
from mgost.api.schemas.mgost import (
    BuildResult, Message, Project, ProjectExtended, ProjectFile
)

from ._base import FileStore

__all__ = ('API_PREFIX', 'BASE_URL', 'Call', 'FakeCloud')

BASE_URL = ArtichaAPI._host
API_PREFIX = urlsplit(BASE_URL).path

FILE_RE = re.compile(
    rf'^{re.escape(API_PREFIX)}/mgost/project/(?P<pid>\d+)'
    r'/files/(?P<path>.+)$'
)


@dataclass(frozen=True, slots=True)
class Call:
    """One recorded file-endpoint request.

    `path` is a Path, not a str: Path equality and ordering are the same
    on every platform, while str(Path('a/b')) is 'a\\b' on Windows.
    """

    method: str
    path: Path
    target: Path | None = None

    @classmethod
    def of(cls, request: Request, path: Path) -> 'Call':
        target = request.url.params.get('target', None)
        return cls(request.method, path, Path(target) if target else None)


class FakeCloud(FileStore):
    """The server, modelled as a directory that also answers HTTP."""

    __slots__ = (
        'router', 'project_id', 'name', 'md', 'docx',
        'created', 'requirements', 'calls', 'endpoints', '_next_id',
    )

    EXAMPLE_SIZE = 200

    def __init__(
        self,
        router: respx.MockRouter,
        project_id: int = 1,
        name: str = 'Test',
        md: Path = Path('main.md'),
        docx: Path = Path('output.docx'),
    ) -> None:
        super().__init__(prefix='cloud-')
        self.router = router
        self.project_id = project_id
        self.name = name
        self.md = md
        self.docx = docx
        # `created` cannot live on the filesystem: it is a birth time,
        # which Linux does not expose and no platform lets you set.
        self.created: dict[Path, datetime] = {}
        self.requirements: list[Path] = []
        self.calls: list[Call] = []
        self.endpoints: list[str] = []
        self._next_id = project_id + 1
        self._install_routes()

    # ---------------------------------------------------------------- state

    def add(
        self,
        path: Path,
        size: int,
        modified: datetime,
        created: datetime | None = None,
    ) -> None:
        """Seed a file that already exists on the server."""
        self.materialise(path, size, modified)
        self.created[path] = created or modified

    def as_project_file(self, path: Path) -> ProjectFile:
        return ProjectFile(
            project_id=self.project_id,
            path=path.as_posix(),
            created=self.created.get(path, self.modified(path)),
            modified=self.modified(path),
            size=self.stat(path).st_size,
        )

    def file_calls(self) -> list[Call]:
        """Recorded file operations, sorted by (method, path).

        Sorted on an explicit key rather than making Call order=True,
        because ordering records would compare `target` and None vs Path
        raises. Sorted rather than raw order because sync() gathers
        requirement actions with the docx sync, so ordering is genuinely
        nondeterministic with two or more concurrent actions. Duplicates
        survive, so a double upload still fails.
        """
        return sorted(self.calls, key=lambda c: (c.method, c.path))

    def _record(self, endpoint: str) -> None:
        self.endpoints.append(endpoint)

    # --------------------------------------------------------------- routes

    def _install_routes(self) -> None:
        r = self.router
        r.get(f'{BASE_URL}/me').mock(side_effect=self._handle_me)
        r.get(f'{BASE_URL}/mgost/examples').mock(
            side_effect=self._handle_examples
        )
        r.get(f'{BASE_URL}/mgost/project').mock(
            side_effect=self._handle_projects
        )
        r.put(f'{BASE_URL}/mgost/project').mock(
            side_effect=self._handle_project_create
        )
        base = f'{BASE_URL}/mgost/project/{self.project_id}'
        # Registration order matters: respx matches first-wins, and a bare
        # get(base) would otherwise swallow the three below it.
        r.get(f'{base}/files').mock(side_effect=self._handle_files)
        r.get(f'{base}/requirements').mock(
            side_effect=self._handle_requirements
        )
        r.get(f'{base}/render').mock(side_effect=self._handle_render)
        r.get(base).mock(side_effect=self._handle_project)
        r.route(path__regex=FILE_RE.pattern).mock(
            side_effect=self._handle_file
        )

    async def _handle_me(self, request: Request) -> Response:
        self._record('me')
        now = datetime.now(timezone.utc)
        return Response(200, json=TokenInfo(
            name='Test', owner='TestOwner', created=now, modified=now,
        ).model_dump(mode='json'))

    async def _handle_examples(self, request: Request) -> Response:
        self._record('examples')
        assert request.url.params.get('name') == 'init', request.url
        assert request.url.params.get('type') == 'md', request.url
        return Response(200, content=b'0' * self.EXAMPLE_SIZE)

    async def _handle_projects(self, request: Request) -> Response:
        self._record('projects')
        return Response(200, json=[
            Project(**self._project_fields()).model_dump(mode='json')
        ])

    async def _handle_project_create(self, request: Request) -> Response:
        self._record('project_create')
        name = request.url.params.get('project_name', None)
        assert name is not None, request.url
        now = datetime.now(timezone.utc)
        project_id, self._next_id = self._next_id, self._next_id + 1
        return Response(200, json=Project(
            name=name, id=project_id, created=now, modified=now,
        ).model_dump(mode='json'))

    async def _handle_project(self, request: Request) -> Response:
        self._record('project')
        return Response(200, json=ProjectExtended(
            **self._project_fields(),
            path_to_markdown=self.md,
            path_to_docx=self.docx,
            files=[self.as_project_file(p) for p in sorted(self.paths())],
        ).model_dump(mode='json'))

    async def _handle_files(self, request: Request) -> Response:
        self._record('files')
        return Response(200, json=[
            self.as_project_file(p).model_dump(mode='json')
            for p in sorted(self.paths())
        ])

    async def _handle_requirements(self, request: Request) -> Response:
        self._record('requirements')
        return Response(200, json={
            path.as_posix(): {'path': path.as_posix()}
            for path in self.requirements
        })

    async def _handle_render(self, request: Request) -> Response:
        self._record('render')
        now = datetime.now(timezone.utc)
        if self.exists(self.docx):
            self.write(self.docx, self.read(self.docx), now)
        else:
            self.add(self.docx, size=1, modified=now)
        return Response(200, json=BuildResult(
            max_log_level=0, finished=True, logs=[],
        ).model_dump(mode='json'))

    async def _handle_file(
        self, request: Request, pid: str, path: str
    ) -> Response:
        """respx hands the regex's named groups over as keyword
        arguments, so `pid` and `path` arrive already extracted."""
        assert int(pid) == self.project_id, request.url
        file = Path(path)
        self.calls.append(Call.of(request, file))
        exists = self.exists(file)
        match request.method, exists:
            case 'POST', False:
                return self._create(request, file)
            case 'PUT', True:
                return self._overwrite(request, file)
            case 'GET', True:
                return Response(200, content=self.read(file))
            case 'PATCH', True:
                return self._move_on_cloud(request, file)
            case 'DELETE', True:
                self.remove(file)
                self.created.pop(file, None)
                return self._ok()
            case method, existed:
                raise AssertionError(
                    f'{method} on '
                    f"{'existing' if existed else 'missing'} file "
                    f'{file.as_posix()}'
                )

    def _modify_time(self, request: Request) -> datetime:
        raw = request.url.params.get('modify_time', None)
        assert raw is not None, request.url
        return datetime.fromisoformat(raw)

    def _create(self, request: Request, path: Path) -> Response:
        modified = self._modify_time(request)
        self.write(path, request.read(), modified)
        self.created[path] = modified
        return Response(
            201, json=self.as_project_file(path).model_dump(mode='json')
        )

    def _overwrite(self, request: Request, path: Path) -> Response:
        self.write(path, request.read(), self._modify_time(request))
        return self._ok()

    def _move_on_cloud(self, request: Request, path: Path) -> Response:
        raw_target = request.url.params.get('target', None)
        assert raw_target is not None, request.url
        target = Path(raw_target)
        self.move(path, target)
        self.created[target] = self.created.pop(path, self.modified(target))
        return self._ok()

    # -------------------------------------------------------------- helpers

    def _project_fields(self) -> dict:
        now = datetime.now(timezone.utc)
        return {
            'name': self.name,
            'id': self.project_id,
            'created': now,
            'modified': now,
        }

    @staticmethod
    def _ok() -> Response:
        return Response(200, json=Message().model_dump(mode='json'))
