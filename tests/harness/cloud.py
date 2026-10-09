import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from os.path import normpath
from pathlib import Path, PurePosixPath, PureWindowsPath
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
    r'/files/(?P<fid>\d+)$'
)

# Where fictional files are stored; hidden from `paths()`
FICTIONAL = Path('.fictional')


def is_fictional(written: str) -> bool:
    """The server's rule: absolute, or climbing out of the root"""
    if PurePosixPath(written).is_absolute():
        return True
    if PureWindowsPath(written).is_absolute():
        return True
    normal = normpath(written.replace('\\', '/'))
    return normal == '..' or normal.startswith('../')


@dataclass(frozen=True, slots=True)
class Call:
    """One recorded file-endpoint request.

    `path` is a Path, not a str: Path equality and ordering are the same
    on every platform, while str(Path('a/b')) is 'a\\b' on Windows. A
    fictional file's `path` is `Path(written)`.
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
        '_ids',
        '_next_id',
        'calls',
        'created',
        'docx',
        'endpoints',
        'fictional',
        'md',
        'name',
        'project_id',
        'requirements',
        'router',
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
        # A Path is an ordinary requirement, a str is written as-is
        self.requirements: list[Path | str] = []
        self.calls: list[Call] = []
        self.endpoints: list[str] = []
        self._next_id = project_id + 1
        # Ordinary file ids, assigned on first sight like a DB row's
        self._ids: dict[Path, int] = {}
        # Fictional file id -> path as written
        self.fictional: dict[int, str] = {}
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

    def add_fictional(
        self, written: str, size: int, modified: datetime
    ) -> int:
        """Seed a file uploaded under a path outside the project."""
        assert is_fictional(written), written
        file_id = self._new_id()
        self.fictional[file_id] = written
        self.materialise(self._stored(file_id), size, modified)
        return file_id

    def paths(self) -> set[Path]:
        """Ordinary files only, so convergence checks ignore fictional."""
        return {
            p for p in super().paths() if not p.is_relative_to(FICTIONAL)
        }

    def id_of(self, path: Path) -> int:
        if path not in self._ids:
            self._ids[path] = self._new_id()
        return self._ids[path]

    def _new_id(self) -> int:
        file_id, self._next_id = self._next_id, self._next_id + 1
        return file_id

    @staticmethod
    def _stored(file_id: int) -> Path:
        return FICTIONAL / str(file_id)

    def _by_id(self, file_id: int) -> tuple[Path, str] | None:
        """(stored path, path as listed) of an existing file"""
        if file_id in self.fictional:
            return self._stored(file_id), self.fictional[file_id]
        for path, known in self._ids.items():
            if known == file_id and self.exists(path):
                return path, path.as_posix()
        return None

    def as_project_file(self, path: Path) -> ProjectFile:
        return self._project_file(self.id_of(path), path, path.as_posix())

    def _project_file(
        self, file_id: int, stored: Path, listed: str
    ) -> ProjectFile:
        return ProjectFile(
            id=file_id,
            project_id=self.project_id,
            path=listed,
            fictional=file_id in self.fictional,
            created=self.created.get(stored, self.modified(stored)),
            modified=self.modified(stored),
            size=self.stat(stored).st_size,
            hash=sha256(self.read(stored)).hexdigest(),
        )

    def all_project_files(self) -> list[ProjectFile]:
        ordinary = [self.as_project_file(p) for p in sorted(self.paths())]
        return ordinary + [
            self._project_file(i, self._stored(i), written)
            for i, written in sorted(self.fictional.items())
        ]

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
        r.post(f'{base}/files').mock(side_effect=self._handle_create)
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
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)
        project_id = self._new_id()
        return Response(200, json=Project(
            name=name, id=project_id, created=now, modified=now,
        ).model_dump(mode='json'))

    async def _handle_project(self, request: Request) -> Response:
        self._record('project')
        return Response(200, json=ProjectExtended(
            **self._project_fields(),
            path_to_markdown=self.md,
            path_to_docx=self.docx,
            files=self.all_project_files(),
        ).model_dump(mode='json'))

    async def _handle_files(self, request: Request) -> Response:
        self._record('files')
        return Response(200, json=[
            i.model_dump(mode='json') for i in self.all_project_files()
        ])

    async def _handle_requirements(self, request: Request) -> Response:
        self._record('requirements')
        return Response(200, json=[
            {'path': written, 'file_id': self._requirement_id(written)}
            for written in (
                r.as_posix() if isinstance(r, Path) else r
                for r in self.requirements
            )
        ])

    def _requirement_id(self, written: str) -> int | None:
        if is_fictional(written):
            for file_id, known in self.fictional.items():
                if known == written:
                    return file_id
            return None
        path = Path(written)
        return self.id_of(path) if self.exists(path) else None

    async def _handle_render(self, request: Request) -> Response:
        self._record('render')
        now = datetime.now(UTC)
        if self.exists(self.docx):
            self.write(self.docx, self.read(self.docx), now)
        else:
            self.add(self.docx, size=1, modified=now)
        return Response(200, json=BuildResult(
            max_log_level=0, finished=True, logs=[],
        ).model_dump(mode='json'))

    async def _handle_create(self, request: Request) -> Response:
        written = request.url.params.get('path', None)
        assert written is not None, request.url
        self.calls.append(Call.of(request, Path(written)))
        if is_fictional(written):
            assert written not in self.fictional.values(), (
                f'POST on existing file {written}'
            )
            file_id = self._new_id()
            self.fictional[file_id] = written
            stored = self._stored(file_id)
        else:
            stored = Path(written)
            assert not self.exists(stored), (
                f'POST on existing file {written}'
            )
            self._ids.pop(stored, None)
            file_id = self.id_of(stored)
        modified = self._modify_time(request)
        self.write(stored, request.read(), modified)
        self.created[stored] = modified
        return Response(201, json=self._project_file(
            file_id, stored, written
        ).model_dump(mode='json'))

    async def _handle_file(
        self, request: Request, pid: str, fid: str
    ) -> Response:
        """respx hands the regex's named groups over as keyword
        arguments, so `pid` and `fid` arrive already extracted."""
        assert int(pid) == self.project_id, request.url
        file_id = int(fid)
        found = self._by_id(file_id)
        if found is None:
            raise AssertionError(
                f'{request.method} on missing file {file_id}'
            )
        stored, listed = found
        self.calls.append(Call.of(request, Path(listed)))
        match request.method:
            case 'PUT':
                return self._overwrite(request, stored)
            case 'GET':
                return Response(200, content=self.read(stored))
            case 'PATCH':
                assert file_id not in self.fictional, (
                    f'PATCH on fictional file {listed}'
                )
                return self._move_on_cloud(request, stored)
            case 'DELETE':
                self.remove(stored)
                self.created.pop(stored, None)
                self.fictional.pop(file_id, None)
                return self._ok()
            case method:
                raise AssertionError(f'{method} on file {listed}')

    def _modify_time(self, request: Request) -> datetime:
        raw = request.url.params.get('modify_time', None)
        assert raw is not None, request.url
        return datetime.fromisoformat(raw)

    def _overwrite(self, request: Request, path: Path) -> Response:
        self.write(path, request.read(), self._modify_time(request))
        return self._ok()

    def _move_on_cloud(self, request: Request, path: Path) -> Response:
        raw_target = request.url.params.get('target', None)
        assert raw_target is not None, request.url
        target = Path(raw_target)
        self.move(path, target)
        self._ids[target] = self._ids.pop(path)
        self.created[target] = self.created.pop(path, self.modified(target))
        return self._ok()

    # -------------------------------------------------------------- helpers

    def _project_fields(self) -> dict:
        now = datetime.now(UTC)
        return {
            'name': self.name,
            'id': self.project_id,
            'created': now,
            'modified': now,
        }

    @staticmethod
    def _ok() -> Response:
        return Response(200, json=Message().model_dump(mode='json'))
